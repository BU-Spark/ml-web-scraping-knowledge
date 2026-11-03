# Project guidance — current direction

The user's latest onboarding brief and README supersede earlier planning notes.
This repository is the BU DS 549 Salesforce Sales Knowledge Extraction and MCP
Retrieval System. Current scope: public sales best practices and know-how, pending
sponsor confirmation. Experience-backed/internal seller knowledge is not an approved
current deliverable. Do not invent seller experiences, performance gains, or context.

## Architecture and layout

- SCC runs batch processing in data_pipeline/: scrape, clean, chunk, extract,
  validate, deduplicate, embed, upload. No retrieval server runs on SCC.
- prompts/ holds LLM prompt text; schemas/ will define record contracts.
- database/ will contain Postgres/pgvector schema, connections, and queries.
- mcp_server/ will serve authenticated retrieval on Heroku to Salesforce agents.
- deployment/ contains explicitly non-deployable scaffolding and notes.
- chunking/ retains existing algorithms and comparisons; scraper/ preserves the old
  entry point. Data samples and URL lists remain under data/; outputs are gitignored.
- Only scraping, cleaning, and chunking are implemented. Other requested files are
  labeled placeholders. Do not describe them as functioning services or validation.

Keep source URLs, titles, headings, supporting passages, and processing references.
Distinguish evidence that a source recommends an action from evidence of effectiveness.
Unknown fields remain null/empty. Final schemas, LLM provider, embedding model,
MCP interfaces, SCC configuration, and Heroku security require confirmation.
Use the same compatible embedding model during ingestion and query processing.

## Working rules

Prefer small, independently testable Python stages. Preserve useful existing code.
Explain significant architectural changes. Never commit credentials or internal
Salesforce data; use approved environment variables or secret management. Do not
bypass website access restrictions. Heroku hosting alone is not access control.
No database changes, deployments, or internal ingestion without authorization.

Branch from dev. Personal branch for this update: Jen. The user permits direct
integration into dev; PRs are required for dev into main. Never force-push. Confirm
commit messages with the user before committing. No AI co-author lines.

Run modules from the repository root; see README for commands and current limitations.
