"""Status page at GET /: counts only, no secrets, 503 when the database is unavailable."""
import asyncio
from contextlib import contextmanager

import httpx

from database import queries
from mcp_server import landing
from mcp_server.server import create_server
from mcp_server.tools import TOOL_FUNCTIONS

COUNTS = [("Enablement Operations", 3), ("Sales Methodology and Process", 2)]


def test_render_shows_total_categories_and_every_tool():
    page = landing.render(COUNTS, "https://example.test/mcp")
    assert "5 knowledge units available" in page
    assert "Enablement Operations" in page and "https://example.test/mcp" in page
    assert all(f.__name__ in page for f in TOOL_FUNCTIONS)
    assert page.count('class="tag">core') == 4


def test_render_escapes_html():
    page = landing.render([("<script>x</script>", 1)], "https://example.test/mcp")
    assert "<script>x" not in page and "&lt;script&gt;" in page


def test_database_failure_is_reported_without_detail(caplog):
    def broken():
        raise RuntimeError("postgres://user:SECRET@host/db unreachable")
    assert landing.read_counts(broken) is None
    page = landing.render(None, "https://example.test/mcp")
    assert "unavailable" in page
    assert "SECRET" not in page and "SECRET" not in caplog.text


def test_counts_query_is_parameterized_and_reads_no_text():
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, sql, params): self.sql, self.params = sql, params
        def fetchall(self): return COUNTS
    cursor = Cursor()
    class Conn:
        def cursor(self): return cursor
    assert queries.unit_counts(Conn(), visibility=("public",)) == COUNTS
    assert cursor.params == (["public"],)
    assert "claim" not in cursor.sql and "evidence" not in cursor.sql


def test_http_route_returns_page_and_503_when_down(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "testserver")
    async def run(counts):
        monkeypatch.setattr(landing, "read_counts", lambda: counts)
        app = create_server().streamable_http_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://testserver") as client:
            return await client.get("/")
    ok = asyncio.run(run(COUNTS))
    assert ok.status_code == 200 and "http://testserver/mcp" in ok.text
    down = asyncio.run(run(None))
    assert down.status_code == 503


def test_http_route_shows_https_url_behind_proxy(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "testserver")
    monkeypatch.setattr(landing, "read_counts", lambda: COUNTS)
    async def run():
        app = create_server().streamable_http_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://testserver") as client:
            return await client.get("/", headers={"X-Forwarded-Proto": "https"})
    assert "https://testserver/mcp" in asyncio.run(run()).text
