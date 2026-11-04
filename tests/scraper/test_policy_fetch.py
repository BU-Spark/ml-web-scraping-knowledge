from data_pipeline.scraper import config
from data_pipeline.scraper.fetch import Throttle
from data_pipeline.scraper.policy import Policy

from .conftest import FakeClock, make_fetcher

PAGE = "https://site.com/blog/post"


def test_robots_disallow_blocks():
    f = make_fetcher({"https://site.com/robots.txt": (200, "User-agent: *\nDisallow: /blog/\n")})
    d = Policy(f, rules={}).check(PAGE, "site.com")
    assert (d.allowed, d.status) == (False, "blocked_robots")


def test_robots_rule_for_our_bot_name():
    robots = f"User-agent: {config.BOT_NAME}\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    f = make_fetcher({"https://site.com/robots.txt": (200, robots)})
    assert Policy(f, rules={}).check(PAGE, "site.com").status == "blocked_robots"


def test_crawl_delay_is_honored_when_longer():
    f = make_fetcher({"https://site.com/robots.txt": (200, "User-agent: *\nCrawl-delay: 10\n")})
    d = Policy(f, rules={}).check(PAGE, "site.com")
    assert d.allowed and d.delay == 10


def test_missing_robots_allows_but_errors_block():
    assert Policy(make_fetcher({}), rules={}).check(PAGE, "site.com").allowed  # 404 -> allowed
    f = make_fetcher({"https://site.com/robots.txt": (403, "")})
    d = Policy(f, rules={}).check(PAGE, "site.com")
    assert d.status == "blocked_robots" and "403" in d.reason


def test_robots_fetched_once_per_host():
    f = make_fetcher({"https://site.com/robots.txt": (200, "User-agent: *\nAllow: /\n")})
    p = Policy(f, rules={})
    p.check(PAGE, "site.com")
    p.check("https://site.com/other", "site.com")
    assert [c for c in f.session.calls if c[1].endswith("robots.txt")] == [("GET", "https://site.com/robots.txt")]


def test_tos_skip_matches_subdomains_without_network():
    f = make_fetcher({})
    d = Policy(f, rules={"close.com": {"skip": True, "reason": "ToS"}}).check("https://blog.close.com/x", "blog.close.com")
    assert d.status == "blocked_tos" and f.session.calls == []


def test_throttle_spaces_same_host_but_not_different_hosts():
    clock = FakeClock()
    t = Throttle(clock=clock, sleep=clock.sleep)
    t.wait("a.com", 3)
    t.wait("b.com", 3)          # different host: no wait
    assert clock.sleeps == []
    t.wait("a.com", 3)          # same host: waits the full delay
    assert clock.sleeps == [3]


def test_requests_to_one_host_are_delay_apart():
    clock = FakeClock()
    f = make_fetcher({PAGE: (200, "x"), "https://site.com/b": (200, "y")}, clock)
    times = []
    real = f.session.request
    f.session.request = lambda *a, **k: (times.append(clock.now), real(*a, **k))[1]
    f.get(PAGE, delay=5)
    f.get("https://site.com/b", delay=5)
    assert times[1] - times[0] >= 5


def test_retry_on_503_then_success_and_no_retry_on_404():
    f = make_fetcher({PAGE: (503, "")})
    calls = {"n": 0}
    real = f.session.request

    def flaky(method, url, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            f.session.routes[PAGE] = (200, "ok")
        return real(method, url, **kw)
    f.session.request = flaky
    assert f.get(PAGE).http_status == 200 and calls["n"] == 2

    f2 = make_fetcher({})
    assert f2.get(PAGE).http_status == 404 and len(f2.session.calls) == 1
