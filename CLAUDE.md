# Project guidance — current direction

The user's latest onboarding brief and README supersede earlier planning notes.
This repository is the BU DS 549 Salesforce Sales Knowledge Extraction and MCP
Retrieval System. Scope: public sales best practices and know-how, plus internal
Salesforce documents supplied by the client (confirmed allowed Nov 3; see "Internal data"
below). Do not invent seller experiences, performance gains, or context.

## Architecture and layout

- SCC runs batch processing in data_pipeline/: scrape, clean, chunk, extract,
  validate, deduplicate, embed, upload. No retrieval server runs on SCC.
- prompts/ holds LLM prompt text; schemas/ will define record contracts.
- database/ will contain Postgres/pgvector schema, connections, and queries.
- mcp_server/ will serve authenticated retrieval on Heroku to Salesforce agents.
- deployment/ contains explicitly non-deployable scaffolding and notes.
- data_pipeline/scraper/ is the scraper (package): link file -> robots/ToS check -> polite
  fetch (cached) -> trafilatura extraction with headings -> clean -> quality gates -> one clean
  doc JSON per page + a source registry. Also `ingest-internal` for internal .txt files.
  Run `python3 -m data_pipeline.scraper <parse|probe|run|report|show|export-sections|
  ingest-internal>`; details in data_pipeline/scraper/README.md. data_pipeline/cleaner.py
  points to its cleaning code; data_pipeline/scc/scrape.sh is the SCC batch job.
- chunking/ retains existing algorithms and comparisons (data_pipeline/chunker.py points to it).
- data/urls/public_urls_compiled.txt is the source list (412 URLs, categories 1, 2, 10).
  data/scrape/ holds the manifest and run reports (URLs and statuses only). Scraped page text
  and internal files are gitignored (data/output/, data/internal/); on SCC they live in
  team-only project space. Last full run (Nov 3): 356/412 usable.
- Only scraping, cleaning, internal ingest, and chunking are implemented. Other requested
  files are labeled placeholders. Do not describe them as functioning services or validation.

Keep source URLs, titles, headings, supporting passages, and processing references.
Distinguish evidence that a source recommends an action from evidence of effectiveness.
Unknown fields remain null/empty. Final schemas, LLM provider, embedding model,
MCP interfaces, SCC configuration, and Heroku security require confirmation.
Use the same compatible embedding model during ingestion and query processing.

## Working rules

Prefer small, independently testable Python stages. Preserve useful existing code.
Explain significant architectural changes. Never commit credentials or internal
Salesforce data; use approved environment variables or secret management. Do not
bypass website access restrictions (robots.txt, bot challenges, paywalls: log and skip).
Heroku hosting alone is not access control. No database changes or deployments without
authorization.

## Internal data

Allowed as of Nov 3 (Nora confirmed with the client; keep the written confirmation on file).
Internal files are markdown .txt; ingest with `python3 -m data_pipeline.scraper ingest-internal`.
Store them only in gitignored data/internal/ locally or a team-only SCC folder. Never commit
them, copy real internal text into code, tests or samples, or log it. Output docs carry
`visibility: internal` and `sensitivity` (default confidential) for access control; keep
[INFERRED]/[UNKNOWN] tags as low-confidence. Tests use data/samples/synthetic_internal/.

Branch from dev (personal or feature branches). Direct integration into dev is permitted;
PRs are required for dev into main. Never force-push. Confirm
commit messages with the user before committing. No AI co-author lines.

Run modules from the repository root; see README for commands and current limitations.
Run tests with `python3 -m pytest tests` (runs both unittest and pytest-style tests).
