"""Validate extracted knowledge units against JSON schemas, source chunks, and epistemic rules.

Run from the repository root:
    python3 -m data_pipeline.validator [units_path] [chunks_path] [output_path]
"""
import argparse
import json
import logging
from pathlib import Path
import re
import sys

from jsonschema import Draft202012Validator

logger = logging.getLogger(__name__)

DEFAULT_UNITS_PATH = Path("data/output/knowledge_units.json")
DEFAULT_CHUNKS_PATH = Path("data/output/chunks_semantic.json")
DEFAULT_VALIDATED_PATH = Path("data/output/knowledge_units_validated.json")
DEFAULT_REJECTED_PATH = Path("data/output/knowledge_units_rejected.json")

KU_SCHEMA_PATH = Path("schemas/knowledge_unit_schema.json")
META_SCHEMA_PATH = Path("schemas/metadata_schema.json")

RETAINED_LEVELS = {"know_how", "knowledge"}


def normalize_for_match(text):
    """Normalize curly quotes, dashes, and whitespace for substring verification."""
    if not text:
        return ""
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
    for src, target in replacements.items():
        text = text.replace(src, target)
    return " ".join(text.split())


def verify_quote_in_chunk(evidence_quote, chunk_text):
    """Check that evidence_quote (including '...' multi-span quotes) exists in chunk_text."""
    norm_quote = normalize_for_match(evidence_quote)
    norm_chunk = normalize_for_match(chunk_text)
    if not norm_quote or len(norm_quote) < 10:
        return False
    if norm_quote in norm_chunk:
        return True

    parts = [p.strip() for p in re.split(r"\.{3,}|\u2026", norm_quote) if p.strip()]
    if len(parts) > 1:
        cursor = 0
        for part in parts:
            if len(part) < 4:
                continue
            pos = norm_chunk.find(part, cursor)
            if pos == -1:
                return False
            cursor = pos + len(part)
        return True
    return False


def load_validators(ku_schema_path=KU_SCHEMA_PATH, meta_schema_path=META_SCHEMA_PATH):
    """Load Draft 2020-12 JSON Schema validators for units and metadata."""
    ku_schema = json.loads(Path(ku_schema_path).read_text(encoding="utf-8"))
    meta_schema = json.loads(Path(meta_schema_path).read_text(encoding="utf-8"))
    return Draft202012Validator(ku_schema), Draft202012Validator(meta_schema)


def validate_unit(unit, chunk_map, ku_validator, meta_validator):
    """Validate a single knowledge unit. Returns (is_valid, list_of_error_messages)."""
    errors = []

    for err in ku_validator.iter_errors(unit):
        loc = ".".join(str(p) for p in err.path) or "<root>"
        errors.append(f"knowledge_unit_schema [{loc}]: {err.message}")

    for err in meta_validator.iter_errors(unit):
        loc = ".".join(str(p) for p in err.path) or "<root>"
        errors.append(f"metadata_schema [{loc}]: {err.message}")

    level = unit.get("level")
    if level not in RETAINED_LEVELS:
        errors.append(f"retention_rule: level '{level}' must be dropped")

    if unit.get("is_obvious_to_layperson") is True:
        errors.append("epistemic_gate: unit flagged as is_obvious_to_layperson=True (common_sense)")

    if int(unit.get("specificity_score", 0)) < 3:
        errors.append(f"epistemic_gate: specificity_score {unit.get('specificity_score')} is below minimum threshold 3")

    if level == "know_how" and not unit.get("actionable_step"):
        errors.append("epistemic_gate: 'know_how' unit requires a non-empty actionable_step mechanism")

    if level == "knowledge" and not unit.get("outcome"):
        errors.append("epistemic_gate: 'knowledge' unit requires a non-null empirical/case outcome")

    chunk_id = unit.get("chunk_id")
    parent_chunk = chunk_map.get(chunk_id)
    if parent_chunk is None:
        errors.append(f"provenance: parent chunk_id '{chunk_id}' not found in chunks")
    else:
        if unit.get("source_url") != parent_chunk.get("source_url"):
            errors.append("provenance: source_url does not match parent chunk")
        if not verify_quote_in_chunk(unit.get("evidence_quote", ""), parent_chunk.get("text", "")):
            errors.append("grounding: evidence_quote not found verbatim in parent chunk text")

    return len(errors) == 0, errors


def validate_batch(units, chunks, ku_schema_path=KU_SCHEMA_PATH, meta_schema_path=META_SCHEMA_PATH):
    """Validate a list of units against schemas, epistemic gates, and parent chunks.

    Returns (valid_units, rejected_records).
    """
    ku_validator, meta_validator = load_validators(ku_schema_path, meta_schema_path)
    chunk_map = {c["chunk_id"]: c for c in chunks if "chunk_id" in c}

    valid_units = []
    rejected_records = []
    for unit in units:
        ok, errs = validate_unit(unit, chunk_map, ku_validator, meta_validator)
        if ok:
            valid_units.append(unit)
        else:
            logger.warning("REJECT %s: %s", unit.get("unit_id", "<unknown>"), "; ".join(errs))
            rejected_records.append({"unit": unit, "errors": errs})

    logger.info(
        "VALIDATE: %s/%s units passed validation (%s rejected)",
        len(valid_units),
        len(units),
        len(rejected_records),
    )
    return valid_units, rejected_records


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("units_path", nargs="?", default=str(DEFAULT_UNITS_PATH))
    parser.add_argument("chunks_path", nargs="?", default=str(DEFAULT_CHUNKS_PATH))
    parser.add_argument("output_path", nargs="?", default=str(DEFAULT_VALIDATED_PATH))
    parser.add_argument("--rejected-out", default=str(DEFAULT_REJECTED_PATH))
    args = parser.parse_args()

    units = json.loads(Path(args.units_path).read_text(encoding="utf-8"))
    chunks = json.loads(Path(args.chunks_path).read_text(encoding="utf-8"))

    valid_units, rejected = validate_batch(units, chunks)

    out_path = Path(args.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(valid_units, indent=2, ensure_ascii=False), encoding="utf-8")

    rej_path = Path(args.rejected_out)
    rej_path.parent.mkdir(parents=True, exist_ok=True)
    rej_path.write_text(json.dumps(rejected, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
