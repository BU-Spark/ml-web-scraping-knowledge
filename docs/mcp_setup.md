# Connecting to the Sales Knowledge MCP server

For: anyone connecting an agent to the server (Brian first).
Full tool reference: [mcp_tool_schema.md](mcp_tool_schema.md). Deployment: [../deployment/heroku_notes.md](../deployment/heroku_notes.md).

> **Status:** live since Nov 16, 2026. Open https://bu-research-7dc3f331235a.herokuapp.com/ in a
> browser to check it is up and see how many knowledge units are loaded.

## What it is

An MCP server that answers sales questions with short, cited **knowledge units** extracted from
public sales sources. Units from internal Salesforce documents, when loaded, are labeled as such.
Every result carries its source URL, publisher, date and the exact supporting quote.

A citation means *a source says this*. It is not evidence that the practice works.

## Connect

| Setting | Value |
|---|---|
| URL | `https://bu-research-7dc3f331235a.herokuapp.com/mcp` |
| Transport | Streamable HTTP (stateless, JSON responses) |
| Authentication | None. Anyone with the URL can call the tools; do not send confidential input. |

Any MCP client that supports Streamable HTTP can connect. A typical client configuration:

```json
{
  "mcpServers": {
    "sales-knowledge": {
      "type": "http",
      "url": "https://bu-research-7dc3f331235a.herokuapp.com/mcp"
    }
  }
}
```

To try it without writing code, run `npx @modelcontextprotocol/inspector`, choose
"Streamable HTTP", paste the URL, then **List Tools**.

## Tools

Start with the four core tools:

| Tool | Use it for | Example arguments |
|---|---|---|
| `get_sales_methodology` | Sales methodology and process (qualification, discovery, deal stages, MEDDICC…) | `{"query": "How should a rep qualify an enterprise deal?", "entity": "MEDDICC"}` |
| `get_segmentation_guidance` | Segmentation and territory (SMB / commercial / enterprise, ICP, account tiers) | `{"query": "How do teams split territories for commercial accounts?", "company_size": "commercial"}` |
| `get_enablement_practices` | Enablement operations (onboarding, coaching, training, ramp) | `{"query": "What makes new-rep onboarding effective?"}` |
| `get_source` | The full supporting passage behind a result | `{"identifier": "<unit_id from a result>"}` |

Also available: `get_objection_handling`, `compare_approaches`, `map_value_drivers`,
`audit_messaging_alignment`, `score_adherence_metric`. The last two use simple word matching,
not AI judgment, and say so in their output.

Common optional arguments: `entity` (a named method, e.g. `MEDDIC`; MEDDIC and MEDDICC match each
other), `topic`, `role`, `industry`, `company_size`, `limit` (1–20, default 5). Optional filters
only match units that have that metadata, so use them sparingly.

## What a result looks like

```json
{
  "status": "ok",
  "results": [{
    "unit_id": "…", "claim": "…", "level": "know_how", "category": "Sales Methodology and Process",
    "visibility": "public", "sensitivity": "public", "cosine_distance": 0.42,
    "citation": {"url": "…", "title": "…", "publisher": "…", "published_date": "…",
                 "heading": "…", "evidence_quote": "…"}
  }],
  "message": "Results ranked by cosine distance; lower is closer.",
  "evidence_note": "Citations show what a source states; they do not establish effectiveness."
}
```

- `status: "no_results"` comes with a message suggesting a broader question or fewer filters.
- `cosine_distance` ranks results (lower is closer). It is not a confidence score.
- `visibility: "internal"` marks units from internal Salesforce documents.

## Troubleshooting

| Symptom | Meaning |
|---|---|
| First call takes several seconds | The server is opening its first database connection; later calls take well under a second. |
| `no_results` for everything | The knowledge store may not be loaded yet, or the filters are too narrow. |
| "Knowledge retrieval is unavailable" | The server cannot reach the database. Tell the team. |
| HTTP 421 | The server's allowed-host setting does not include this hostname (a deployment setting). |

Missing a tool you need? Tell the team which question failed. The tool set grows from those
reports.
