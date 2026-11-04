"""Extract discrete, schema-bound knowledge units from semantic chunks using Claude.

Run from the repository root:
    python3 -m data_pipeline.extractor [input_chunks_path] [output_units_path]
"""
import argparse
from datetime import date
import json
import logging
import os
from pathlib import Path
import re
import sys

logger = logging.getLogger(__name__)

DEFAULT_IN_PATH = Path("data/output/chunks_semantic.json")
DEFAULT_OUT_PATH = Path("data/output/knowledge_units.json")
DEFAULT_RAW_OUT_PATH = Path("data/output/knowledge_units_all_levels.json")

EXTRACTION_PROMPT_PATH = Path("prompts/extraction_prompt.txt")
CLASSIFICATION_PROMPT_PATH = Path("prompts/classification_prompt.txt")

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

VALID_LEVELS = ("common_sense", "content", "know_how", "knowledge")
RETAINED_LEVELS = {"know_how", "knowledge"}
VALID_UNIT_TYPES = ("how_to", "definition", "statistic", "example")

CATEGORIES = {
    "1": "1. Sales Methodology and Process",
    "2": "2. Segmentation and Territory",
    "10": "10. Enablement Operations",
    "1. Sales Methodology and Process": "1. Sales Methodology and Process",
    "2. Segmentation and Territory": "2. Segmentation and Territory",
    "10. Enablement Operations": "10. Enablement Operations",
    "10. Enablement operations": "10. Enablement Operations",
}

TIER_1_DOMAINS = {
    "www.salesforce.com",
    "salesforce.com",
    "hbr.org",
    "www.gartner.com",
    "www.mckinsey.com",
    "www.forrester.com",
}

TIER_2_DOMAINS = {
    "blog.hubspot.com",
    "www.hubspot.com",
    "www.gong.io",
    "www.outreach.io",
    "www.kornferry.com",
    "www.rain-group.com",
}

SEGMENTATION_KEYWORDS = (
    "territory",
    "segmentation",
    "icp",
    "ideal customer profile",
    "account tier",
    "tam",
    "market segment",
    "quota allocation",
)

ENABLEMENT_KEYWORDS = (
    "enablement",
    "ramp time",
    "call coaching",
    "call review",
    "onboarding",
    "sales training",
    "playbook",
    "configure price quote",
    "cpq",
    "crm",
    "customer relationship management",
    "kpi",
)

EXTRACTION_TOOL_SCHEMA = {
    "name": "record_knowledge_units",
    "description": "Record discrete sales knowledge units extracted from the chunk.",
    "input_schema": {
        "type": "object",
        "required": ["units"],
        "properties": {
            "units": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "claim",
                        "evidence_quote",
                        "level",
                        "unit_type",
                        "context",
                        "outcome",
                        "topic",
                    ],
                    "properties": {
                        "claim": {"type": "string"},
                        "evidence_quote": {"type": "string"},
                        "level": {
                            "type": "string",
                            "enum": list(VALID_LEVELS),
                        },
                        "unit_type": {
                            "type": "string",
                            "enum": list(VALID_UNIT_TYPES),
                        },
                        "context": {
                            "type": "object",
                            "required": ["who", "industry", "company_size", "situation"],
                            "properties": {
                                "who": {"type": "string"},
                                "industry": {"type": "string"},
                                "company_size": {"type": "string"},
                                "situation": {"type": "string"},
                            },
                        },
                        "outcome": {"type": ["string", "null"]},
                        "topic": {"type": ["string", "null"]},
                        "category_hint": {
                            "type": "string",
                            "enum": [
                                "1. Sales Methodology and Process",
                                "2. Segmentation and Territory",
                                "10. Enablement Operations",
                            ],
                        },
                    },
                },
            }
        },
    },
}


def load_prompt(path):
    """Read a prompt file and verify it is not an unimplemented placeholder."""
    text = Path(path).read_text(encoding="utf-8").strip()
    if text.startswith("NOT IMPLEMENTED"):
        raise RuntimeError(f"Prompt file is still a placeholder: {path}")
    return text


def infer_publisher(domain, page_title=""):
    """Derive clean publisher name from domain or page title."""
    host = (domain or "").lower().removeprefix("www.")
    if "salesforce." in host:
        return "Salesforce"
    if "hubspot." in host:
        return "HubSpot"
    if "gartner." in host:
        return "Gartner"
    if "hbr.org" in host:
        return "Harvard Business Review"
    if "mckinsey." in host:
        return "McKinsey & Company"
    if " - " in (page_title or ""):
        tail = page_title.rsplit(" - ", 1)[-1].strip()
        if tail and len(tail) <= 40:
            return tail
    return host.split(".")[0].capitalize() if host else "Unknown"


