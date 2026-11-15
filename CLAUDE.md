# Project guidance — current direction

BU Spark! DS 549 (Fall 2026): Salesforce Sales Knowledge Extraction and MCP Retrieval System.
A pipeline scrapes public web pages, extracts discrete labeled **knowledge units** (not raw
chunks), embeds them, and serves them through an **MCP server with category-specific tools** that a
Salesforce agent can call. Scope: public sales best practices and know-how, plus internal
Salesforce documents supplied by the client (see "Internal data"). Do not invent seller
experiences, performance gains, or context.

- Client: Salesforce. Brian Floyd (day-to-day), Shawn Waterman (Director of Product Management).
- Team: Nora Amer, Tony Wu, Jennifer (Qiyue) Hu, Aaliyah Aman.
- Categories (client numbering): **1** Sales methodology and process, **2** Segmentation and
  territory (SMB / commercial / enterprise), **10** Enablement operations.

## Current priority (Meeting 5, Nov 5)

**A public MCP endpoint Brian can connect an agent to, by the Nov 19 meeting**, with callable tools
and clear setup/usage instructions. A working proof of concept beats polish.
Next: Nov 19 end-to-end + MCP · Dec 3 finalization · Dec 11 Demo Day · Dec 18 deliverables due.

Client decisions:
- Hosting is our choice; the vector DB does not need to be on Heroku. Pick what ships fastest and
  is maintainable.
