"""Offline tests for first-principles knowledge extraction, epistemic gating, corroboration, and embedding."""
import json
from pathlib import Path
import unittest

from data_pipeline.deduplicator import deduplicate_units
from data_pipeline.embedder import embed_units
from data_pipeline.extractor import (
    apply_epistemic_calibration,
    assign_category,
    build_embed_text,
    compute_authority_weight,
    enrich_unit,
    extract_from_chunks,
    normalize_company_size,
)
from data_pipeline.validator import validate_batch, verify_quote_in_chunk


class KnowledgeExtractionTests(unittest.TestCase):
    def setUp(self):
        self.sample_chunks = json.loads(
            Path("data/samples/chunks_semantic.json").read_text(encoding="utf-8")
        )

    def test_extract_filters_common_sense_and_content(self):
        """Retention rule keeps know_how and knowledge, dropping common_sense, platitudes, and e-book teasers."""
        target_chunks = [
            self.sample_chunks[0],  # sem-0-0 (intro fluff)
            self.sample_chunks[4],  # sem-2-0 (Stage 1: Contact Leads + e-book teaser)
            self.sample_chunks[5],  # sem-3-0 (Stage 2: Qualify Leads)
            self.sample_chunks[9],  # sem-5-0 (Stage 4: Handle Objections)
        ]

        def mock_llm(chunk):
            cid = chunk["chunk_id"]
            if cid == "sem-0-0":
                return [
                    {
                        "claim": "The sales process from prospect to close is full of obstacles.",
                        "actionable_step": None,
                        "evidence_quote": "The sales process from prospect to close is often full of uphill climbs",
                        "level": "common_sense",
                        "level_rationale": "Truism obvious to any layperson without sales training.",
                        "specificity_score": 1,
                        "is_obvious_to_layperson": True,
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
            if cid == "sem-2-0":
                return [
                    # Even if the model mistakenly labels an e-book teaser as know_how, epistemic calibration drops it!
                    {
                        "claim": "This e-book chapter addresses how to use inbound marketing to control costs.",
                        "actionable_step": "Read the e-book chapter on inbound marketing.",
                        "evidence_quote": "In this e-book chapter, we also address: How to start the conversation — ask questions, build on previous experiences How to use inbound marketing to control your costs",
                        "level": "know_how",
                        "level_rationale": "Chapter preview.",
                        "specificity_score": 3,
                        "is_obvious_to_layperson": False,
                        "unit_type": "how_to",
                        "context": {
                            "who": "unknown",
                            "industry": "unknown",
                            "company_size": "unknown",
                            "situation": "Stage 1: Contact Leads",
                        },
                        "outcome": None,
                        "topic": "inbound marketing",
                    }
                ]
            if cid == "sem-3-0":
                return [
                    {
                        "claim": "Salespeople should ask prospects what they need and want from the conversation before pitching their company.",
                        "actionable_step": "Open qualification calls by asking the prospect to state their needs, priorities, and desired conversation outcome before describing your company.",
                        "evidence_quote": "Before diving straight into who you are and what you do, ask them if they’d like to tell you what they need, what’s important to them, and what they want to get from the conversation.",
                        "level": "know_how",
                        "level_rationale": "Concrete conversational sequence for lead qualification calls.",
                        "specificity_score": 4,
                        "is_obvious_to_layperson": False,
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
                        "actionable_step": None,
                        "evidence_quote": "78% of salespeople said that listening had a substantial impact on converting a prospect into a customer.",
                        "level": "knowledge",
                        "level_rationale": "Empirical survey benchmark tying active listening to prospect conversion.",
                        "specificity_score": 4,
                        "is_obvious_to_layperson": False,
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
                        "actionable_step": None,
                        "evidence_quote": "Top sales performers counter client objections over 23% more often than average performers .",
                        "level": "knowledge",
                        "level_rationale": "Quantitative benchmark differentiating top performers from average performers.",
                        "specificity_score": 5,
                        "is_obvious_to_layperson": False,
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
            target_chunks, llm_fn=mock_llm, extracted_at="2026-11-15"
        )
        self.assertEqual(len(all_units), 5)
        self.assertEqual(len(retained), 3)
        self.assertTrue(all(u["level"] in ("know_how", "knowledge") for u in retained))

        valid_units, rejected = validate_batch(retained, target_chunks)
        self.assertEqual(len(rejected), 0)
        self.assertEqual(len(valid_units), 3)

        first = valid_units[0]
        self.assertEqual(first["publisher"], "Salesforce")
        self.assertEqual(first["source_type"], "external")
        self.assertEqual(first["sensitivity"], "public")
        self.assertEqual(first["source_tier"], 1)
        self.assertEqual(first["authority_weight"], 1.0)
        self.assertEqual(first["corroboration_count"], 1)
        self.assertEqual(first["category"], "1. Sales Methodology and Process")
        self.assertIsNone(first["outcome"])

    def test_internal_visibility_and_section_index_handling(self):
        """Extractor preserves section_index, internal visibility,confidential sensitivity, and chunk category."""
        internal_chunk = dict(self.sample_chunks[5])
        internal_chunk["section_id"] = "sec-string-id"
        internal_chunk["section_index"] = 7
        internal_chunk["visibility"] = "internal"
        internal_chunk["category"] = "2"
        internal_chunk["source_metadata"] = {
            "publisher": "Salesforce Internal Enablement",
            "published_date": "2026-10-01",
        }

        raw = {
            "claim": "Ask prospects what they want to get from the conversation before pitching.",
            "actionable_step": "Ask the prospect for their goals at the start of the discovery call.",
            "evidence_quote": "ask them if they’d like to tell you what they need, what’s important to them, and what they want to get from the conversation.",
            "level": "know_how",
            "specificity_score": 4,
            "is_obvious_to_layperson": False,
            "unit_type": "how_to",
            "context": {"who": "salespeople", "industry": "unknown", "company_size": "unknown", "situation": "qualification"},
            "outcome": None,
            "topic": "lead qualification",
        }
        unit = enrich_unit(raw, internal_chunk, 0, extracted_at="2026-11-15")
        self.assertEqual(unit["section_id"], 7)
        self.assertEqual(unit["source_type"], "internal")
        self.assertEqual(unit["sensitivity"], "confidential")
        self.assertEqual(unit["category"], "2. Segmentation and Territory")
        self.assertEqual(unit["publisher"], "Salesforce Internal Enablement")
        self.assertEqual(unit["published_date"], "2026-10-01")

    def test_epistemic_calibration_drops_misclassified_platitudes(self):
        """First-principles calibration catches 'Follow up after a meeting' even if LLM labels it know_how."""
        chunk = self.sample_chunks[5]
        platitude_raw = {
            "claim": "Follow up after a meeting.",
            "actionable_step": None,
            "evidence_quote": "Before diving straight into who you are and what you do",
            "level": "know_how",
            "specificity_score": 2,
            "is_obvious_to_layperson": True,
            "unit_type": "how_to",
            "context": {"who": "reps", "industry": "unknown", "company_size": "mom and pop", "situation": "post-meeting"},
            "outcome": None,
            "topic": "follow up",
        }
        unit = enrich_unit(platitude_raw, chunk, 0, extracted_at="2026-11-15")
        self.assertEqual(unit["level"], "common_sense")
        self.assertEqual(unit["context"]["company_size"], "SMB (small business)")
        self.assertEqual(normalize_company_size("50,000 employees"), "Enterprise")

    def test_deduplicator_corroborates_same_context_and_preserves_distinct_context(self):
        """Deduplicator merges corroborating sources (Tier 1 anchor first) while keeping SMB vs Enterprise separate."""
        chunk_sf = self.sample_chunks[5]  # Tier 1 Salesforce
        chunk_blog = dict(self.sample_chunks[5])
        chunk_blog["chunk_id"] = "sem-ext-0"
        chunk_blog["source_url"] = "https://salesblog.example.com/qualify"
        chunk_blog["domain"] = "salesblog.example.com"
        chunk_blog["page_title"] = "Sales Blog"

        raw_claim = {
            "claim": "Salespeople should ask prospects what they need and want from the conversation before pitching.",
            "actionable_step": "Ask the lead to share their needs and goals before presenting company offerings.",
            "evidence_quote": "Before diving straight into who you are and what you do, ask them if they’d like to tell you what they need, what’s important to them, and what they want to get from the conversation.",
            "level": "know_how",
            "specificity_score": 4,
            "is_obvious_to_layperson": False,
            "unit_type": "how_to",
            "context": {"who": "salespeople", "industry": "software", "company_size": "Enterprise", "situation": "qualification"},
            "outcome": None,
            "topic": "lead qualification",
        }

        # Unit 1 from Tier 3 blog, Unit 2 from Tier 1 Salesforce (same claim + same Enterprise context)
        unit_tier3 = enrich_unit(raw_claim, chunk_blog, 0, extracted_at="2026-11-15")
        unit_tier1 = enrich_unit(raw_claim, chunk_sf, 0, extracted_at="2026-11-15")

        # Unit 3 has the same claim but for SMB (mom and pop) context -> must remain a separate vector!
        raw_smb = dict(raw_claim)
        raw_smb["context"] = {"who": "salespeople", "industry": "software", "company_size": "mom and pop", "situation": "qualification"}
        unit_smb = enrich_unit(raw_smb, chunk_sf, 1, extracted_at="2026-11-15")

        deduped = deduplicate_units([unit_tier3, unit_tier1, unit_smb])
        self.assertEqual(len(deduped), 2)

        enterprise_unit = [u for u in deduped if u["context"]["company_size"] == "Enterprise"][0]
        # Tier 1 Salesforce must win as the primary anchor even though Tier 3 was passed first
        self.assertEqual(enterprise_unit["publisher"], "Salesforce")
        self.assertEqual(enterprise_unit["source_tier"], 1)
        self.assertEqual(enterprise_unit["corroboration_count"], 2)
        self.assertEqual(len(enterprise_unit["corroborating_sources"]), 2)
        self.assertEqual(enterprise_unit["authority_weight"], compute_authority_weight(1, 2))

    def test_validator_rejects_fabricated_quote(self):
        """Validator catches hallucinated evidence quotes not present in the chunk."""
        chunk = self.sample_chunks[5]
        bad_raw = {
            "claim": "Sales reps must send three follow-up emails within 48 hours.",
            "actionable_step": "Send three follow-up emails within 48 hours.",
            "evidence_quote": "Always send three follow-up emails within 48 hours of contact.",
            "level": "know_how",
            "specificity_score": 4,
            "is_obvious_to_layperson": False,
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
        unit = enrich_unit(bad_raw, chunk, 0, extracted_at="2026-11-15")
        valid_units, rejected = validate_batch([unit], [chunk])
        self.assertEqual(len(valid_units), 0)
        self.assertEqual(len(rejected), 1)
        self.assertTrue(any("grounding" in err for err in rejected[0]["errors"]))

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
            "actionable_step": "Ask the prospect for their goals at the start of the discovery call.",
            "evidence_quote": "ask them if they’d like to tell you what they need, what’s important to them, and what they want to get from the conversation.",
            "level": "know_how",
            "specificity_score": 4,
            "is_obvious_to_layperson": False,
            "unit_type": "how_to",
            "context": {"who": "salespeople", "industry": "unknown", "company_size": "unknown", "situation": "qualification"},
            "outcome": None,
            "topic": "lead qualification",
        }
        unit = enrich_unit(raw, chunk, 0, extracted_at="2026-11-15")
        embedded = embed_units([unit], embed_fn=lambda texts: [[0.1, 0.2, 0.3] for _ in texts])
        self.assertEqual(len(embedded), 1)
        self.assertEqual(embedded[0]["embedding"], [0.1, 0.2, 0.3])
        self.assertIn("Topic: lead qualification.", build_embed_text(unit))


if __name__ == "__main__":
    unittest.main()