def infer_source_tier(domain):
    """Assign publisher trust tier (1 = highest, 3 = general external)."""
    host = (domain or "").lower()
    if host in TIER_1_DOMAINS or host.removeprefix("www.") in TIER_1_DOMAINS:
        return 1
    if host in TIER_2_DOMAINS or host.removeprefix("www.") in TIER_2_DOMAINS:
        return 2
    return 3


def assign_category(raw_unit, chunk):
    """Deterministically assign Area 1, 2, or 10 based on content and model hint."""
    hint = (raw_unit.get("category_hint") or raw_unit.get("category") or "").strip()
    if hint in CATEGORIES:
        mapped = CATEGORIES[hint]
    else:
        mapped = None

    combined = " ".join(
        filter(
            None,
            [
                raw_unit.get("claim", ""),
                raw_unit.get("topic", ""),
                chunk.get("heading", ""),
            ],
        )
    ).lower()

    if any(kw in combined for kw in SEGMENTATION_KEYWORDS):
        return "2. Segmentation and Territory"
    if any(kw in combined for kw in ENABLEMENT_KEYWORDS):
        return "10. Enablement Operations"
    return mapped or "1. Sales Methodology and Process"


def normalize_context(raw_context):
    """Ensure context has all four required keys, defaulting empty values to 'unknown'."""
    ctx = raw_context if isinstance(raw_context, dict) else {}
    out = {}
    for key in ("who", "industry", "company_size", "situation"):
        val = ctx.get(key)
        clean = str(val).strip() if val is not None else ""
        out[key] = clean if clean and clean.lower() not in ("null", "none", "n/a") else "unknown"
    return out


def build_embed_text(unit):
    """Format claim and non-unknown context into a single string for embedding."""
    parts = [unit["claim"].rstrip(".") + "."]
    if unit.get("topic"):
        parts.append(f"Topic: {unit['topic']}.")
    if unit.get("category"):
        parts.append(f"Category: {unit['category']}.")

    ctx = unit.get("context", {})
    ctx_bits = [
        f"{k}={ctx[k]}"
        for k in ("who", "industry", "company_size", "situation")
        if ctx.get(k) and ctx[k].lower() != "unknown"
    ]
    if ctx_bits:
        parts.append("Context: " + ", ".join(ctx_bits) + ".")
    if unit.get("outcome"):
        parts.append(f"Outcome: {unit['outcome']}.")
    return " ".join(parts)


def enrich_unit(raw_unit, chunk, unit_index, extracted_at=None):
    """Combine model-extracted fields with code-populated provenance fields."""
    chunk_id = chunk.get("chunk_id", f"chunk-{unit_index}")
    domain = chunk.get("domain") or re.sub(r"^https?://([^/]+).*$", r"\1", chunk.get("source_url", ""))
    page_title = chunk.get("page_title") or chunk.get("heading") or chunk.get("source_url", "Untitled")
    section_id = chunk.get("section_index", chunk.get("section_id", 0))
    char_start = chunk.get("start", chunk.get("char_start"))
    char_end = chunk.get("end", chunk.get("char_end"))

    outcome_raw = raw_unit.get("outcome")
    outcome = (
        str(outcome_raw).strip()
        if outcome_raw and str(outcome_raw).strip().lower() not in ("null", "none", "unknown", "n/a")
        else None
    )

    topic_raw = raw_unit.get("topic")
    topic = (
        str(topic_raw).strip()
        if topic_raw and str(topic_raw).strip().lower() not in ("null", "none", "unknown", "n/a")
        else None
    )

    unit = {
        "unit_id": f"ku-{chunk_id}-{unit_index}",
        "chunk_id": chunk_id,
        "section_id": int(section_id),
        "claim": str(raw_unit.get("claim", "")).strip(),
        "evidence_quote": str(raw_unit.get("evidence_quote", "")).strip(),
        "level": str(raw_unit.get("level", "content")).strip().lower(),
        "unit_type": str(raw_unit.get("unit_type", "how_to")).strip().lower(),
        "context": normalize_context(raw_unit.get("context")),
        "outcome": outcome,
        "topic": topic,
        "category": assign_category(raw_unit, chunk),
        "source_url": chunk["source_url"],
        "domain": domain,
        "publisher": infer_publisher(domain, page_title),
        "published_date": chunk.get("published_date"),
        "page_title": page_title,
        "heading": chunk.get("heading", ""),
        "char_start": char_start,
        "char_end": char_end,
        "source_type": "external",
        "sensitivity": "public",
        "source_tier": infer_source_tier(domain),
        "extracted_at": extracted_at or date.today().isoformat(),
        "embed_text": "",
        "embedding": None,
    }
    unit["embed_text"] = build_embed_text(unit)
    return unit


