"""Tidy extracted sections: normalize unicode/whitespace, drop leftover boilerplate lines and
sections, and drop lines repeated many times on the same page.

Conservative: only short lines that match a known pattern are removed.
"""
import re
import unicodedata
from collections import Counter

from data_pipeline.scraper import config


def normalize(text):
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"[ \t ]+", " ", text).strip()


def is_boilerplate_line(line):
    low = line.lower()
    return len(line) < config.MAX_BOILERPLATE_LEN and any(p in low for p in config.BOILERPLATE_LINE_PATTERNS)


def is_boilerplate_heading(heading):
    low = (heading or "").lower()
    return bool(low) and len(low) < 80 and any(p in low for p in config.BOILERPLATE_HEADING_PATTERNS)


def is_teaser(text):
    """A related-post card: one short line that trails off ('...'), e.g. a blog excerpt."""
    return "\n" not in text and len(text) < 400 and text.rstrip().endswith(("...", "\u2026"))


def clean_sections(sections, web=True):
    """Returns (cleaned sections, stats dict). Sections left with no text are dropped.

    web=False (internal documents) only normalizes text and drops repeated lines: the
    web clutter rules (CTAs, teasers, tab navigation) would remove real content there."""
    stats = Counter()
    norm = []
    for s in sections:
        if web and is_boilerplate_heading(s["heading"]):
            stats["boilerplate_sections"] += 1
            continue
        lines = [normalize(ln) for ln in s["text"].split("\n")]
        norm.append({**s, "heading": normalize(s["heading"]) if s["heading"] else None,
                     "lines": [ln for ln in lines if ln]})

    # Tab/accordion navigation: list items that just repeat a heading on the same page.
    headings = {s["heading"].lower() for s in norm if s["heading"]}
    counts = Counter(ln for s in norm for ln in s["lines"])
    seen = set()
    out = []
    for s in norm:
        kept = []
        for ln in s["lines"]:
            if web and is_boilerplate_line(ln):
                stats["boilerplate_lines"] += 1
                continue
            if web and ln.startswith("- ") and ln[2:].lower() in headings:
                stats["nav_lines"] += 1
                continue
            if counts[ln] > config.MAX_REPEATS and ln in seen:
                stats["repeated_lines"] += 1
                continue
            seen.add(ln)
            kept.append(ln)
        if web and kept and is_teaser("\n".join(kept)) and s["heading"]:
            stats["teaser_sections"] += 1
            continue
        if kept:
            out.append({"heading": s["heading"], "level": s["level"], "text": "\n".join(kept)})
        else:
            stats["empty_sections"] += 1
    return out, dict(stats)


def sections_to_text(title, sections):
    """Markdown-ish full text: '# Title' then '## Heading' lines (level-matched) and bodies."""
    parts = [f"# {title}"] if title else []
    for s in sections:
        if s["heading"]:
            parts.append("#" * max(2, min(s["level"], 6)) + " " + s["heading"])
        parts.append(s["text"])
    return "\n\n".join(parts)
