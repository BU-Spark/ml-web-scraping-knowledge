"""Load pipeline output into Postgres (schema: database/migrations/001_init.sql).

    python3 -m data_pipeline.uploader --registry data/output/scrape/registry.jsonl \
        --docs data/output/scrape/clean --chunks data/output/chunks_semantic.json \
        --units data/output/knowledge_units_validated.json [--embed] [--dry-run]

Every input is optional, but rows are loaded in dependency order: scrape_log, documents, chunks,
units. Each row is upserted (inserted, or updated if its id already exists), so re-running after
a re-scrape or re-extraction updates rows instead of duplicating them.

Formats are taken as each stage writes them and translated here, so no stage has to change:
  - category 10 / "10. Enablement Operations" / "enablement_operations" -> "Enablement Operations"
  - chunk start/end -> char_start/char_end
  - fields the tables do not have are ignored
Units at level common_sense/content are skipped. Chunks whose document, and units whose chunk, is
not in the database are skipped and counted, not loaded. Only ids and counts are logged, never
text (internal documents may be loaded).

Writes to DATABASE_URL (.env). Loading into a shared database (Heroku) needs team approval.
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CATEGORY_NAMES = {
    1: "Sales Methodology and Process",
    2: "Segmentation and Territory",
    10: "Enablement Operations",
}
SLUGS = {  # scraper's category_name values (data_pipeline/scraper/config.py)
    "sales_methodology": CATEGORY_NAMES[1],
    "segmentation_territory": CATEGORY_NAMES[2],
    "enablement_operations": CATEGORY_NAMES[10],
}
KEPT_LEVELS = {"know_how", "knowledge"}


# ---------- format translation (pure functions, no database) ----------

def category_name(value):
    """Return the category name for any form the pipeline writes; None if missing."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return CATEGORY_NAMES.get(value, str(value))
    text = str(value).strip()
    if text.isdigit():
        return CATEGORY_NAMES.get(int(text), text)
    text = re.sub(r"^\d+\.\s*", "", text)          # "10. Enablement Operations"
    return SLUGS.get(text, text)                     # "enablement_operations"


def scrape_log_row(rec):
    return {
        "doc_id": rec["doc_id"], "url": rec["url"], "final_url": rec.get("final_url"),
        "domain": rec.get("domain"), "category": category_name(rec.get("category")),
        "section_label": rec.get("section_label"), "status": rec["status"], "reason": rec.get("reason"),
        "http_status": rec.get("http_status"), "fetch_method": rec.get("fetch_method"),
        "content_type": rec.get("content_type"), "word_count": rec.get("word_count"),
        "content_sha256": rec.get("content_sha256"), "retrieved_at": rec.get("retrieved_at"),
        "robots_allowed": rec.get("robots_allowed"), "tos_flag": rec.get("tos_flag"),
        "duplicate_of": rec.get("duplicate_of"),
    }


def document_row(doc):
    visibility = doc.get("visibility") or "public"
    return {
        "doc_id": doc["doc_id"], "url": doc.get("url"), "canonical_url": doc.get("canonical_url"),
        "source_file": doc.get("source_file"), "domain": doc.get("domain"),
        "publisher": doc.get("publisher"), "title": doc.get("title"), "author": doc.get("author"),
        "published_date": doc.get("published_date"), "retrieved_at": doc.get("retrieved_at"),
        "category": category_name(doc.get("category")),
        "also_categories": [category_name(c) for c in doc.get("also_categories") or []],
        "visibility": visibility,
        "sensitivity": doc.get("sensitivity") or ("public" if visibility == "public" else "confidential"),
    }


def chunk_row(ch):
    visibility = ch.get("visibility") or "public"
    return {
        "chunk_id": ch["chunk_id"], "doc_id": ch["doc_id"], "section_id": str(ch["section_id"]),
        "section_index": ch["section_index"], "chunk_index": ch["chunk_index"],
        "heading": ch.get("heading"), "heading_level": ch.get("heading_level"),
        "heading_path": ch.get("heading_path") or [],
        "char_start": ch.get("start", ch.get("char_start")), "char_end": ch.get("end", ch.get("char_end")),
        "text": ch["text"], "tags": ch.get("tags") or [], "category": category_name(ch.get("category")),
        "visibility": visibility,
        "sensitivity": ch.get("sensitivity") or ("public" if visibility == "public" else "confidential"),
        "strategy": ch.get("strategy"), "schema_version": ch.get("schema_version"),
    }


