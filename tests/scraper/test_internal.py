"""Internal ingest: markdown .txt + metadata.csv -> clean docs marked internal. Uses tmp folders only."""
import json

import pytest

from scraper import internal

META = "file,title,category,sensitivity,owner,doc_date,notes\n"
BODY = """# Routing rules

Intro paragraph about routing that is long enough to count as real content for the test here.

## Who owns an account

* Each account has one owner.
* Contact sales ops for exceptions.

```
# not a heading inside code
```

### Parent accounts

Children inherit the parent's owner when the parent is in Enterprise segment accounts.
"""


def _setup(tmp_path, files, meta_rows):
    src = tmp_path / "in"
    src.mkdir()
    for name, text in files.items():
        (src / name).write_text(text, encoding="utf-8")
    (src / "metadata.csv").write_text(META + "".join(r + "\n" for r in meta_rows), encoding="utf-8")
    return src, tmp_path / "out"


def _run(src, out):
    rows = internal.ingest(src, out, log=lambda *_: None)
    docs = {p.stem: json.loads(p.read_text()) for p in (out / "clean").glob("*.json")}
    return {r["source_file"]: r for r in rows}, docs


def test_parse_markdown_headings_levels_and_code_blocks():
    secs = internal.parse_markdown(BODY)
    assert [(s["heading"], s["level"]) for s in secs] == [
        ("Routing rules", 1), ("Who owns an account", 2), ("Parent accounts", 3)]
    assert "# not a heading inside code" in secs[1]["text"]
    assert "- Each account has one owner." in secs[1]["text"]


def test_ingest_marks_internal_and_keeps_real_content(tmp_path):
    src, out = _setup(tmp_path, {"routing.txt": BODY},
                      ["routing.txt,Routing rules,2,confidential,Sales Ops,2026-07-01,"])
    rows, docs = _run(src, out)
    assert rows["routing.txt"]["status"] == "ok"
    doc = next(iter(docs.values()))
    assert doc["visibility"] == "internal" and doc["sensitivity"] == "confidential"
    assert doc["category"] == 2 and doc["url"] is None and doc["source_file"] == "routing.txt"
    assert "Contact sales ops for exceptions." in doc["text"]      # web CTA rules are off for internal
    assert doc["text"].count("Routing rules") == 1                  # title not repeated as a heading
    assert doc["doc_id"].startswith("int_")


def test_missing_or_bad_metadata_is_flagged_not_guessed(tmp_path):
    src, out = _setup(tmp_path, {"a.txt": BODY, "b.txt": BODY.replace("Routing", "Other"), "c.txt": BODY + "x"},
                      ["b.txt,B,7,internal,,,", "c.txt,C,1,secret,,,"])
    rows, docs = _run(src, out)
    assert rows["a.txt"]["status"] == "missing_metadata"
    assert rows["b.txt"]["status"] == "bad_metadata"     # unknown category 7
    assert rows["c.txt"]["status"] == "bad_metadata"     # unknown sensitivity
    assert docs == {}


def test_duplicate_and_stale_docs(tmp_path):
    src, out = _setup(tmp_path, {"a.txt": BODY, "b.txt": BODY},
                      ["a.txt,Routing rules,2,internal,,,", "b.txt,Routing rules,2,internal,,,"])
    rows, docs = _run(src, out)
    assert rows["b.txt"]["status"] == "duplicate_content" and len(docs) == 1
    (src / "a.txt").unlink()                               # file removed -> its clean doc is removed too
    rows, docs = _run(src, out)
    assert rows["b.txt"]["status"] == "ok" and list(docs) == [internal.doc_id_for("b.txt")]


def test_doc_id_stable_when_file_is_edited(tmp_path):
    src, out = _setup(tmp_path, {"a.txt": BODY}, ["a.txt,Routing rules,2,internal,,,"])
    _, first = _run(src, out)
    (src / "a.txt").write_text(BODY + "\nOne more sentence added in an edit to the policy.\n")
    _, second = _run(src, out)
    assert list(first) == list(second)


def test_refuses_folder_inside_repo_that_is_not_gitignored():
    with pytest.raises(SystemExit, match="not gitignored"):
        internal.check_not_tracked("scraper")          # tracked code folder
    internal.check_not_tracked("data/internal")        # gitignored: fine


HEADER_FORMAT = """SYNTHETIC GLOSSARY (DEMO): ACRONYMS
Knowledge category: Segmentation and territory (SMB, Commercial, Enterprise)
Provenance: Invented for this test.
Tags: [INFERRED] = guessed. [UNKNOWN] = not confirmed.
Counts are invented.

## ROLE ACRONYMS (Synthetic, Demo)
- XR = Example Representative. Generates pipeline for the closers on the team.
- [INFERRED] XC = Example Closer. Carries a quota and closes the deals.

## SEGMENT TERMS (Synthetic, Demo)
- [UNKNOWN] Tier Z is not defined anywhere in this invented sample document.
"""


def test_header_format_without_metadata_csv(tmp_path):
    src, out = _setup(tmp_path, {"glossary.txt": HEADER_FORMAT}, [])   # no metadata rows at all
    rows, docs = _run(src, out)
    assert rows["glossary.txt"]["status"] == "ok", rows
    doc = next(iter(docs.values()))
    assert doc["title"] == "SYNTHETIC GLOSSARY (DEMO): ACRONYMS"
    assert doc["category"] == 2                                     # from "Knowledge category:" line
    assert doc["sensitivity"] == "confidential"                     # safest default when not given
    assert doc["provenance"] == "Invented for this test."
    assert doc["tag_legend"].startswith("[INFERRED]")
    assert doc["heading_suffix"] == "(Synthetic, Demo)"
    assert [s["heading"] for s in doc["sections"]] == [None, "ROLE ACRONYMS", "SEGMENT TERMS"]
    assert doc["sections"][0]["text"] == "Counts are invented."      # other header lines kept as intro
    assert doc["confidence_tags"] == {"inferred": 1, "unknown": 1}
    assert "[INFERRED] XC = Example Closer." in doc["text"]          # tags stay in the text
    assert "Knowledge category:" not in doc["text"]                  # header fields not duplicated in body


def test_metadata_csv_overrides_header(tmp_path):
    src, out = _setup(tmp_path, {"glossary.txt": HEADER_FORMAT}, ["glossary.txt,Better title,1,internal,,,"])
    _, docs = _run(src, out)
    doc = next(iter(docs.values()))
    assert (doc["title"], doc["category"], doc["sensitivity"]) == ("Better title", 1, "internal")


def test_unknown_header_category_is_flagged(tmp_path):
    src, out = _setup(tmp_path, {"g.txt": HEADER_FORMAT.replace("Segmentation and territory", "Pricing")}, [])
    rows, _ = _run(src, out)
    assert rows["g.txt"]["status"] == "bad_metadata"
