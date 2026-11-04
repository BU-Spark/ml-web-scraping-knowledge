"""Offline tests for knowledge extraction, schema validation, and embedding."""
import json
from pathlib import Path
import unittest

from data_pipeline.embedder import embed_units
from data_pipeline.extractor import (
    assign_category,
    build_embed_text,
    enrich_unit,
    extract_from_chunks,
)
from data_pipeline.validator import validate_batch, verify_quote_in_chunk


class KnowledgeExtractionTests(unittest.TestCase):
    def setUp(self):
        self.sample_chunks = json.loads(
            Path("data/samples/chunks_semantic.json").read_text(encoding="utf-8")
        )

    def test_extract_filters_common_sense_and_content(self):
        """Retention rule keeps know_how and knowledge, dropping common_sense and content."""
        target_chunks = [
            self.sample_chunks[0],  # sem-0-0 (intro fluff)
            self.sample_chunks[5],  # sem-3-0 (Stage 2: Qualify Leads)
            self.sample_chunks[9],  # sem-5-0 (Stage 4: Handle Objections)
        ]

        def mock_llm(chunk):
            cid = chunk["chunk_id"]
            if cid == "sem-0-0":
                return [
                    {
                        "claim": "The sales process from prospect to close is full of obstacles.",
                        "evidence_quote": "The sales process from prospect to close is often full of uphill climbs",
                        "level": "common_sense",
                        "unit_type": "definition",
                        "context": {
                            "who": "unknown",
                            "industry": "unknown",
                            "company_size": "unknown",
                            "situation": "unknown",
                        },
                        "outcome": None,
                        "topic": "sales process",
                    }
                ]
            if cid == "sem-3-0":
                return [
                    {
                        "claim": "Salespeople should ask prospects what they need and want from the conversation before pitching their company.",
                        "evidence_quote": "Before diving straight into who you are and what you do, ask them if they’d like to tell you what they need, what’s important to them, and what they want to get from the conversation.",
                        "level": "know_how",
                        "unit_type": "how_to",
                        "context": {
                            "who": "salespeople",
                            "industry": "unknown",
                            "company_size": "unknown",
                            "situation": "Stage 2: Qualify Leads",
                        },
                        "outcome": None,
                        "topic": "lead qualification",
                    },
                    {
                        "claim": "78% of surveyed salespeople reported that listening had a substantial impact on converting a prospect into a customer.",
                        "evidence_quote": "78% of salespeople said that listening had a substantial impact on converting a prospect into a customer.",
                        "level": "knowledge",
                        "unit_type": "statistic",
                        "context": {
                            "who": "salespeople",
                            "industry": "unknown",
                            "company_size": "unknown",
                            "situation": "converting a prospect into a customer",
                        },
                        "outcome": "substantial impact on converting a prospect into a customer (reported by 78% of salespeople)",
                        "topic": "active listening",
                    },
                ]
            if cid == "sem-5-0":
                return [
                    {
                        "claim": "Top sales performers counter client objections over 23% more often than average performers.",
                        "evidence_quote": "Top sales performers counter client objections over 23% more often than average performers .",
                        "level": "knowledge",
                        "unit_type": "statistic",
                        "context": {
                            "who": "top sales performers",
                            "industry": "unknown",
                            "company_size": "unknown",
                            "situation": "Stage 4: Handle Objections",
                        },
                        "outcome": "counter client objections over 23% more often",
                        "topic": "objection handling",
                    }
                ]
            return []

        retained, all_units = extract_from_chunks(
            target_chunks, llm_fn=mock_llm, extracted_at="2026-11-04"
        )
        self.assertEqual(len(all_units), 4)
        self.assertEqual(len(retained), 3)
        self.assertTrue(all(u["level"] in ("know_how", "knowledge") for u in retained))

        valid_units, rejected = validate_batch(retained, target_chunks)
        self.assertEqual(len(rejected), 0)
        self.assertEqual(len(valid_units), 3)

        # Verify provenance and code-populated fields
        first = valid_units[0]
        self.assertEqual(first["publisher"], "Salesforce")
        self.assertEqual(first["source_type"], "external")
        self.assertEqual(first["sensitivity"], "public")
        self.assertEqual(first["source_tier"], 1)
        self.assertEqual(first["category"], "1. Sales Methodology and Process")
        self.assertIsNone(first["outcome"])

    def test_validator_rejects_fabricated_quote(self):
        """Validator catches hallucinated evidence quotes not present in the chunk."""
        chunk = self.sample_chunks[5]
        bad_raw = {
            "claim": "Sales reps must send three follow-up emails within 48 hours.",
            "evidence_quote": "Always send three follow-up emails within 48 hours of contact.",
            "level": "know_how",
            "unit_type": "how_to",
            "context": {
                "who": "sales reps",
                "industry": "unknown",
                "company_size": "unknown",
                "situation": "follow-up",
            },
            "outcome": None,
            "topic": "follow-up cadence",
        }
        unit = enrich_unit(bad_raw, chunk, 0, extracted_at="2026-11-04")
        valid_units, rejected = validate_batch([unit], [chunk])
        self.assertEqual(len(valid_units), 0)
        self.assertEqual(len(rejected), 1)
        self.assertTrue(
            any("grounding" in err for err in rejected[0]["errors"])
        )

    def test_ellipsis_quote_matching_and_category_routing(self):
        """Ellipsis-joined quotes validate cleanly and enablement topics route to Area 10."""
        chunk = self.sample_chunks[12]  # sem-6-1 (mentions CPQ and BANT)
        quote = "configure price quote software is projected to grow 126%... know this customer has the “Budget, Authority, Needs, and Timeline” (BANT)"
        self.assertTrue(verify_quote_in_chunk(quote, chunk["text"]))

        cat = assign_category(
            {"claim": "Weekly call reviews cut new-rep ramp time from 6 to 4 months", "topic": "call coaching"},
            {"heading": "Coaching"},
        )
        self.assertEqual(cat, "10. Enablement Operations")

    def test_embedder_populates_vectors_offline(self):
        """Embedder populates float vectors without downloading models when given a mock."""
        chunk = self.sample_chunks[5]
        raw = {
            "claim": "Ask prospects what they want to get from the conversation before pitching.",
            "evidence_quote": "ask them if they’d like to tell you what they need, what’s important to them, and what they want to get from the conversation.",
            "level": "know_how",
            "unit_type": "how_to",
            "context": {"who": "salespeople", "industry": "unknown", "company_size": "unknown", "situation": "qualification"},
            "outcome": None,
            "topic": "lead qualification",
        }
        unit = enrich_unit(raw, chunk, 0, extracted_at="2026-11-04")
        embedded = embed_units([unit], embed_fn=lambda texts: [[0.1, 0.2, 0.3] for _ in texts])
        self.assertEqual(len(embedded), 1)
        self.assertEqual(embedded[0]["embedding"], [0.1, 0.2, 0.3])
        self.assertIn("Topic: lead qualification.", build_embed_text(unit))


if __name__ == "__main__":
    unittest.main()
