"""Scraper CLI. Run from the repo root:

  python3 -m scraper parse   [--links data/urls/public_urls_compiled.txt]   # link file -> manifest + counts
  python3 -m scraper probe   [--category 1,2] [--domain x.com]            # robots + HEAD only, no bodies
  python3 -m scraper run     [--category 1,2] [--domain x.com] [--limit N] [--sample-per-domain K]
                             [--refetch] [--force]
  python3 -m scraper report                                               # rebuild CSV + summary.md
  python3 -m scraper show    <doc_id|url>                                 # print one clean doc
  python3 -m scraper export-sections                                      # clean docs -> data/output/sections.json
"""
import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from scraper import config, links, pipeline, registry
from scraper.fetch import Fetcher
from scraper.policy import Policy

log = logging.getLogger("scraper")


def _setup_logging(name):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = config.LOG_DIR / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.log"
    fmt = logging.Formatter("%(message)s")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(path, encoding="utf-8")):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    return path


def _categories(value):
    return [int(c) for c in value.split(",")] if value else None


def cmd_parse(args):
    rows = links.parse_link_file(Path(args.links).read_text(encoding="utf-8"))
    links.write_manifest(rows)
    counts = Counter(r["category"] for r in rows)
    print(f"Parsed {len(rows)} URLs from {args.links} -> {config.MANIFEST}")
    for cat in sorted(counts):
        doms = Counter(r["domain"] for r in rows if r["category"] == cat)
        print(f"  category {cat:>2} ({config.CATEGORY_NAMES.get(cat)}): {counts[cat]} URLs, {len(doms)} domains; "
              f"top: {', '.join(f'{d} {n}' for d, n in doms.most_common(3))}")
    also = [r for r in rows if r["also_categories"]]
    print(f"  {len(also)} URLs also tagged for other categories")
    problems = links.check_counts(rows)
    if problems:
        print("COUNT CHECK FAILED:\n  " + "\n  ".join(problems))
        sys.exit(1)
    print("Count check OK (" + " / ".join(str(n) for n in config.EXPECTED_COUNTS.values()) + ").")


def cmd_probe(args):
    log_path = _setup_logging("probe")
    rows = pipeline.select(links.load_manifest(), _categories(args.category), args.domain, limit=args.limit)
    fetcher = Fetcher()
    policy = Policy(fetcher)
    out = []
    for i, m in enumerate(rows, 1):
        d = policy.check(m["url"], m["domain"])
        rec = {"doc_id": m["doc_id"], "url": m["url"], "domain": m["domain"], "category": m["category"],
               "policy": d.status, "reason": d.reason, "http_status": None, "content_type": None, "final_url": None}
        if d.allowed:
            r = fetcher.head(m["url"], d.delay)
            rec.update(http_status=r.http_status, content_type=r.content_type, final_url=r.final_url,
                       reason=r.error or d.reason)
        out.append(rec)
        log.info(f"[{i}/{len(rows)}] {rec['policy']:<14} {rec['http_status'] or '-':<4} "
                 f"{(rec['content_type'] or '-'):<24} {m['url']}  {rec['reason']}")
    cols = ["doc_id", "url", "domain", "category", "policy", "reason", "http_status", "content_type", "final_url"]
    registry.write_csv(out, config.PROBE_CSV, cols)

    print(f"\nProbe of {len(out)} URLs -> {config.PROBE_CSV} (log: {log_path})")
    print("Policy:", dict(Counter(r["policy"] for r in out)))
    print("HTTP status:", dict(Counter(r["http_status"] for r in out if r["policy"] == "allowed")))
    print("Content types:", dict(Counter(r["content_type"] for r in out if r["policy"] == "allowed")))
    per = defaultdict(Counter)
    for r in out:
        bad = r["policy"] != "allowed" or not r["http_status"] or r["http_status"] >= 400
        per[r["domain"]]["bad" if bad else "good"] += 1
    problem = sorted(((d, c) for d, c in per.items() if c["bad"]), key=lambda kv: -kv[1]["bad"])
    if problem:
        print("Domains with blocked/failed URLs (bad/total):")
        for d, c in problem:
            reasons = Counter(r["reason"] or f"HTTP {r['http_status']}" for r in out if r["domain"] == d and
                              (r["policy"] != "allowed" or not r["http_status"] or r["http_status"] >= 400))
            print(f"  {d}: {c['bad']}/{c['bad'] + c['good']}  {dict(reasons)}")


