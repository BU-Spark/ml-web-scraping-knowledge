import json

from scraper import __main__ as cli
from scraper import clean, config, extract, links, pipeline, registry
from scraper.policy import Policy

from .conftest import fixture, make_fetcher

ROBOTS_OK = (200, "User-agent: *\nAllow: /\n")


def _row(url, category=1):
    norm = links.normalize_url(url)
    return {"doc_id": links.doc_id_for(norm), "url": url, "url_normalized": norm, "domain": links.domain_of(url),
            "category": category, "category_name": config.CATEGORY_NAMES[category],
            "section_label": "Test", "also_categories": [], "source_line": 1}


def _process(routes, url, dupes=None):
    f = make_fetcher(routes)
    return pipeline.process(_row(url), Policy(f, rules={}), f, dupes or pipeline.DuplicateIndex())


def test_blog_keeps_article_and_headings_only():
    meta, sections, _ = extract.extract(fixture("blog.html"), "https://blog.example.com/meddicc-guide/", "blog.example.com")
    sections, _ = clean.clean_sections(sections)
    headings = [s["heading"] for s in sections]
    assert "The seven elements" in headings and "Metrics in practice" in headings and "When to use MEDDICC" in headings
    text = "\n".join(s["text"] for s in sections).lower()
    for junk in ("we use cookies", "pricing", "subscribe to our newsletter", "share this article",
                 "related posts", "cold email", "all rights reserved"):
        assert junk not in text, junk
    assert "- metrics: the measurable value" in text          # list items kept as "- " lines
    assert "metrics | what will improve?" in text              # table kept as pipe text
    levels = {s["heading"]: s["level"] for s in sections}
    assert levels["The seven elements"] == 2 and levels["Metrics in practice"] == 3
    assert meta["publisher"] == "Example Sales Blog" and meta["author"] == "Jane Seller"
    assert meta["published_date"] == "2025-04-02"
    assert meta["canonical_url"] == "https://blog.example.com/meddicc-guide/"


def test_ok_doc_written_with_provenance():
    url = "https://blog.example.com/meddicc-guide/"
    row = _process({"https://blog.example.com/robots.txt": ROBOTS_OK, url: (200, fixture("blog.html"))}, url)
    assert row["status"] == "ok", row
    doc = json.loads((config.CLEAN_DIR / f"{row['doc_id']}.json").read_text())
    assert doc["visibility"] == "public" and doc["content_sha256"] == row["content_sha256"]
    assert doc["text"].startswith("# What Is MEDDICC?")
    assert "## The seven elements" in doc["text"] and "### Metrics in practice" in doc["text"]
    assert doc["retrieved_at"].endswith("Z") and doc["final_url"] == url


def test_short_page_is_too_short():
    url = "https://site.com/contact"
    row = _process({"https://site.com/robots.txt": ROBOTS_OK, url: (200, fixture("short.html"))}, url)
    assert row["status"] == "too_short"
    assert not (config.CLEAN_DIR / f"{row['doc_id']}.json").exists()


def test_login_wall_is_paywall_or_login():
    url = "https://research.com/report"
    row = _process({"https://research.com/robots.txt": ROBOTS_OK, url: (200, fixture("login.html"))}, url)
    assert row["status"] == "paywall_or_login", row


def test_robots_block_stops_before_fetch():
    url = "https://site.com/private/page"
    f = make_fetcher({"https://site.com/robots.txt": (200, "User-agent: *\nDisallow: /private/\n")})
    row = pipeline.process(_row(url), Policy(f, rules={}), f, pipeline.DuplicateIndex())
    assert row["status"] == "blocked_robots" and row["robots_allowed"] is False
    assert ("GET", url) not in f.session.calls


def test_pdf_is_skipped():
    url = "https://site.com/report.pdf"
    row = _process({"https://site.com/robots.txt": ROBOTS_OK,
                    url: (200, b"%PDF-1.4", {"Content-Type": "application/pdf"})}, url)
    assert row["status"] == "non_html_skipped"


