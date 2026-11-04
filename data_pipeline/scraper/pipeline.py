"""Process one manifest row end to end: policy -> fetch (or cache) -> extract -> clean -> gates -> write.

Every outcome becomes a registry row with a status and a reason; nothing fails silently.

Statuses: ok, blocked_robots, blocked_tos, timeout, fetch_error, http_error, bot_challenge,
redirected_away, non_html_skipped, paywall_or_login, js_required_failed, too_short, non_english,
duplicate_content, error (unexpected exception; see reason).
"""
import hashlib
import json
import traceback
from collections import defaultdict
from itertools import zip_longest

from bs4 import UnicodeDammit

from data_pipeline.scraper import clean, config, extract, fetch, quality, sec
from data_pipeline.scraper.links import normalize_url


def order_round_robin(rows):
    """Interleave domains (a, b, c, a, b, c, ...) so the per-host delay rarely makes us wait."""
    by_domain = defaultdict(list)
    for r in rows:
        by_domain[r["domain"]].append(r)
    return [r for group in zip_longest(*by_domain.values()) for r in group if r is not None]


def select(manifest, categories=None, domain=None, sample_per_domain=None, limit=None):
    rows = [r for r in manifest
            if (not categories or r["category"] in categories)
            and (not domain or r["domain"] == domain or r["domain"].endswith("." + domain))]
    if sample_per_domain:
        taken = defaultdict(int)
        kept = []
        for r in rows:
            if taken[r["domain"]] < sample_per_domain:
                taken[r["domain"]] += 1
                kept.append(r)
        rows = kept
    rows = order_round_robin(rows)
    return rows[:limit] if limit else rows


