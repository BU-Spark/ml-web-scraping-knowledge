# Sales Knowledge Extraction and MCP Retrieval System

BU DS 549 capstone for Salesforce. The current direction is a public sales
best-practice and know-how retrieval system, pending sponsor confirmation.
Public recommendations must not be described as proven seller outcomes.

## Repository structure

```text
sales-knowledge-project/
│
├── README.md
├── requirements.txt
├── .env.example
│
├── data_pipeline/
│   ├── scraper/            # scraper package (see data_pipeline/scraper/README.md)
│   ├── scc/scrape.sh       # SCC batch job for the scraper
│   ├── cleaner.py          # points to the scraper's cleaning code
│   ├── chunker.py
│   ├── extractor.py
│   ├── validator.py
│   ├── deduplicator.py
│   ├── embedder.py
│   ├── uploader.py
│   └── run_pipeline.py
│
├── embed/                  # shared embedding interface (pipeline AND MCP server)
│   ├── __init__.py
│   └── model.py
│
├── prompts/
│   ├── extraction_prompt.txt
│   ├── validation_prompt.txt
│   └── classification_prompt.txt
│
├── schemas/
│   ├── knowledge_unit_schema.json
│   └── metadata_schema.json
│
├── database/
│   ├── schema.sql
│   ├── queries.py
│   └── connection.py
│
├── mcp_server/
│   ├── server.py
│   ├── tools.py
│   ├── retrieval.py
│   ├── filters.py
│   └── ranking.py
│
├── tests/
│   ├── test_chunking.py
│   ├── test_extraction.py
│   ├── test_database.py
│   └── test_mcp_tools.py
│
├── eval/                   # planned: demo questions and scoring
│   ├── README.md
│   └── run_eval.py
│
├── docs/                   # extraction methodology, MCP tool schema (outlines)
│
└── deployment/
    ├── Procfile
    ├── runtime.txt
    └── heroku_notes.md
```

## Setup and implemented commands

Run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
echo "SCRAPER_CONTACT=<team email>" >> .env        # goes in the scraper's User-Agent
python3 -m data_pipeline.scraper parse                 # link file -> manifest
python3 -m data_pipeline.scraper run --category 1,2    # scrape (resumable)
python3 -m data_pipeline.scraper export-sections       # -> data/output/sections.json
python3 -m data_pipeline.chunker 90 200
python3 -m chunking.character 500 50
python3 -m chunking.compare
python3 -m pytest tests
```

The scraper writes one clean JSON doc per page to `data/output/scrape/clean/` plus a source
registry; `export-sections` flattens them into `data/output/sections.json`. Chunkers read it and write
`chunks_semantic.json` or `chunks_character.json` in the same folder. The comparison
also writes `comparison.html`. For an offline character-chunking demo:

```bash
mkdir -p data/output
cp data/samples/sections.json data/output/sections.json
python3 -m chunking.character 500 50
```

Semantic chunking requires the listed LangChain/sentence-transformers dependencies
and downloads its embedding model on first use.

The scraper checks robots.txt with Protego (an unreadable robots.txt counts as blocked),
uses an honest User-Agent with a contact address, waits 3 s between requests to the same
site, caches raw pages, and records a status for every URL (`ok`, `blocked_robots`,
`bot_challenge`, `too_short`, ...). It never works around blocks, paywalls or logins.
Cleaning is heuristic and may leave some promotional content. Full details, output schema
and statuses: `data_pipeline/scraper/README.md`. The Oct 8 demo scraper is at tag `oct8-demo`.

## Architecture and knowledge requirements

SCC batch processing: URLs → scrape → clean → semantic chunks → LLM extraction →
validation/classification/deduplication → embeddings → upload to Heroku Postgres.
Heroku hosts Postgres with pgvector and an authenticated MCP retrieval service.
Salesforce agents query Heroku; they do not need access to SCC.

The three categories are Sales Methodology and Process, Segmentation and Territory,
and Enablement Operations. The source list is `data/urls/public_urls_compiled.txt`
(412 URLs); run reports are in `data/scrape/` (`summary.md`, `scrape_report.csv`).

Knowledge units should be independent, actionable, and traceable to supporting
passages and source URLs. Capture context only when supported; leave unknown values
empty or null. Distinguish practitioner guidance, procedures, research, and case
evidence. A source recommending an action does not establish its effectiveness.
The supplied example knowledge-unit schema and proposed MCP tool names are not yet
final contracts. Preserve source/chunk references for audits and reruns.

Use compatible embedding models for stored knowledge units and incoming queries.
Confirm SCC network requirements, API authorization, database/vector support, and
MCP authentication before implementing those integrations. Internal Salesforce documents
(markdown .txt) are allowed as of Nov 3: ingest them with
`python3 -m data_pipeline.scraper ingest-internal`, keep them in gitignored `data/internal/`
or team-only SCC space, and never commit them. Output docs are marked `visibility: internal`.

## Configuration and collaboration

Secrets belong in approved environment variables or secret management; `.env.example`
contains names only. The code does not automatically load `.env`. Never commit
credentials or internal Salesforce data. Heroku hosting does not itself establish
authentication or authorization.

Work on personal or feature branches based on `dev`. Changes
may be pushed/integrated directly into `dev`; a PR is required from `dev` to `main`.
Do not force-push or include AI co-author lines. The Oct 8 demo remains available at
`oct8-demo`. Keep prompts separate from code and add implementations incrementally.