def cmd_run(args):
    log_path = _setup_logging("run")
    manifest = links.load_manifest()
    rows = pipeline.select(manifest, _categories(args.category), args.domain, args.sample_per_domain, args.limit)
    reg = registry.load()
    fetcher = Fetcher()
    policy = Policy(fetcher)
    dupes = pipeline.DuplicateIndex.from_clean_dir()
    todo = [m for m in rows if args.force or reg.get(m["url"], {}).get("status") != "ok"]
    log.info(f"{len(rows)} URLs selected, {len(rows) - len(todo)} already ok (skipped; use --force to redo), "
             f"{len(todo)} to process. Log: {log_path}")
    for i, m in enumerate(todo, 1):
        row = pipeline.process(m, policy, fetcher, dupes, refetch=args.refetch)
        tb = row.pop("traceback", None)
        registry.append(row)
        reg[row["url"]] = row
        reason = f" ({row['reason']})" if row["reason"] else ""
        log.info(f"[{i}/{len(todo)}] [{row['status']}] {row['word_count'] or 0} {row['domain']} {row['url']}{reason}")
        if tb:
            log.info(tb)
    registry.compact(reg)
    _write_reports(reg, manifest, policy)
    log.info("Status counts this run: " + str(dict(Counter(reg[m["url"]]["status"] for m in rows if m["url"] in reg))))


def _write_reports(reg, manifest, policy):
    order = {m["url"]: i for i, m in enumerate(manifest)}
    rows = sorted(reg.values(), key=lambda r: order.get(r["url"], 1e9))
    registry.write_csv(rows)
    attempted_domains = {r["domain"] for r in rows if r["status"] != "blocked_tos"}
    config.SUMMARY_MD.write_text(registry.summary_markdown(rows, manifest, policy.tos_unreviewed(attempted_domains)),
                                 encoding="utf-8")
    print(f"Wrote {config.REPORT_CSV} and {config.SUMMARY_MD}")


def cmd_report(args):
    _write_reports(registry.load(), links.load_manifest(), Policy(fetcher=None))


def _find_doc(key):
    doc_id = key if len(key) == 16 and "/" not in key else links.doc_id_for(links.normalize_url(key))
    path = config.CLEAN_DIR / f"{doc_id}.json"
    if not path.exists():
        reg = registry.load()
        row = next((r for r in reg.values() if r["doc_id"] == doc_id), None)
        status = f"registry status: {row['status']} ({row['reason']})" if row else "not in the registry"
        raise SystemExit(f"No clean doc for {key} [{doc_id}]; {status}")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_show(args):
    doc = _find_doc(args.key)
    skip = {"sections", "text"}
    for k, v in doc.items():
        if k not in skip:
            print(f"{k:>16}: {v}")
    print(f"{'sections':>16}: {len(doc['sections'])}")
    print("-" * 80)
    text = doc["text"]
    print(text if args.full or len(text) < 6000 else text[:6000] + f"\n\n... [{len(text) - 6000} more chars; use --full]")


def cmd_export_sections(args):
    out = []
    for p in sorted(config.CLEAN_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if args.category and d["category"] not in _categories(args.category):
            continue
        for s in d["sections"]:
            out.append({"doc_id": d["doc_id"], "source_url": d["url"], "domain": d["domain"],
                        "page_title": d["title"], "heading": s["heading"] or d["title"], "text": s["text"],
                        "category": d["category"], "scraped_at": d["retrieved_at"][:10]})
    config.SECTIONS_EXPORT.parent.mkdir(parents=True, exist_ok=True)
    config.SECTIONS_EXPORT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(out)} sections to {config.SECTIONS_EXPORT}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m scraper", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("parse", help="link file -> manifest")
    s.add_argument("--links", default=str(config.LINK_FILE))
    s.set_defaults(func=cmd_parse)

    for name, func in (("probe", cmd_probe), ("run", cmd_run)):
        s = sub.add_parser(name)
        s.add_argument("--category", help="e.g. 1,2")
        s.add_argument("--domain", help="only this domain (and its subdomains)")
        s.add_argument("--limit", type=int)
        s.set_defaults(func=func)
        if name == "run":
            s.add_argument("--sample-per-domain", type=int, help="pilot: at most K URLs per domain")
            s.add_argument("--refetch", action="store_true", help="ignore the raw cache and download again")
            s.add_argument("--force", action="store_true", help="re-process URLs already marked ok")

    sub.add_parser("report").set_defaults(func=cmd_report)

    s = sub.add_parser("show")
    s.add_argument("key", help="doc_id or URL")
    s.add_argument("--full", action="store_true")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("export-sections", help="clean docs -> flat sections.json for chunking/")
    s.add_argument("--category")
    s.set_defaults(func=cmd_export_sections)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
