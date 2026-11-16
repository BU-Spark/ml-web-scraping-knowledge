"""Extract discrete, schema-bound knowledge units from semantic chunks using Claude.

Implements the Salesforce Unified Context Layer (UCL) Information Spectrum
with first-principles epistemic gating, source authority tiering, and
canonical claim hashing for multi-source corroboration.

Run from the repository root:
    python3 -m data_pipeline.extractor [input_chunks_path] [output_units_path]
"""
import argparse
from datetime import date
import hashlib
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

# Source Hierarchy & Authority Tiers
# Tier 1: Primary Institutional & Empirical Authorities (Salesforce/Trailhead, Gartner, HBR, McKinsey, Forrester)
TIER_1_DOMAINS = {
    "www.salesforce.com",
    "salesforce.com",
    "trailhead.salesforce.com",
    "engineering.salesforce.com",
    "hbr.org",
    "www.gartner.com",
    "www.mckinsey.com",
    "www.forrester.com",
}

# Tier 2: Vetted Sales Practitioner & Revenue Intelligence Benchmarks
TIER_2_DOMAINS = {
    "blog.hubspot.com",
    "www.hubspot.com",
    "www.gong.io",
    "www.outreach.io",
    "www.kornferry.com",
    "www.rain-group.com",
    "www.pavilion.com",
    "www.winningbydesign.com",
}

