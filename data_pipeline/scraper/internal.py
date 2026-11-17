"""Ingest internal (non-public) documents: markdown .txt files -> the same clean-doc format the
scraper writes, marked visibility "internal" so access control can filter them later.

Input folder ($INTERNAL_DIR):
  *.txt          markdown text (## headings); other file types are ignored
  metadata.csv   OPTIONAL, one row per file: file,title,category,sensitivity,owner,doc_date,notes
                 (overrides the file header; needed for files without a 'Knowledge category:' line)
  File header (lines before the first ## heading) may give: a title line, 'Knowledge category: ...',
  'Provenance: ...' and 'Tags: ...'. Sensitivity defaults to 'confidential' if not given.

Output ($INTERNAL_OUT): clean/<doc_id>.json and registry.jsonl, separate from public docs.

Safety: refuses to run if either folder is inside the repo but NOT gitignored, and logs only
file names, ids and counts, never document text.
"""
import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from data_pipeline.scraper import clean, config

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
BULLET = re.compile(r"^\s*[*+]\s+")
# The one committed input folder: invented sample data, so it's allowed to be tracked by git.
SYNTHETIC_DIR = Path("data/samples/synthetic_internal")
REGISTRY_COLUMNS = ["doc_id", "source_file", "title", "category", "sensitivity", "status", "reason",
                    "word_count", "content_sha256", "ingested_at", "clean_path"]


def doc_id_for(rel_path):
    """Stable id from the file's path inside the input folder (editing the file keeps its id)."""
    return "int_" + hashlib.sha256(rel_path.encode()).hexdigest()[:16]


def parse_markdown(text):
    """Markdown -> [{heading, level, text}]. '#' lines inside ``` code blocks are not headings."""
    sections, current, in_code = [], {"heading": None, "level": 0, "lines": []}, False
    for line in text.splitlines():
        if FENCE.match(line):
            in_code = not in_code
            current["lines"].append(line)
            continue
        m = None if in_code else HEADING.match(line)
        if m:
            if current["lines"] or current["heading"]:
                sections.append(current)
            current = {"heading": m.group(2), "level": len(m.group(1)), "lines": []}
        else:
            current["lines"].append(BULLET.sub("- ", line) if not in_code else line)
    if current["lines"] or current["heading"]:
        sections.append(current)
    return [{"heading": s["heading"], "level": s["level"], "text": "\n".join(s["lines"]).strip()}
            for s in sections]


def load_metadata(folder):
    path = folder / "metadata.csv"
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {row["file"].strip(): {k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)}


def check_not_tracked(*paths):
    """Abort if a folder sits inside this git repo without being gitignored."""
    for p in paths:
        p = Path(p).resolve()
        try:
            root = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                                       text=True, check=True).stdout.strip()).resolve()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return  # not in a git repo: nothing could be committed by accident
        if root not in p.parents and p != root:
            continue  # outside the repo (e.g. SCC project space)
        probe = p / "__probe__.txt"
        ignored = subprocess.run(["git", "check-ignore", "-q", str(probe)], cwd=root).returncode == 0
        if not ignored:
            raise SystemExit(f"Refusing to run: {p} is inside the repo and not gitignored. "
                             f"Internal data must never be committable.")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


HEADER_KEY = re.compile(r"^(knowledge category|provenance|tags)\s*:\s*(.+)$", re.I)
CONFIDENCE_TAG = re.compile(r"\[(IN TITLE|INFERRED|UNKNOWN)\]")
SHARED_SUFFIX = re.compile(r"\s*(\([^()]*\))\s*$")