def test_same_content_at_two_urls_is_duplicate():
    a, b = "https://one.com/post", "https://two.com/copy"
    routes = {"https://one.com/robots.txt": ROBOTS_OK, "https://two.com/robots.txt": ROBOTS_OK,
              a: (200, fixture("blog.html").replace('<link rel="canonical" href="https://blog.example.com/meddicc-guide/">', "")),
              b: (200, fixture("blog.html").replace('<link rel="canonical" href="https://blog.example.com/meddicc-guide/">', ""))}
    f = make_fetcher(routes)
    policy, dupes = Policy(f, rules={}), pipeline.DuplicateIndex()
    first = pipeline.process(_row(a), policy, f, dupes)
    second = pipeline.process(_row(b), policy, f, dupes)
    assert first["status"] == "ok"
    assert second["status"] == "duplicate_content" and second["duplicate_of"] == first["doc_id"]


def test_second_run_skips_ok_rows_and_uses_cache(monkeypatch):
    url = "https://blog.example.com/meddicc-guide/"
    routes = {"https://blog.example.com/robots.txt": ROBOTS_OK, url: (200, fixture("blog.html"))}
    links.write_manifest([_row(url)])
    fetchers = []

    def fake_fetcher(*a, **k):
        fetchers.append(make_fetcher(routes))
        return fetchers[-1]
    monkeypatch.setattr(cli, "Fetcher", fake_fetcher)
    monkeypatch.setattr(cli, "Policy", lambda f: Policy(f, rules={}))

    cli.main(["run"])
    assert registry.load()[url]["status"] == "ok"
    cli.main(["run"])                          # nothing to do: already ok
    assert fetchers[1].session.calls == []
    cli.main(["run", "--force"])               # re-processes from the raw cache, no network
    assert fetchers[2].session.calls == []
    assert config.SUMMARY_MD.exists() and config.REPORT_CSV.exists()


def test_redirect_to_generic_page_is_flagged():
    from scraper import quality
    assert quality.redirected_away("https://forcemanagement.com/seller-blog/some-post", "https://www.ascender.co/")
    assert quality.redirected_away("https://www.salesforce.com/in/hub/sales/best-practices/",
                                   "https://www.salesforce.com/in/resources/")
    assert not quality.redirected_away("https://handbook.gitlab.com/job-families/sales",
                                       "https://handbook.gitlab.com/job-description-library/sales/")


def test_teasers_and_tab_navigation_are_dropped():
    sections = [
        {"heading": "How to negotiate", "level": 2, "text": "Real body text about negotiation.\n- Create a plan"},
        {"heading": "Create a plan", "level": 3, "text": "Plan details that matter."},
        {"heading": "Another great post", "level": 3, "text": "Buyers today are different from what we've seen..."},
    ]
    out, stats = clean.clean_sections(sections)
    assert [s["heading"] for s in out] == ["How to negotiate", "Create a plan"]
    assert out[0]["text"] == "Real body text about negotiation."
    assert stats["teaser_sections"] == 1 and stats["nav_lines"] == 1


def test_sec_keeps_business_item_and_recovers_headings():
    from scraper import sec
    text = "\n".join(["Item 1. | |", "Item 1A. | |",                       # table of contents
                      "ITEM 1. BUSINESS", "Overview", "We sell software to companies of all sizes.",
                      "Sales and Marketing", "We sell primarily through our direct sales force.",
                      "•partner co-marketing activities;",
                      "ITEM 1A. RISK FACTORS", "Risks", "Many risks exist."])
    out, note = sec.business_sections([{"heading": None, "level": 0, "text": text}])
    assert [s["heading"] for s in out] == ["Overview", "Sales and Marketing"]
    assert out[1]["text"].endswith("- partner co-marketing activities;")
    assert "Many risks" not in str(out) and "kept Item 1. Business" in note