def unit_row(u):
    """Return a units row, or None if the unit's level is not kept."""
    if u.get("level") not in KEPT_LEVELS:
        return None
    return {
        "unit_id": u["unit_id"], "chunk_id": u["chunk_id"], "section_id": u.get("section_id"),
        "claim": u["claim"], "evidence_quote": u["evidence_quote"], "level": u["level"],
        "unit_type": u["unit_type"], "context": u.get("context") or {}, "outcome": u.get("outcome"),
        "topic": u.get("topic"), "category": category_name(u.get("category")),
        "source_url": u.get("source_url") or None, "domain": u.get("domain"),
        "publisher": u.get("publisher"), "published_date": u.get("published_date"),
        "page_title": u.get("page_title"), "heading": u.get("heading"),
        "char_start": u.get("char_start"), "char_end": u.get("char_end"),
        "source_type": u.get("source_type") or "external", "sensitivity": u.get("sensitivity") or "public",
        "source_tier": u.get("source_tier"), "extracted_at": u.get("extracted_at"),
        "embed_text": u.get("embed_text"), "embedding": u.get("embedding"),
    }


# ---------- reading input files ----------

def read_registry(path):
    """Public scrape registry lines (internal registries have no URL and are not scrape-log rows)."""
    with open(path, encoding="utf-8") as f:
        return [rec for rec in map(json.loads, filter(str.strip, f)) if rec.get("url")]


def read_docs(paths):
    files = []
    for p in map(Path, paths):
        files.extend(sorted(p.glob("*.json")) if p.is_dir() else [p])
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def read_json_list(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("chunks") or data.get("units") or []


# ---------- writing to Postgres ----------

def upsert(conn, table, key, rows):
    """Insert rows; on an existing key, overwrite with the new values. Returns the row count."""
    if not rows:
        return 0
    from psycopg.types.json import Jsonb

    cols = list(rows[0])
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != key)
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
           f"ON CONFLICT ({key}) DO UPDATE SET {updates}, loaded_at = now()")
    values = [[Jsonb(r[c]) if isinstance(r[c], dict) else r[c] for c in cols] for r in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, values)
    return len(rows)


def existing_ids(conn, table, key):
    return {row[0] for row in conn.execute(f"SELECT {key} FROM {table}")}


def vector_literal(vec):
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def load(conn, registry=None, docs=None, chunks=None, units=None, embed_fn=None):
    """Load whatever inputs are given, in dependency order. Returns counts per table."""
    counts = {}
    with conn.transaction():
        if registry is not None:
            counts["scrape_log"] = upsert(conn, "scrape_log", "doc_id", [scrape_log_row(r) for r in registry])
        if docs is not None:
            counts["documents"] = upsert(conn, "documents", "doc_id", [document_row(d) for d in docs])
        if chunks is not None:
            known = existing_ids(conn, "documents", "doc_id")
            rows = [chunk_row(c) for c in chunks]
            kept = [r for r in rows if r["doc_id"] in known]
            counts["chunks"] = upsert(conn, "chunks", "chunk_id", kept)
            counts["chunks_skipped_no_document"] = len(rows) - len(kept)
        if units is not None:
            rows = [unit_row(u) for u in units]
            counts["units_skipped_level"] = sum(r is None for r in rows)
            known = existing_ids(conn, "chunks", "chunk_id")
            kept = [r for r in rows if r is not None and r["chunk_id"] in known]
            counts["units_skipped_no_chunk"] = sum(r is not None for r in rows) - len(kept)
            missing = [r for r in kept if not r["embedding"]]
            if missing and embed_fn is not None:
                for r, vec in zip(missing, embed_fn([r["embed_text"] or r["claim"] for r in missing])):
                    r["embedding"] = vec
            for r in kept:
                r["embedding"] = vector_literal(r["embedding"]) if r["embedding"] else None
            counts["units"] = upsert(conn, "units", "unit_id", kept)
            counts["units_without_embedding"] = sum(r["embedding"] is None for r in kept)
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", help="scraper registry.jsonl")
    parser.add_argument("--docs", nargs="+", help="clean doc folder(s) or files")
    parser.add_argument("--chunks", help="chunker output .json")
    parser.add_argument("--units", help="extractor/validator/embedder output .json")
    parser.add_argument("--embed", action="store_true", help="embed units that have no embedding (shared embed/ model)")
    parser.add_argument("--dry-run", action="store_true", help="read and translate inputs; write nothing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s", stream=sys.stdout)

    registry = read_registry(args.registry) if args.registry else None
    docs = read_docs(args.docs) if args.docs else None
    chunks = read_json_list(args.chunks) if args.chunks else None
    units = read_json_list(args.units) if args.units else None
    if args.dry_run:
        for name, recs, fn in (("scrape_log", registry, scrape_log_row), ("documents", docs, document_row),
                               ("chunks", chunks, chunk_row), ("units", units, unit_row)):
            if recs is not None:
                rows = [fn(r) for r in recs]
                logger.info("DRY RUN %s: %s read, %s would load", name, len(rows), sum(r is not None for r in rows))
        return 0

    embed_fn = None
    if args.embed:
        from embed import embed_texts
        embed_fn = embed_texts
    from database.connection import connect
    with connect() as conn:
        counts = load(conn, registry, docs, chunks, units, embed_fn)
    for table, n in counts.items():
        logger.info("LOAD %s: %s", table, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
