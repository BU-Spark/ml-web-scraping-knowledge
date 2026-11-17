"""SEC filings (sec.gov): keep only the part that describes the business, and recover its headings.

A 10-K or 20-F is 60k-120k words; for us only the business description matters (how the company
sells, its segments and customers). EDGAR pages use styled divs instead of <h> tags, so headings
come through as short plain lines; we turn those back into headings.

  10-K: "ITEM 1. BUSINESS"                       up to "ITEM 1A."
  20-F: "ITEM 4. INFORMATION ON/ABOUT <company>" up to "ITEM 4A."
The table of contents lists the same items, so we take the longest start->end span.
"""
import re

PARTS = [
    (re.compile(r"^item\s*1\.\s*business\b", re.I), re.compile(r"^item\s*1a\.", re.I), "Item 1. Business"),
    (re.compile(r"^item\s*4\.\s*information (on|about)\b", re.I), re.compile(r"^item\s*4a\.", re.I),
     "Item 4. Information on the Company"),
]
BULLETS = ("•", "●", "◦", "▪", "- ")


def _find_span(lines):
    for start_re, end_re, name in PARTS:
        best = None
        for i, line in enumerate(lines):
            if start_re.match(line):
                end = next((j for j in range(i + 1, len(lines)) if end_re.match(lines[j])), None)
                if end is not None and (best is None or end - i > best[1] - best[0]):
                    best = (i, end)
        if best:
            return best, name
    return None, None


def _looks_like_heading(line):
    s = line.strip()
    return (len(s) < 70 and s[:1].isupper() and not s.startswith(BULLETS) and "|" not in s
            and not s.endswith((".", ":", ";", ",")))


def business_sections(sections):
    """Returns (sections, note). If no business item is found, returns the input unchanged."""
    lines = [ln for s in sections for ln in s["text"].split("\n")]
    span, name = _find_span(lines)
    if not span:
        return sections, "sec: business item not found; kept whole filing"
    body = lines[span[0] + 1:span[1]]
    out = []
    current = {"heading": name, "level": 2, "lines": []}
    for ln in body:
        if _looks_like_heading(ln):
            if current["lines"]:
                out.append(current)
            current = {"heading": ln.strip(), "level": 3, "lines": []}
        else:
            current["lines"].append(("- " + ln.lstrip("•●◦▪ ").strip()) if ln.startswith(BULLETS[:4]) else ln)
    if current["lines"]:
        out.append(current)
    result = [{"heading": s["heading"], "level": s["level"], "text": "\n".join(s["lines"])} for s in out]
    return result, f"sec: kept {name} ({len(body)} of {len(lines)} lines)"