def split_header(text):
    """Split a file into (header fields, body).

    The header is everything before the first markdown heading. Recognized lines:
      first line without '#'      -> title (e.g. an ALL-CAPS title line)
      Knowledge category: <name>  -> category (matched to 1 / 2 / 10)
      Provenance: <text>          -> provenance
      Tags: <text>                -> tag legend ([INFERRED] = ..., etc.)
    Any other header lines stay in the body as an untitled intro section.
    """
    lines = text.splitlines()
    first_heading = next((i for i, ln in enumerate(lines) if HEADING.match(ln)), len(lines))
    header, intro = {}, []
    for ln in lines[:first_heading]:
        stripped = ln.strip()
        if not stripped:
            continue
        m = HEADER_KEY.match(stripped)
        if m:
            header[m.group(1).lower().replace(" ", "_")] = m.group(2).strip()
        elif "title" not in header and not intro:
            header["title"] = stripped
        else:
            intro.append(ln)
    body = "\n".join(intro + [""] + lines[first_heading:])
    return header, body


def category_from_label(label):
    """'Segmentation and territory (SMB, ...)' -> 2, using the same names as the link file."""
    from data_pipeline.scraper.links import CATEGORY_BY_LABEL
    low = (label or "").strip().lower()
    for name, number in CATEGORY_BY_LABEL.items():
        if low.startswith(name):
            return number
    return None


def strip_shared_heading_suffix(sections):
    """If every heading ends with the same '(...)', e.g. '(Salesforce internal, Org62)', drop it
    from the headings and return it once, so headings read as their actual topic."""
    suffixes = {m.group(1) if (m := SHARED_SUFFIX.search(s["heading"])) else None
                for s in sections if s["heading"]}
    headed = [s for s in sections if s["heading"]]
    if len(headed) < 2 or len(suffixes) != 1 or None in suffixes:
        return sections, None
    suffix = suffixes.pop()
    return [s | {"heading": SHARED_SUFFIX.sub("", s["heading"])} if s["heading"] else s for s in sections], suffix


def ingest_file(path, rel, meta, seen_hashes):
    """One file -> (registry row, clean doc or None).

    Category, title and sensitivity come from metadata.csv when given, otherwise from the file's
    header. Sensitivity defaults to the most restrictive level ('confidential'), never to public.
    """
    meta = meta or {}
    doc_id = doc_id_for(rel)
    row = {"doc_id": doc_id, "source_file": rel, "title": None, "category": None, "sensitivity": None,
           "status": None, "reason": "", "word_count": None, "content_sha256": None,
           "ingested_at": _now(), "clean_path": None}

    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return row | {"status": "bad_encoding", "reason": "file is not UTF-8 text"}, None
    header, body = split_header(raw)

    if meta.get("category"):
        try:
            category = int(meta["category"])
        except ValueError:
            return row | {"status": "bad_metadata", "reason": f"category {meta['category']!r} is not a number"}, None
    elif header.get("knowledge_category"):
        category = category_from_label(header["knowledge_category"])
        if category is None:
            return row | {"status": "bad_metadata",
                          "reason": f"unknown 'Knowledge category: {header['knowledge_category'][:60]}'"}, None
    else:
        return row | {"status": "missing_metadata",
                      "reason": "no category in metadata.csv or a 'Knowledge category:' header line"}, None
    if category not in config.CATEGORY_NAMES:
        return row | {"status": "bad_metadata", "reason": f"unknown category {category}"}, None
    sensitivity = (meta.get("sensitivity") or "confidential").lower()
    if sensitivity not in config.INTERNAL_SENSITIVITY:
        return row | {"status": "bad_metadata",
                      "reason": f"sensitivity must be one of {config.INTERNAL_SENSITIVITY}"}, None

    sections, stats = clean.clean_sections(parse_markdown(body), web=False)
    first_h1 = next((s["heading"] for s in sections if s["level"] == 1 and s["heading"]), None)
    title = meta.get("title") or header.get("title") or first_h1 or path.stem
    # The file's top "# Title" heading is the doc title, not a section: don't repeat it.
    sections = [s | {"heading": None, "level": 0} if s["level"] == 1 and s["heading"] in (title, first_h1)
                and i == 0 else s for i, s in enumerate(sections)]
    sections = [s for s in sections if s["heading"] or s["text"]]
    sections, heading_suffix = strip_shared_heading_suffix(sections)
    text = clean.sections_to_text(title, sections)
    words = sum(len(s["text"].split()) for s in sections)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    row.update(title=title, category=category, sensitivity=sensitivity, word_count=words, content_sha256=sha)

    if words < config.INTERNAL_MIN_WORDS:
        return row | {"status": "too_short", "reason": f"{words} words < {config.INTERNAL_MIN_WORDS}"}, None
    if sha in seen_hashes:
        return row | {"status": "duplicate_content", "reason": f"same content as {seen_hashes[sha]}"}, None
    seen_hashes[sha] = doc_id

    tag_counts = {}
    for t in CONFIDENCE_TAG.findall(text):
        key = t.lower().replace(" ", "_")
        tag_counts[key] = tag_counts.get(key, 0) + 1

    doc = {
        "doc_id": doc_id, "url": None, "source_file": rel, "final_url": None, "canonical_url": None,
        "domain": None, "publisher": "Salesforce (internal)",
        "category": category, "category_name": config.CATEGORY_NAMES[category], "also_categories": [],
        "section_label": None, "title": title, "author": meta.get("owner") or None,
        "published_date": meta.get("doc_date") or None, "modified_date": None,
        "description": meta.get("notes") or None, "language": "en",
        # From the file header: where the data came from and what its [TAGS] mean. Extraction should
        # carry these through (e.g. an [INFERRED] line is not an official definition).
        "provenance": header.get("provenance"), "tag_legend": header.get("tags"),
        "confidence_tags": tag_counts, "heading_suffix": heading_suffix,
        "retrieved_at": row["ingested_at"], "fetch_method": "file", "extractor": "markdown",
        "content_type": "text/markdown", "word_count": words, "content_sha256": sha,
        "visibility": "internal", "sensitivity": sensitivity, "clean_stats": stats,
        "sections": sections, "text": text,
    }
    return row | {"status": "ok"}, doc


