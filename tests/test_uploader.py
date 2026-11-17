"""Loader tests. Format checks always run; the rest read the real Bain page from
data/output/scrape/clean/ at runtime (gitignored) and, for live tests, write only to a temporary
schema in TEST_DATABASE_URL (see tests/test_database.py). Nothing scraped is stored in this file.
"""
import json
from pathlib import Path

import pytest

from data_pipeline import uploader
from tests.test_database import CLEAN_DOC, conn, live  # noqa: F401  (conn is a fixture)

REGISTRY = Path("data/output/scrape/registry.jsonl")
real = pytest.mark.skipif(not CLEAN_DOC.exists(), reason="scraped pages not in data/output")


@pytest.mark.parametrize("value", [10, "10", "10. Enablement Operations", "enablement_operations",
                                   "Enablement Operations"])
def test_every_category_form_maps_to_the_name(value):
    assert uploader.category_name(value) == "Enablement Operations"


def test_unknown_category_passes_through_for_the_database_to_reject():
    assert uploader.category_name("Pricing Strategy") == "Pricing Strategy"


def test_dropped_levels_are_skipped():
    assert uploader.unit_row({"level": "common_sense"}) is None
    assert uploader.unit_row({"level": "content"}) is None


def real_inputs():
    """Registry line, clean doc, one chunk (chunker field names) and two units, all from the Bain page."""
    doc = json.loads(CLEAN_DOC.read_text(encoding="utf-8"))
    registry = [r for r in uploader.read_registry(REGISTRY) if r["doc_id"] == doc["doc_id"]]
    section = doc["sections"][0]
    text = section["text"][:884]
    chunk = {"chunk_id": "sem-test", "doc_id": doc["doc_id"], "section_id": f"{doc['doc_id']}:section:0",
             "section_index": 0, "chunk_index": 0, "heading": section["heading"], "heading_level": 2,
             "heading_path": [section["heading"]], "start": 0, "end": len(text), "text": text,
             "tags": [], "category": doc["category"], "visibility": "public", "sensitivity": None,
             "strategy": "semantic", "schema_version": "1.0", "page_title": doc["title"]}
    sentence = text.split(". ")[0]
    unit = {"unit_id": "ku-sem-test-0", "chunk_id": "sem-test", "section_id": 0, "claim": sentence,
            "evidence_quote": sentence, "level": "knowledge", "unit_type": "statistic",
            "context": {"company_size": "unknown"}, "outcome": None, "topic": None,
            "category": "10. Enablement Operations", "source_url": doc["url"], "domain": doc["domain"],
            "publisher": doc["publisher"], "published_date": doc["published_date"],
            "page_title": doc["title"], "heading": section["heading"], "char_start": 0,
            "char_end": len(text), "source_type": "external", "sensitivity": "public", "source_tier": 3,
            "extracted_at": "2026-11-04", "embed_text": sentence, "embedding": None}
    dropped = dict(unit, unit_id="ku-sem-test-1", level="common_sense")
    orphan = dict(unit, unit_id="ku-orphan", chunk_id="sem-missing")
    return registry, [doc], [chunk], [unit, dropped, orphan]


@real
def test_real_doc_and_chunk_translate():
    _, docs, chunks, units = real_inputs()
    d = uploader.document_row(docs[0])
    assert d["category"] == "Enablement Operations" and d["sensitivity"] == "public"
    c = uploader.chunk_row(chunks[0])
    assert (c["char_start"], c["category"]) == (0, "Enablement Operations")
    assert uploader.unit_row(units[0])["category"] == "Enablement Operations"


@real
@live
def test_load_is_idempotent_and_skips_bad_units(conn):  # noqa: F811
    inputs = real_inputs()
    first = uploader.load(conn, *inputs)
    assert first == {"scrape_log": 1, "documents": 1, "chunks": 1, "chunks_skipped_no_document": 0,
                     "units_skipped_level": 1, "units_skipped_no_chunk": 1, "units": 1,
                     "units_without_embedding": 1}
    uploader.load(conn, *inputs)
    counts = [conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in ("scrape_log", "documents", "chunks", "units")]
    assert counts == [1, 1, 1, 1]
    assert conn.execute("SELECT category, visibility FROM served_units").fetchone() == \
        ("Enablement Operations", "public")


@real
@live
def test_given_embeddings_are_stored(conn):  # noqa: F811
    registry, docs, chunks, units = real_inputs()
    units[0]["embedding"] = [0.0] * 383 + [1.0]
    uploader.load(conn, registry, docs, chunks, units[:1])
    assert conn.execute("SELECT vector_dims(embedding) FROM units").fetchone()[0] == 384


@real
@live
def test_embed_fn_fills_missing_embeddings(conn):  # noqa: F811
    registry, docs, chunks, units = real_inputs()
    counts = uploader.load(conn, registry, docs, chunks, units[:1], embed_fn=lambda texts: [[1.0] + [0.0] * 383 for _ in texts])
    assert counts["units_without_embedding"] == 0