TIER_BASE_WEIGHTS = {
    1: 1.0,
    2: 0.8,
    3: 0.6,
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

# Phrases that indicate generic blog/e-book teasers ("content") or truisms ("common_sense")
PROMO_TEASER_PATTERNS = (
    r"\bin this e-book\b",
    r"\bdownload the e-book\b",
    r"\bin this chapter\b",
    r"\bover the next several weeks on the blog\b",
    r"\bturned these tips into an infographic\b",
    r"\bsee you on the trail\b",
    r"\byour journey through the sales process starts here\b",
)

COMMON_SENSE_PLATITUDE_PATTERNS = (
    r"^the sales process from prospect to close is (often )?full of",
    r"^don'?t interrupt (the |your )?(customer|prospect)",
    r"^follow up after a meeting\.?$",
    r"^build trust with (your )?(prospects|customers)\.?$",
    r"^listen to (your )?(prospects|customers)\.?$",
    r"^do your research\.?$",
    r"^set your (new )?customer up for success\.?$",
)

COMPANY_SIZE_ALIASES = (
    (r"\b(mom and pop|small business|smb|1-20|under 50)\b", "SMB (small business)"),
    (r"\b(esm|mid-market|mid market|emerging small|50-500|20-200)\b", "ESM / mid-market"),
    (r"\b(enterprise|fortune 500|50,?000|1,?000\+|large enterprise)\b", "Enterprise"),
)

EXTRACTION_TOOL_SCHEMA = {
    "name": "record_knowledge_units",
    "description": (
        "Record discrete sales knowledge units evaluated along the Salesforce "
        "UCL Information Spectrum (common_sense, content, know_how, knowledge)."
    ),
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
                        "actionable_step",
                        "evidence_quote",
                        "level",
                        "level_rationale",
                        "specificity_score",
                        "is_obvious_to_layperson",
                        "unit_type",
                        "context",
                        "outcome",
                        "topic",
                    ],
                    "properties": {
                        "claim": {
                            "type": "string",
                            "description": "One standalone, de-contextualized sentence stating the finding or practice.",
                        },
                        "actionable_step": {
                            "type": ["string", "null"],
                            "description": "Concrete operational mechanism or tactical move (how to execute). Null if pure statistic or if lacking a concrete mechanism.",
                        },
                        "evidence_quote": {
                            "type": "string",
                            "description": "Exact verbatim substring from the chunk (may join two spans with '...').",
                        },
                        "level": {
                            "type": "string",
                            "enum": list(VALID_LEVELS),
                        },
                        "level_rationale": {
                            "type": "string",
                            "description": "First-principles justification for the assigned level based on layperson obviousness, operational mechanism, and empirical outcome.",
                        },
                        "specificity_score": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 5,
                            "description": "1=platitude/truism, 2=textbook theory/teaser, 3=tactical mechanism, 4=contextualized workflow/stat, 5=case-proven outcome.",
                        },
                        "is_obvious_to_layperson": {
                            "type": "boolean",
                            "description": "True if an intelligent non-salesperson would already agree with this advice without training.",
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
                        "outcome": {
                            "type": ["string", "null"],
                            "description": "Explicitly measured result or quantitative benchmark in the text, or null.",
                        },
                        "topic": {
                            "type": ["string", "null"],
                            "description": "Short canonical topic label (e.g., 'BANT', 'lead qualification', 'objection handling').",
                        },
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
    if "forrester." in host:
        return "Forrester"
    if "gong.io" in host:
        return "Gong"
    if " - " in (page_title or ""):
        tail = page_title.rsplit(" - ", 1)[-1].strip()
        if tail and len(tail) <= 40:
            return tail
    return host.split(".")[0].capitalize() if host else "Unknown"


def infer_source_tier(domain):
    """Assign publisher trust tier (1 = Primary Authority, 2 = Vetted Practitioner, 3 = General Web)."""
    host = (domain or "").lower()
    bare = host.removeprefix("www.")
    if host in TIER_1_DOMAINS or bare in TIER_1_DOMAINS or bare.endswith(".salesforce.com"):
        return 1
    if host in TIER_2_DOMAINS or bare in TIER_2_DOMAINS:
        return 2
    return 3


def compute_authority_weight(source_tier, corroboration_count=1):
    """Compute bounded [0.0, 1.0] authority weight from source_tier and corroboration count."""
    base = TIER_BASE_WEIGHTS.get(int(source_tier), 0.6)
    bonus = min(0.15, 0.05 * max(0, int(corroboration_count) - 1))
    return round(min(1.0, base + bonus), 4)


def assign_category(raw_unit, chunk):
    """Deterministically assign Area 1, 2, or 10 based on content and model hint."""
    hint = (raw_unit.get("category_hint") or raw_unit.get("category") or "").strip()
    mapped = CATEGORIES.get(hint)

    combined = " ".join(
        filter(
            None,
            [
                raw_unit.get("claim", ""),
                raw_unit.get("actionable_step", "") or "",
                raw_unit.get("topic", "") or "",
                chunk.get("heading", ""),
            ],
        )
    ).lower()

    if any(kw in combined for kw in SEGMENTATION_KEYWORDS):
        return "2. Segmentation and Territory"
    if any(kw in combined for kw in ENABLEMENT_KEYWORDS):
        return "10. Enablement Operations"
    return mapped or "1. Sales Methodology and Process"


def normalize_company_size(val):
    """Normalize diverse company-size vocabulary (SMB, ESM, Enterprise) per UCL governance."""
    if not val or str(val).strip().lower() in ("unknown", "null", "none", "n/a", ""):
        return "unknown"
    clean = str(val).strip()
    lower = clean.lower()
    for pattern, canonical in COMPANY_SIZE_ALIASES:
        if re.search(pattern, lower):
            return canonical
    return clean


def normalize_context(raw_context):
    """Ensure context has all four required keys, normalizing vocabulary and defaulting missing to 'unknown'."""
    ctx = raw_context if isinstance(raw_context, dict) else {}
    out = {}
    for key in ("who", "industry", "company_size", "situation"):
        val = ctx.get(key)
        clean = str(val).strip() if val is not None else ""
        if not clean or clean.lower() in ("null", "none", "n/a", "unknown"):
            out[key] = "unknown"
        elif key == "company_size":
            out[key] = normalize_company_size(clean)
        else:
            out[key] = clean
    return out


def compute_canonical_claim_hash(category, topic, claim):
    """Generate a deterministic hash from category, normalized topic, and content words of claim."""
    stop_words = {
        "the", "a", "an", "to", "of", "in", "on", "for", "and", "or", "by", "with",
        "from", "at", "as", "is", "are", "be", "should", "must", "can", "their", "your",
    }
    words = re.findall(r"[a-z0-9]+", (claim or "").lower())
    core_words = [w for w in words if w not in stop_words][:12]
    norm_topic = re.sub(r"[^a-z0-9]+", "_", (topic or "general").lower()).strip("_")
    cat_prefix = (category or "1").split(".")[0].strip()
    payload = f"{cat_prefix}|{norm_topic}|{'_'.join(core_words)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def apply_epistemic_calibration(unit):
    """First-principles post-calibration of `level`, `specificity_score`, and `is_obvious_to_layperson`.

    Prevents prompt-only drift by enforcing structural invariants:
    1. Promotional / e-book chapter teasers -> downgraded to 'content'.
    2. Obvious layperson truisms or platitudes -> downgraded to 'common_sense'.
    3. 'know_how' without a concrete actionable_step -> downgraded to 'common_sense' or 'content'.
    4. 'knowledge' without an explicit outcome -> recalibrated to 'know_how' (if actionable) or 'content'.
    """
    claim_text = unit.get("claim", "")
    quote_text = unit.get("evidence_quote", "")
    combined_lower = f"{claim_text} {quote_text}".lower()

    # Rule 1: E-book / blog teaser detection
    if any(re.search(pat, combined_lower) for pat in PROMO_TEASER_PATTERNS):
        unit["level"] = "content"
        unit["specificity_score"] = min(unit.get("specificity_score", 2), 2)
        unit["level_rationale"] = (
            "Downgraded by epistemic gate: passage is a promotional or e-book chapter teaser rather than an operational tactic."
        )
        return unit

    # Rule 2: Explicit common-sense platitude patterns or layperson-obvious flag
    if unit.get("is_obvious_to_layperson") is True or any(
        re.search(pat, claim_text.strip().lower()) for pat in COMMON_SENSE_PLATITUDE_PATTERNS
    ):
        unit["is_obvious_to_layperson"] = True
        unit["level"] = "common_sense"
        unit["specificity_score"] = 1
        unit["level_rationale"] = (
            "Downgraded by epistemic gate: fails counterfactual layperson test (truism/platitude without non-obvious mechanism)."
        )
        return unit

    # Rule 3: Specificity floor check
    if unit.get("specificity_score", 3) < 3 and unit["level"] in RETAINED_LEVELS:
        unit["level"] = "common_sense" if unit.get("unit_type") == "how_to" else "content"
        unit["level_rationale"] = (
            f"Downgraded by epistemic gate: specificity_score={unit.get('specificity_score')} is below retention threshold (>=3)."
        )
        return unit

    # Rule 4: 'knowledge' requires a verified non-null outcome (metric, stat, or case result)
    if unit["level"] == "knowledge" and not unit.get("outcome"):
        if unit.get("actionable_step"):
            unit["level"] = "know_how"
            unit["level_rationale"] = (
                "Recalibrated from 'knowledge' to 'know_how': contains a concrete tactical mechanism but no measured empirical outcome."
            )
        else:
            unit["level"] = "content"
            unit["specificity_score"] = min(unit.get("specificity_score", 2), 2)
            unit["level_rationale"] = (
                "Downgraded from 'knowledge' to 'content': lacks both a measured outcome and a concrete actionable mechanism."
            )
        return unit

    # Rule 5: 'know_how' requires a concrete operational mechanism (actionable_step)
    if unit["level"] == "know_how" and not unit.get("actionable_step"):
        if unit.get("outcome") and unit.get("unit_type") in ("statistic", "example"):
            unit["level"] = "knowledge"
            unit["specificity_score"] = max(unit.get("specificity_score", 4), 4)
        else:
            unit["level"] = "common_sense"
            unit["specificity_score"] = 2
            unit["level_rationale"] = (
                "Downgraded from 'know_how' to 'common_sense': states a desirable goal without a concrete operational mechanism (actionable_step is null)."
            )

    return unit


def build_embed_text(unit):
    """Format claim, actionable mechanism, and non-unknown context into a single string for embedding."""
    parts = [unit["claim"].rstrip(".") + "."]
    if unit.get("actionable_step"):
        step = unit["actionable_step"].rstrip(".")
        if step.lower() not in unit["claim"].lower():
            parts.append(f"How-to: {step}.")
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


def _clean_nullable_str(val):
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("null", "none", "unknown", "n/a") else None


def enrich_unit(raw_unit, chunk, unit_index, extracted_at=None):
    """Combine model-extracted fields with code-populated provenance, tiering, and epistemic calibration."""
    chunk_id = chunk.get("chunk_id", f"chunk-{unit_index}")
    domain = chunk.get("domain") or re.sub(r"^https?://([^/]+).*$", r"\1", chunk.get("source_url", ""))
    page_title = chunk.get("page_title") or chunk.get("heading") or chunk.get("source_url", "Untitled")
    section_id = chunk.get("section_id", 0)
    char_start = chunk.get("start", chunk.get("char_start"))
    char_end = chunk.get("end", chunk.get("char_end"))

    outcome = _clean_nullable_str(raw_unit.get("outcome"))
    topic = _clean_nullable_str(raw_unit.get("topic"))
    actionable_step = _clean_nullable_str(raw_unit.get("actionable_step"))

    # Default sensible actionable_step for backwards-compatible mocks if how_to + know_how
    claim_str = str(raw_unit.get("claim", "")).strip()
    raw_level = str(raw_unit.get("level", "content")).strip().lower()
    if actionable_step is None and raw_level == "know_how" and len(claim_str) >= 25:
        actionable_step = claim_str

    raw_spec = raw_unit.get("specificity_score")
    if isinstance(raw_spec, int) and 1 <= raw_spec <= 5:
        specificity_score = raw_spec
    else:
        specificity_score = 4 if raw_level == "knowledge" else (3 if raw_level == "know_how" else 1)

    is_obvious = bool(raw_unit.get("is_obvious_to_layperson", raw_level == "common_sense"))
    rationale = str(
        raw_unit.get("level_rationale")
        or f"Classified as {raw_level} based on specificity_score={specificity_score} and operational grounding."
    ).strip()

    category = assign_category(raw_unit, chunk)
    publisher = infer_publisher(domain, page_title)
    source_tier = infer_source_tier(domain)
    evidence_quote = str(raw_unit.get("evidence_quote", "")).strip()

    unit = {
        "unit_id": f"ku-{chunk_id}-{unit_index}",
        "chunk_id": chunk_id,
        "section_id": int(section_id),
        "claim": claim_str,
        "actionable_step": actionable_step,
        "evidence_quote": evidence_quote,
        "level": raw_level,
        "level_rationale": rationale,
        "specificity_score": specificity_score,
        "is_obvious_to_layperson": is_obvious,
        "unit_type": str(raw_unit.get("unit_type", "how_to")).strip().lower(),
        "context": normalize_context(raw_unit.get("context")),
        "outcome": outcome,
        "topic": topic,
        "category": category,
        "source_url": chunk["source_url"],
        "domain": domain,
        "publisher": publisher,
        "published_date": chunk.get("published_date"),
        "page_title": page_title,
        "heading": chunk.get("heading", ""),
        "char_start": char_start,
        "char_end": char_end,
        "source_type": "external",
        "sensitivity": "public",
        "source_tier": source_tier,
        "authority_weight": compute_authority_weight(source_tier, corroboration_count=1),
        "canonical_claim_hash": compute_canonical_claim_hash(category, topic, claim_str),
        "corroborating_sources": [
            {
                "source_url": chunk["source_url"],
                "publisher": publisher,
                "source_tier": source_tier,
                "evidence_quote": evidence_quote,
                "chunk_id": chunk_id,
            }
        ],
        "corroboration_count": 1,
        "extracted_at": extracted_at or date.today().isoformat(),
        "embed_text": "",
        "embedding": None,
    }

    unit = apply_epistemic_calibration(unit)
    unit["embed_text"] = build_embed_text(unit)
    return unit


def should_retain(unit):
    """Retention rule: keep know_how and knowledge (with specificity >= 3 and non-obvious); drop common_sense and content."""
    return (
        unit.get("level") in RETAINED_LEVELS
        and not unit.get("is_obvious_to_layperson", False)
        and int(unit.get("specificity_score", 0)) >= 3
    )


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
        max_tokens=2500,
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
    know_how and knowledge units passing first-principles epistemic gates.
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
                logger.info(
                    "DROP: unit %s dropped (level=%s, specificity=%s, obvious=%s)",
                    enriched["unit_id"],
                    enriched["level"],
                    enriched["specificity_score"],
                    enriched["is_obvious_to_layperson"],
                )

    logger.info(
        "SUMMARY: extracted %s total candidate units from %s chunks; retained %s (know_how/knowledge), dropped %s",
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