def ingest(in_dir=None, out_dir=None, log=print):
    in_dir = Path(in_dir or config.INTERNAL_DIR)
    if out_dir is None and in_dir.resolve() == SYNTHETIC_DIR.resolve():
        out_dir = config.INTERNAL_OUT.parent / "internal_synthetic"  # never mix with real internal docs
    out_dir = Path(out_dir or config.INTERNAL_OUT)
    if not in_dir.exists():
        raise SystemExit(f"{in_dir} not found. Set INTERNAL_DIR or create the folder.")
    if in_dir.resolve() == SYNTHETIC_DIR.resolve():
        check_not_tracked(out_dir)
    else:
        check_not_tracked(in_dir, out_dir)
    meta = load_metadata(in_dir)
    files = sorted(p for p in in_dir.rglob("*") if p.suffix.lower() == ".txt" and p.is_file())
    clean_dir = out_dir / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)

    rows, written, seen = [], set(), {}
    for p in files:
        rel = p.relative_to(in_dir).as_posix()
        row, doc = ingest_file(p, rel, meta.get(rel), seen)
        if doc:
            path = clean_dir / f"{doc['doc_id']}.json"
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
            row["clean_path"] = str(path)
            written.add(path.name)
        rows.append(row)
        reason = f" ({row['reason']})" if row["reason"] else ""
        log(f"[{row['status']}] {row['word_count'] or 0} words  {rel}{reason}")  # never log the text

    for unused in sorted(set(meta) - {r["source_file"] for r in rows}):
        log(f"[warning] metadata.csv lists {unused!r} but no such file was found")

    # Clean docs for files that were removed or now fail are deleted, so stale internal text never lingers.
    for stale in clean_dir.glob("*.json"):
        if stale.name not in written:
            stale.unlink()

    with (out_dir / "registry.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({c: r.get(c) for c in REGISTRY_COLUMNS}, ensure_ascii=False) + "\n")
    ok = sum(r["status"] == "ok" for r in rows)
    log(f"Ingested {ok}/{len(rows)} files from {in_dir} -> {clean_dir}")
    return rows
