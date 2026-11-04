"""Source registry (one row per URL, latest attempt), the CSV report and the run summary.

registry.jsonl is the source of truth (gitignored, lives with the scraped data). The CSV mirror
and summary.md hold URLs and statuses only, so they are committed. Column names are stable
snake_case so the registry can load straight into a Postgres `sources` table later.
"""
import csv
import json
import statistics
from collections import Counter, defaultdict

from data_pipeline.scraper import config

COLUMNS = ["doc_id", "url", "final_url", "domain", "category", "section_label", "status", "reason",
           "http_status", "fetch_method", "content_type", "word_count", "content_sha256",
           "retrieved_at", "robots_allowed", "tos_flag", "duplicate_of", "clean_path"]


def load(path=None):
    """{url: row}. Later lines win, so appending a row is an upsert."""
    path = path or config.REGISTRY
    rows = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["url"]] = row
    return rows


def append(row, path=None):
    """Append one row right away, so a crash mid-run loses nothing."""
    path = path or config.REGISTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({c: row.get(c) for c in COLUMNS}, ensure_ascii=False) + "\n")


def compact(rows, path=None):
    """Rewrite the file with only the latest row per URL."""
    path = path or config.REGISTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows.values():
            f.write(json.dumps({c: row.get(c) for c in COLUMNS}, ensure_ascii=False) + "\n")


def write_csv(rows, path=None, columns=COLUMNS):
    path = path or config.REPORT_CSV
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _table(header, body):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in body]
    return "\n".join(lines)


def summary_markdown(rows, manifest, tos_unreviewed):
    """Human-readable run summary. `rows` = registry rows, `manifest` = all manifest rows."""
    cats = sorted({m["category"] for m in manifest})
    attempted = {r["url"] for r in rows}
    out = ["# Scrape summary", ""]
    out.append(f"{len(rows)} of {len(manifest)} manifest URLs attempted; "
               f"{sum(r['status'] == 'ok' for r in rows)} usable (`ok`).")
    out.append("")

    # Status x category
    by = Counter((r["status"], r["category"]) for r in rows)
    statuses = sorted({r["status"] for r in rows}, key=lambda s: (s != "ok", s))
    body = [[s] + [by[(s, c)] for c in cats] + [sum(by[(s, c)] for c in cats)] for s in statuses]
    not_run = [sum(1 for m in manifest if m["category"] == c and m["url"] not in attempted) for c in cats]
    body.append(["_not attempted_"] + not_run + [sum(not_run)])
    out += ["## Status by category", "", _table(["status"] + [f"cat {c}" for c in cats] + ["total"], body), ""]

    # Usable docs per domain per category (shows the skew)
    ok = [r for r in rows if r["status"] == "ok"]
    out += ["## Usable docs per domain", ""]
    for c in cats:
        dom = Counter(r["domain"] for r in ok if r["category"] == c)
        if dom:
            out.append(f"**Category {c}** ({sum(dom.values())} docs, {len(dom)} domains): "
                       + ", ".join(f"{d} {n}" for d, n in dom.most_common()))
            out.append("")

    # Failing domains
    fails = defaultdict(Counter)
    for r in rows:
        if r["status"] != "ok":
            fails[r["domain"]][f"{r['status']}: {r.get('reason') or ''}".rstrip(": ")] += 1
    if fails:
        top = sorted(fails.items(), key=lambda kv: -sum(kv[1].values()))[:20]
        out += ["## Top failing domains", "",
                _table(["domain", "failures", "reasons"],
                       [[d, sum(c.values()), "; ".join(f"{k} (x{n})" for k, n in c.most_common(3))] for d, c in top]),
                ""]

    # Word counts
    wc = sorted(r["word_count"] for r in ok if r.get("word_count"))
    if wc:
        buckets = Counter("<500" if w < 500 else "500-1999" if w < 2000 else "2000-4999" if w < 5000 else "5000+"
                          for w in wc)
        out += ["## Word counts (ok docs)", "",
                f"min {wc[0]}, median {int(statistics.median(wc))}, max {wc[-1]}", "",
                _table(["words", "docs"], [[b, buckets[b]] for b in ["<500", "500-1999", "2000-4999", "5000+"]]), ""]

    out += ["## Domains whose terms of service haven't been reviewed", "",
            "A human should check these and mark them `tos_reviewed: true` or `skip: true` in "
            "`data_pipeline/scraper/domains.yaml`.", "", ", ".join(tos_unreviewed) or "(none)", ""]
    return "\n".join(out)
