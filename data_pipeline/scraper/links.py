"""Parse the compiled link file into a manifest: one row per URL with its category and section label.

File format (data/urls/public_urls_compiled.txt):
  # Knowledge category 1: ...        -> starts category 1   (likewise category 2)
  # Enablement operations: ...       -> starts category 10
  # Some label (7)                   -> sub-section label (ends with a count in brackets)
  # === Some label (24) ===          -> sub-section label, category 10 style
  https://...                        -> a URL
  # Also tagged for Segmentation and territory: <note>   -> applies to the URL just above
Every other '#' line is a comment and ignored.
"""
import hashlib
import json
import re
from collections import Counter
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from data_pipeline.scraper import config

CATEGORY_HEADER = re.compile(r"^#\s*Knowledge category (\d+)\s*:")
ENABLEMENT_HEADER = re.compile(r"^#\s*Enablement operations\b", re.I)
SECTION_LABEL = re.compile(r"^#\s*(?:===\s*)?(.+?)\s*\((\d+)\)\s*(?:===)?\s*$")
ALSO_TAGGED = re.compile(r"^#\s*Also tagged for (.+?):", re.I)

# Names used in "Also tagged for <name>:" lines -> category number.
CATEGORY_BY_LABEL = {
    "sales methodology and process": 1,
    "segmentation and territory": 2,
    "enablement operations": 10,
}


def normalize_url(url):
    """Stable form of a URL: lowercase scheme/host, no fragment, no tracking params, no trailing slash."""
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def doc_id_for(url_normalized):
    """First 16 hex chars of sha256(normalized URL): same URL -> same id on every run."""
    return hashlib.sha256(url_normalized.encode()).hexdigest()[:16]


def domain_of(url):
    host = urlsplit(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def parse_link_file(text):
    """Return manifest rows (dicts) in file order. Raises ValueError on a URL before any category."""
    rows = []
    category = None
    label = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if m := CATEGORY_HEADER.match(line):
                category, label = int(m.group(1)), None
            elif ENABLEMENT_HEADER.match(line):
                category, label = 10, None
            elif m := ALSO_TAGGED.match(line):
                extra = CATEGORY_BY_LABEL.get(m.group(1).strip().lower())
                if extra is None:
                    raise ValueError(f"line {lineno}: unknown category name in {line!r}")
                if rows and extra != rows[-1]["category"] and extra not in rows[-1]["also_categories"]:
                    rows[-1]["also_categories"].append(extra)
            elif category is not None and (m := SECTION_LABEL.match(line)):
                label = m.group(1).strip()
            continue
        if not line.lower().startswith(("http://", "https://")):
            continue  # stray text; not a URL
        if category is None:
            raise ValueError(f"line {lineno}: URL appears before any category header")
        norm = normalize_url(line)
        rows.append({
            "doc_id": doc_id_for(norm),
            "url": line,
            "url_normalized": norm,
            "domain": domain_of(line),
            "category": category,
            "category_name": config.CATEGORY_NAMES.get(category, f"category_{category}"),
            "section_label": label,
            "also_categories": [],
            "source_line": lineno,
        })
    return rows


def write_manifest(rows, path=None):
    path = path or config.MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_manifest(path=None):
    path = path or config.MANIFEST
    if not path.exists():
        raise SystemExit(f"{path} not found. Run: python3 -m data_pipeline.scraper parse")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_counts(rows):
    """Compare per-category counts with the expected ones. Returns a list of problems (empty = OK)."""
    problems = []
    counts = Counter(r["category"] for r in rows)
    for cat, expected in config.EXPECTED_COUNTS.items():
        if counts.get(cat, 0) != expected:
            problems.append(f"category {cat}: found {counts.get(cat, 0)}, expected {expected}")
    dupes = [u for u, n in Counter(r["url_normalized"] for r in rows).items() if n > 1]
    if dupes:
        problems.append(f"{len(dupes)} duplicate URLs after normalizing, e.g. {dupes[0]}")
    return problems