class DuplicateIndex:
    """Remembers content hashes and canonical URLs of accepted docs."""

    def __init__(self):
        self.by_hash, self.by_canonical = {}, {}

    @classmethod
    def from_clean_dir(cls):
        idx = cls()
        for p in sorted(config.CLEAN_DIR.glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            idx.add(d["doc_id"], d["content_sha256"], d.get("canonical_url"))
        return idx

    def find(self, doc_id, sha, canonical):
        other = self.by_hash.get(sha)
        if other and other != doc_id:
            return other, "same content as"
        other = self.by_canonical.get(normalize_url(canonical)) if canonical else None
        if other and other != doc_id:
            return other, "same canonical URL as"
        return None, ""

    def add(self, doc_id, sha, canonical):
        self.by_hash.setdefault(sha, doc_id)
        if canonical:
            self.by_canonical.setdefault(normalize_url(canonical), doc_id)


def _base_row(m, policy):
    return {
        "doc_id": m["doc_id"], "url": m["url"], "final_url": None, "domain": m["domain"],
        "category": m["category"], "section_label": m["section_label"], "status": None, "reason": "",
        "http_status": None, "fetch_method": None, "content_type": None, "word_count": None,
        "content_sha256": None, "retrieved_at": None, "robots_allowed": None,
        "tos_flag": policy.tos_flag(m["domain"]), "duplicate_of": None, "clean_path": None,
    }


def _remove_clean(doc_id):
    (config.CLEAN_DIR / f"{doc_id}.json").unlink(missing_ok=True)


def process(m, policy, fetcher, dupes, refetch=False):
    row = _base_row(m, policy)
    try:
        return _process(m, row, policy, fetcher, dupes, refetch)
    except Exception as err:  # keep going; record what broke
        _remove_clean(m["doc_id"])
        row.update(status="error", reason=f"{type(err).__name__}: {err}"[:300])
        row["traceback"] = traceback.format_exc()  # printed to the run log, not stored in the registry
        return row


def _process(m, row, policy, fetcher, dupes, refetch):
    doc_id, url, domain = m["doc_id"], m["url"], m["domain"]

    # 1. Policy (ToS always re-checked from domains.yaml; robots result reused from the cache)
    tos = policy.tos(domain)
    if not tos.allowed:
        _remove_clean(doc_id)
        return row | {"status": tos.status, "reason": tos.reason}
    cached = None if refetch else fetch.load_raw(doc_id)
    if cached:
        result, extra = cached
        row["robots_allowed"] = extra.get("robots_allowed")
    else:
        decision = policy.check(url, domain)
        row["robots_allowed"] = decision.status != "blocked_robots"
        if not decision.allowed:
            _remove_clean(doc_id)
            return row | {"status": decision.status, "reason": decision.reason}
        result = fetcher.get(url, decision.delay)
        fetch.save_raw(doc_id, result, {"robots_allowed": True})

    row.update(final_url=result.final_url or None, http_status=result.http_status,
               fetch_method=result.fetch_method, content_type=result.content_type,
               retrieved_at=result.retrieved_at)

    # 2. Transport-level failures
    if result.error:
        _remove_clean(doc_id)
        return row | {"status": "timeout" if result.error == "timeout" else "fetch_error", "reason": result.error}
    html = (UnicodeDammit(result.content, is_html=True).unicode_markup or "") if result.content else ""
    html_lower = html.lower()
    if reason := quality.bot_challenge(result.http_status, html_lower):
        _remove_clean(doc_id)
        return row | {"status": "bot_challenge", "reason": f"HTTP {result.http_status}; {reason}"}
    if result.http_status and result.http_status >= 400:
        _remove_clean(doc_id)
        return row | {"status": "http_error", "reason": f"HTTP {result.http_status}"}

    if reason := quality.redirected_away(url, result.final_url):
        _remove_clean(doc_id)
        return row | {"status": "redirected_away", "reason": reason}

    # 3. Content type
    ctype = result.content_type
    if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf"):
        _remove_clean(doc_id)
        return row | {"status": "non_html_skipped", "reason": "PDF (skipped for MVP)", "content_type": "pdf"}
    if ctype and "html" not in ctype and "xml" not in ctype:
        _remove_clean(doc_id)
        return row | {"status": "non_html_skipped", "reason": f"content type {ctype}"}
    row["content_type"] = "html"

    # 4. Extract + clean
    meta, sections, extractor = extract.extract(html, result.final_url or url, domain)
    sections, clean_stats = clean.clean_sections(sections)
    if domain == "sec.gov":  # filings are huge; keep only the business description
        sections, clean_stats["sec"] = sec.business_sections(sections)
    title = clean.normalize(meta["title"]) if meta["title"] else None
    text = clean.sections_to_text(title, sections)
    body_words = sum(quality.word_count(s["text"]) for s in sections)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    row.update(word_count=body_words, content_sha256=sha)

    # 5. Gates (first failure wins)
    gates = [
        ("paywall_or_login", quality.paywall_or_login(result.final_url, url, html_lower, body_words)),
        ("js_required_failed", quality.js_wall(html_lower, body_words)),
        ("too_short", quality.too_short(body_words)),
        ("non_english", quality.non_english(meta["language"], text)),
    ]
    for status, reason in gates:
        if reason:
            _remove_clean(doc_id)
            if status == "js_required_failed":
                reason += " (no Playwright fallback yet)"
            return row | {"status": status, "reason": reason}
    dup_of, why = dupes.find(doc_id, sha, meta["canonical_url"])
    if dup_of:
        _remove_clean(doc_id)
        return row | {"status": "duplicate_content", "reason": f"{why} {dup_of}", "duplicate_of": dup_of}

    # 6. Write the clean doc
    doc = {
        "doc_id": doc_id, "url": url, "final_url": result.final_url, "canonical_url": meta["canonical_url"],
        "domain": domain, "publisher": meta["publisher"],
        "category": m["category"], "category_name": m["category_name"],
        "also_categories": m["also_categories"], "section_label": m["section_label"],
        "title": title, "author": meta["author"],
        "published_date": meta["published_date"], "modified_date": meta["modified_date"],
        "description": meta["description"], "language": (meta["language"] or "en").split("-")[0].lower(),
        "retrieved_at": result.retrieved_at, "fetch_method": result.fetch_method, "extractor": extractor,
        "content_type": "html", "word_count": body_words, "content_sha256": sha, "visibility": "public",
        "clean_stats": clean_stats, "sections": sections, "text": text,
    }
    config.CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    path = config.CLEAN_DIR / f"{doc_id}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    dupes.add(doc_id, sha, meta["canonical_url"])
    return row | {"status": "ok", "clean_path": str(path)}