def should_retain(unit):
    """Retention rule: keep know_how and knowledge; drop common_sense and content."""
    return unit.get("level") in RETAINED_LEVELS


def format_chunk_user_message(chunk):
    """Build the user message payload sent to Claude for a single chunk."""
    return (
        f"SOURCE URL: {chunk.get('source_url', '')}\n"
        f"PAGE TITLE: {chunk.get('page_title', '')}\n"
        f"SECTION HEADING: {chunk.get('heading', '')}\n"
        f"CHUNK ID: {chunk.get('chunk_id', '')}\n\n"
        f"CHUNK TEXT:\n{chunk.get('text', '')}"
    )


def call_claude_on_chunk(chunk, system_prompt, client, model=DEFAULT_MODEL):
    """Call Anthropic Claude with forced tool-use to extract structured units."""
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=0.0,
        system=system_prompt,
        tools=[EXTRACTION_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "record_knowledge_units"},
        messages=[{"role": "user", "content": format_chunk_user_message(chunk)}],
    )
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "record_knowledge_units":
            payload = getattr(block, "input", {}) or {}
            return payload.get("units", [])
        if isinstance(block, dict) and block.get("type") == "tool_use":
            return (block.get("input") or {}).get("units", [])
    return []


def extract_from_chunks(chunks, llm_fn=None, client=None, model=DEFAULT_MODEL, extracted_at=None):
    """Extract knowledge units across a list of chunks.

    Returns (retained_units, all_units) where retained_units contains only
    know_how and knowledge units per Schema v0.1 retention rules.
    """
    extraction_instructions = load_prompt(EXTRACTION_PROMPT_PATH)
    classification_instructions = load_prompt(CLASSIFICATION_PROMPT_PATH)
    system_prompt = f"{extraction_instructions}\n\n{classification_instructions}"

    if llm_fn is None:
        if client is None:
            from anthropic import Anthropic

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY environment variable is required.")
            client = Anthropic(api_key=api_key)
        llm_fn = lambda ch: call_claude_on_chunk(ch, system_prompt, client=client, model=model)

    all_units = []
    retained_units = []
    stamp = extracted_at or date.today().isoformat()

    for idx, chunk in enumerate(chunks, 1):
        chunk_id = chunk.get("chunk_id", f"idx-{idx}")
        logger.info("EXTRACT: chunk %s/%s (%s - %s)", idx, len(chunks), chunk_id, chunk.get("heading", ""))
        raw_list = llm_fn(chunk) or []
        for u_idx, raw_unit in enumerate(raw_list):
            enriched = enrich_unit(raw_unit, chunk, u_idx, extracted_at=stamp)
            all_units.append(enriched)
            if should_retain(enriched):
                retained_units.append(enriched)
            else:
                logger.info("DROP: unit %s dropped due to level=%s", enriched["unit_id"], enriched["level"])

    logger.info(
        "SUMMARY: extracted %s total units from %s chunks; retained %s (know_how/knowledge), dropped %s",
        len(all_units),
        len(chunks),
        len(retained_units),
        len(all_units) - len(retained_units),
    )
    return retained_units, all_units


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", nargs="?", default=str(DEFAULT_IN_PATH))
    parser.add_argument("output_path", nargs="?", default=str(DEFAULT_OUT_PATH))
    parser.add_argument("--all-levels-out", default=str(DEFAULT_RAW_OUT_PATH))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    in_path = Path(args.input_path)
    if not in_path.exists():
        logger.error("Input chunks file not found: %s", in_path)
        sys.exit(1)

    chunks = json.loads(in_path.read_text(encoding="utf-8"))
    retained, all_units = extract_from_chunks(chunks, model=args.model)

    out_path = Path(args.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(retained, indent=2, ensure_ascii=False), encoding="utf-8")

    raw_out = Path(args.all_levels_out)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    raw_out.write_text(json.dumps(all_units, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("SAVE: wrote %s retained units to %s", len(retained), out_path)


if __name__ == "__main__":
    main()
