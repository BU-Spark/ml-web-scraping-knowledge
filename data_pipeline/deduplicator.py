"""Deduplicate and corroborate knowledge units across multiple sources while preserving context.

Answers the client's source-hierarchy and vector-clustering requirement:
1. When multiple sources express the same claim within the SAME context
   (who, industry, company_size, situation), they are consolidated into a
   single canonical knowledge unit anchored by the highest-authority source
   (Tier 1 > Tier 2 > Tier 3, e.g., Salesforce prepends mainstream sources).
2. All corroborating URLs, publishers, tiers, and verbatim quotes are
   compiled in `corroborating_sources`, incrementing `corroboration_count`
   and boosting `authority_weight` for downstream pgvector retrieval.
3. When two units share a topic/claim but apply to DIFFERENT contexts
   (e.g., SMB vs. Enterprise), both units are preserved as separate vectors
   so context-specific nuance is never flattened.

Run from the repository root:
    python3 -m data_pipeline.deduplicator [input_units_path] [output_units_path]
"""
import argparse
from difflib import SequenceMatcher
import json
import logging
from pathlib import Path
import re
import sys

from data_pipeline.extractor import build_embed_text, compute_authority_weight

logger = logging.getLogger(__name__)

DEFAULT_IN_PATH = Path("data/output/knowledge_units_validated.json")
DEFAULT_OUT_PATH = Path("data/output/knowledge_units_deduped.json")

SIMILARITY_THRESHOLD = 0.82


def _norm_text(text):
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def contexts_are_compatible(ctx_a, ctx_b):
    """Return True if two context dicts have identical normalized values (preserving distinct contexts)."""
    for key in ("who", "industry", "company_size", "situation"):
        val_a = (ctx_a or {}).get(key, "unknown").strip().lower()
        val_b = (ctx_b or {}).get(key, "unknown").strip().lower()
        if val_a != val_b:
            return False
    return True


def claims_are_equivalent(unit_a, unit_b, threshold=SIMILARITY_THRESHOLD):
    """Check whether two units in the same category and compatible context express the same claim."""
    if unit_a.get("category") != unit_b.get("category"):
        return False
    if not contexts_are_compatible(unit_a.get("context"), unit_b.get("context")):
        return False
    if unit_a.get("canonical_claim_hash") and unit_a.get("canonical_claim_hash") == unit_b.get("canonical_claim_hash"):
        return True

    norm_a = _norm_text(unit_a.get("claim", ""))
    norm_b = _norm_text(unit_b.get("claim", ""))
    if not norm_a or not norm_b:
        return False
    ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
    return ratio >= threshold


def _unit_priority_key(unit):
    """Sort key so Tier 1 (Salesforce first) + 'knowledge' level + higher specificity wins canonical anchor."""
    tier = int(unit.get("source_tier", 3))
    is_salesforce = 0 if unit.get("publisher", "").lower() == "salesforce" else 1
    level_rank = 0 if unit.get("level") == "knowledge" else 1
    spec_rank = -int(unit.get("specificity_score", 3))
    return (tier, is_salesforce, level_rank, spec_rank)


def merge_cluster(cluster):
    """Merge a cluster of corroborating units into the highest-authority canonical unit."""
    ordered = sorted(cluster, key=_unit_priority_key)
    primary = dict(ordered[0])

    seen_sources = set()
    corroborating = []
    for item in ordered:
        for src in item.get("corroborating_sources", []) or [
            {
                "source_url": item["source_url"],
                "publisher": item.get("publisher", "Unknown"),
                "source_tier": item.get("source_tier", 3),
                "evidence_quote": item.get("evidence_quote", ""),
                "chunk_id": item.get("chunk_id", ""),
            }
        ]:
            key = (src.get("source_url"), src.get("evidence_quote"))
            if key not in seen_sources:
                seen_sources.add(key)
                corroborating.append(src)

    # Sort corroborating sources by tier (Tier 1 first, Salesforce first)
    corroborating.sort(
        key=lambda s: (
            int(s.get("source_tier", 3)),
            0 if str(s.get("publisher", "")).lower() == "salesforce" else 1,
        )
    )

    unique_urls = {s.get("source_url") for s in corroborating if s.get("source_url")}
    corroboration_count = max(1, len(unique_urls))

    primary["corroborating_sources"] = corroborating
    primary["corroboration_count"] = corroboration_count
    primary["authority_weight"] = compute_authority_weight(
        primary["source_tier"], corroboration_count=corroboration_count
    )
    primary["embed_text"] = build_embed_text(primary)
    return primary


def deduplicate_units(units, threshold=SIMILARITY_THRESHOLD):
    """Cluster equivalent units with identical contexts and merge them by source authority hierarchy."""
    clusters = []
    for unit in units:
        placed = False
        for cluster in clusters:
            if claims_are_equivalent(unit, cluster[0], threshold=threshold):
                cluster.append(unit)
                placed = True
                break
        if not placed:
            clusters.append([unit])

    deduped = [merge_cluster(c) for c in clusters]
    logger.info(
        "DEDUP: consolidated %s input units into %s canonical units (%s duplicates merged into corroborating_sources)",
        len(units),
        len(deduped),
        len(units) - len(deduped),
    )
    return deduped


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", nargs="?", default=str(DEFAULT_IN_PATH))
    parser.add_argument("output_path", nargs="?", default=str(DEFAULT_OUT_PATH))
    parser.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD)
    args = parser.parse_args()

    units = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
    deduped = deduplicate_units(units, threshold=args.threshold)

    out_path = Path(args.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(deduped, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("SAVE: wrote %s deduplicated units to %s", len(deduped), out_path)


if __name__ == "__main__":
    main()
