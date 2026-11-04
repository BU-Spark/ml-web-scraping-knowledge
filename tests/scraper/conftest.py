"""Shared test helpers: a fake HTTP session (no network) and temp output folders."""
from pathlib import Path

import pytest

from data_pipeline.scraper import config
from data_pipeline.scraper.fetch import Fetcher, Throttle

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, url, status=200, body="", headers=None):
        self.url, self.status_code = url, status
        self.content = body.encode("utf-8") if isinstance(body, str) else body
        self.text = self.content.decode("utf-8", "replace")
        self.headers = {"Content-Type": "text/html; charset=utf-8"} | (headers or {})

    def close(self):
        pass


class FakeSession:
    """routes: {url: (status, body[, headers])}. Unknown robots.txt -> 404, unknown page -> 404."""

    def __init__(self, routes):
        self.routes = routes
        self.headers = {}
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        status, body, *rest = self.routes.get(url, (404, ""))
        return FakeResponse(url, status, body, rest[0] if rest else None)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_fetcher(routes, clock=None):
    clock = clock or FakeClock()
    return Fetcher(session=FakeSession(routes), throttle=Throttle(clock=clock, sleep=clock.sleep),
                   user_agent="test-bot", sleep=clock.sleep)


@pytest.fixture(autouse=True)
def tmp_outputs(tmp_path, monkeypatch):
    """Point every output path at a temp folder so tests never touch data/."""
    monkeypatch.setattr(config, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "out" / "raw")
    monkeypatch.setattr(config, "CLEAN_DIR", tmp_path / "out" / "clean")
    monkeypatch.setattr(config, "REGISTRY", tmp_path / "out" / "registry.jsonl")
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "out" / "logs")
    monkeypatch.setattr(config, "SCRAPE_DIR", tmp_path / "scrape")
    monkeypatch.setattr(config, "MANIFEST", tmp_path / "scrape" / "manifest.jsonl")
    monkeypatch.setattr(config, "REPORT_CSV", tmp_path / "scrape" / "scrape_report.csv")
    monkeypatch.setattr(config, "PROBE_CSV", tmp_path / "scrape" / "probe_report.csv")
    monkeypatch.setattr(config, "SUMMARY_MD", tmp_path / "scrape" / "summary.md")
    monkeypatch.setenv("SCRAPER_CONTACT", "test@example.edu")
    return tmp_path
