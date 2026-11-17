"""Status page at GET /: shows a browser visitor that the server is up and how to connect.

The MCP endpoint itself (/mcp) only answers MCP clients, so a person who opens the URL would
otherwise see "Not Found". The page doubles as a health check: it returns 503 when the database
cannot be read. It shows counts only, never unit text, and never the database URL or error detail.
"""
import html
import inspect
import logging

import anyio
from starlette.requests import Request
from starlette.responses import HTMLResponse

from database import queries
from database.connection import connect
from mcp_server.filters import allowed_visibility
from mcp_server.tools import TOOL_FUNCTIONS

logger = logging.getLogger(__name__)
CORE_TOOLS = ("get_sales_methodology", "get_segmentation_guidance",
              "get_enablement_practices", "get_source")


def tool_summaries():
    """(name, first docstring line, is_core) for each tool, in registration order."""
    return [(f.__name__, (inspect.getdoc(f) or "").splitlines()[0] if inspect.getdoc(f) else "",
             f.__name__ in CORE_TOOLS) for f in TOOL_FUNCTIONS]


def render(counts, mcp_url):
    """Return the page HTML. counts is [(category, n)] or None when the database is unavailable."""
    esc = html.escape
    if counts is None:
        status = '<p class="bad">Server is running, but the knowledge base is unavailable right now.</p>'
        table = ""
    else:
        total = sum(n for _, n in counts)
        status = f'<p class="ok">Server is running · {total:,} knowledge units available</p>'
        rows = "".join(f"<tr><td>{esc(c)}</td><td>{n:,}</td></tr>" for c, n in counts)
        table = f"<table><tr><th>Category</th><th>Units</th></tr>{rows}</table>"
    core_tag = ' <span class="tag">core</span>'
    tools = "".join(
        f"<li><code>{esc(name)}</code>{core_tag if core else ''} — {esc(summary)}</li>"
        for name, summary, core in tool_summaries())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sales Knowledge MCP</title>
<style>
 body {{ font: 16px/1.5 system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 16px;
        color: #1d1d1f; background: #fff; }}
 code {{ background: #f2f2f4; padding: 1px 5px; border-radius: 4px; word-break: break-all; }}
 .ok {{ color: #1a7f37; font-weight: 600; }} .bad {{ color: #b42318; font-weight: 600; }}
 .tag {{ font-size: 12px; background: #e8f0fe; color: #1a4fb4; padding: 0 6px; border-radius: 8px; }}
 table {{ border-collapse: collapse; }} td, th {{ padding: 4px 16px 4px 0; text-align: left; }}
 .note {{ color: #555; font-size: 14px; }}
 @media (prefers-color-scheme: dark) {{
   body {{ color: #e6e6e6; background: #161618; }} code {{ background: #2a2a2e; }}
   .ok {{ color: #4ac26b; }} .bad {{ color: #f97066; }} .note {{ color: #aaa; }}
   .tag {{ background: #1f2d4d; color: #9db8f5; }} }}
</style></head><body>
<h1>Sales Knowledge MCP server</h1>
{status}
{table}
<h2>Connect</h2>
<p>Add this URL to an MCP-capable agent or client (transport: <b>Streamable HTTP</b>):</p>
<p><code>{esc(mcp_url)}</code></p>
<p class="note">This page is for people. Agents connect to the address above, which does not
display in a browser. No login is required, so anyone with the URL can query it: do not send
confidential information in questions.</p>
<h2>Tools</h2>
<ul>{tools}</ul>
<p class="note">Answers are knowledge units extracted from public sales sources. Units from internal Salesforce documents, when loaded, are labeled
<code>visibility: internal</code>. Each result cites its
source URL, publisher, date and an exact supporting quote. A citation shows what a source says;
it is not evidence that a practice works.</p>
<p class="note">BU Spark! DS 549 · Salesforce Sales Knowledge Extraction and MCP Retrieval</p>
</body></html>"""


def read_counts(connection_factory=connect):
    try:
        with connection_factory() as conn:
            return queries.unit_counts(conn, visibility=allowed_visibility())
    except Exception as error:  # report the type only: the message can contain connection details
        logger.warning("status page: database unavailable (%s)", type(error).__name__)
        return None


async def landing(request: Request) -> HTMLResponse:
    counts = await anyio.to_thread.run_sync(read_counts)
    base = request.base_url
    # Heroku ends HTTPS at its router and forwards plain HTTP; show the URL the visitor used.
    if request.headers.get("x-forwarded-proto") == "https":
        base = base.replace(scheme="https")
    mcp_url = str(base).rstrip("/") + "/mcp"
    return HTMLResponse(render(counts, mcp_url), status_code=200 if counts is not None else 503)