- No login, personalization or role-based access (Nov 5; confirmed Nov 10).
- The internal docs we have are enough; no more are coming. Focus on public sources.
- UCL (Salesforce's insight system) integration is on hold.
- Tools grow over time (Brian finds missing ones when calls fail). Start with the core set.
- Keep categories broad and reusable. Stretch: add a category and auto-discover public links for it.
- Document the workflow, key terms and category definitions (a deliverable).

## Pipeline status (checked Nov 14)

| Stage | Status | Where |
|---|---|---|
| Scrape | Done. Last full run Nov 3: 356/412 usable; 56 failed (20 robots, 16 bot challenge, 7 HTTP, 6 too short, 3 redirect, 2 duplicate, 1 paywall, 1 PDF). | dev, `data_pipeline/scraper/`, `data/scrape/summary.md` |
| Chunk | Done. Heading sections, then SemanticChunker inside each; keeps metadata, access labels, offsets. | dev, `data_pipeline/chunker.py`, `docs/chunking.md` |
| Extract / filter / validate / embed | Written, being refined. Claude API, forced tool use, temperature 0. Validation has no LLM: schema check, evidence quote must appear verbatim in its chunk, unit URL must match chunk URL. Pilot: 15 chunks → 39 units → 29 kept. | `origin/Tony`, `origin/Aaliyah` only; **not in dev** (dev still has placeholders) |
| Shared embedding | `all-MiniLM-L6-v2`, 384 dims, normalized. Shared implementation now on Jen; model override is rejected unless it matches migration 001. | `embed/model.py` |
| Store | Schema, migration runner and loader merged into dev (`97406cb`); shared deployment/application not verified. | `database/migrations/001_init.sql`, `database/migrate.py`, `data_pipeline/uploader.py` |
| MCP server | Nine tools implemented on Jen with Streamable HTTP, cited retrieval and source lookup; local protocol tests only, not deployed. Audit/scoring use explicitly limited lexical methods. | `mcp_server/`, `database/queries.py`, `docs/mcp_tool_schema.md` |

Storage contract: DB categories are names without numeric prefixes. The loader converts pipeline
numbers/slugs/prefixed names to these names. Chunk `section_id` is text; unit `section_id` is the
integer section index. MCP reads the `served_units` view and its effective access labels.

## Architecture and layout

- SCC runs batch processing in data_pipeline/: scrape, clean, chunk, extract, validate,
  deduplicate, embed, upload. SCC has outbound internet but no persistent storage, so results go
  to an external store. No retrieval server runs on SCC.
- prompts/ holds LLM prompt text; schemas/ defines record contracts.
- database/ holds the Postgres/pgvector migrations (`python3 -m database.migrate`), connection and
  queries. The MCP server serves public and internal units (see "Internal data").
- mcp_server/ serves retrieval to Salesforce agents over HTTP (remote-reachable, not stdio-only),
  built with the Python MCP SDK. It may import only embed/, database/ and schemas/, never
  data_pipeline/, so it can be split off or handed over later. No auth, so anyone with the URL can
  query it.
- embed/ is the shared embedding interface used by BOTH data_pipeline/embedder.py and
  mcp_server/. Questions must be embedded with the same model as stored units.
- eval/ (planned): demo questions and scoring. docs/: required write-ups.
- deployment/ contains explicitly non-deployable scaffolding and notes.
- data_pipeline/scraper/ is the scraper (package): link file -> robots/ToS check -> polite
  fetch (cached) -> trafilatura extraction with headings -> clean -> quality gates -> one clean
  doc JSON per page + a source registry. Also `ingest-internal` for internal .txt files.
  Run `python3 -m data_pipeline.scraper <parse|probe|run|report|show|export-sections|
  ingest-internal>`; details in data_pipeline/scraper/README.md. data_pipeline/scc/scrape.sh is
  the SCC batch job.
- chunking/ retains algorithms and comparisons. See docs/chunking.md.
- data/urls/public_urls_compiled.txt is the source list (412 URLs, categories 1, 2, 10).
  data/scrape/ holds the manifest and run reports (URLs and statuses only). Scraped page text and
  internal files are gitignored (data/output/, data/internal/); on SCC they live in team-only
  project space.
- Heroku: app `bu-research` (fr-agent team), Postgres Essential-0, `DATABASE_URL` config var.
  Heroku is available but not required. pgvector status there is unverified.

## MCP tools (list approved by Brian)

Core, build first: `get_sales_methodology`, `get_segmentation_guidance`,
`get_enablement_practices`, `get_source`.
Later: `get_objection_handling`, `compare_approaches`, `map_value_drivers`,
`audit_messaging_alignment`, `score_adherence_metric`.

- Filter by category (and entity/topic where useful), then vector search.
- Return short, structured results with citations (source URL, publisher, date, evidence quote).
- Return a helpful message when there are no results, not an empty list.
- Entity matching is weak: normalize names and add aliases (e.g. "MEDDIC" vs "MEDDICC").

## Terms (from the client's UCL deep-dive; use these exactly)

- **Common sense**: a familiar assumption that needs evidence in this situation.
- **Content**: information to read or look up (help text, training, playbooks).
- **Know-how**: a practical way to do something.
- **Knowledge**: evidence-backed experience of what works, for whom, and when.
- **Insight**: an evidence-backed explanation of *why* a behavior happens. Out of scope.

With public data, "evidence" means *a source said this* (a citation), not *this was proven to
work*. Don't label units as proven practice. Distinguish a source recommending an action from
evidence of effectiveness. Keep source URLs, titles, headings, supporting passages, and processing
references. Unknown fields remain null/empty.

## Internal data

Allowed as of Nov 3 (Nora confirmed with the client; keep the written confirmation on file).
Brian says it isn't confidential, but it is low priority and no more is coming. Internal files are
markdown .txt; ingest with `python3 -m data_pipeline.scraper ingest-internal`. Store them only in
gitignored data/internal/ locally or a team-only SCC folder. Never commit them, copy real internal
text into code, tests or samples, or log it. Records keep `visibility: internal` and
`sensitivity` (default confidential); keep [INFERRED]/[UNKNOWN] tags as low-confidence.
Tests use data/samples/synthetic_internal/.
Serving rule (user decision, Nov 14): the endpoint is for Brian, so internal units are served like
public ones and may be loaded to the hosted DB. Results keep their `visibility`/`sensitivity`
labels so internal sources are identifiable. Still never commit internal text to git.

## Working rules

- Branch from dev. Pushing directly to dev is allowed; PRs are required for dev into main.
  Never force-push. Confirm commit messages with the user before committing. No AI co-author lines.
- No secrets in code: API keys and DB URLs come from env vars / `.env` (gitignored).
- Respect robots.txt and ToS. Never get around a block, paywall, login or bot challenge (log and
  skip). close.com is skipped (ToS).
- Ask before deleting files, changing the link list, or touching shared infrastructure (Heroku,
  the shared DB). No database changes or deployments without authorization.
- Prefer small, independently testable Python stages. Preserve useful existing code. Keep it
  simple: the user wants to understand the tech, so explain choices in plain terms with a one-line
  "why", and show real output (sample units, query results) at checkpoints.
- Run modules from the repository root. Run tests with `python3 -m pytest tests`.

## Open questions (ask the user; don't guess)

- Final host for the MCP server and vector DB.
- Which unit format is standard for `category` and `section_id`.
