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
│   ├── scraper.py
│   ├── cleaner.py
│   ├── chunker.py
│   ├── extractor.py
│   ├── validator.py
│   ├── deduplicator.py
│   ├── embedder.py
│   ├── uploader.py
│   └── run_pipeline.py
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
python3 -m data_pipeline.scraper data/urls/demo_seed.txt
python3 -m data_pipeline.chunker 90 200
python3 -m chunking.character 500 50
python3 -m chunking.compare
python3 -m unittest discover -s tests -v
```

The scraper writes `data/output/sections.json`; chunkers read it and write
`chunks_semantic.json` or `chunks_character.json` in the same folder. The comparison
also writes `comparison.html`. For an offline character-chunking demo:

```bash
mkdir -p data/output
cp data/samples/sections.json data/output/sections.json
python3 -m chunking.character 500 50
```

Semantic chunking requires the listed LangChain/sentence-transformers dependencies
and downloads its embedding model on first use. The previous command
`python3 -m scraper data/urls/demo_seed.txt` still works.

The scraper checks robots.txt, logs processing steps, and skips explicitly disallowed
pages. Its existing behavior continues with a warning when robots.txt is unavailable;
review that policy before running at scale. Cleaning is heuristic and may leave
promotional content. Runs overwrite their output files, including empty results.

## Architecture and knowledge requirements

SCC batch processing: URLs → scrape → clean → semantic chunks → LLM extraction →
validation/classification/deduplication → embeddings → upload to Heroku Postgres.
Heroku hosts Postgres with pgvector and an authenticated MCP retrieval service.
Salesforce agents query Heroku; they do not need access to SCC.

The three categories are Sales Methodology and Process, Segmentation and Territory,
and Enablement Operations. The approximately 388-URL dataset described in the
project brief is not included on this branch; only the demo URL list is present.

Knowledge units should be independent, actionable, and traceable to supporting
passages and source URLs. Capture context only when supported; leave unknown values
empty or null. Distinguish practitioner guidance, procedures, research, and case
evidence. A source recommending an action does not establish its effectiveness.
The supplied example knowledge-unit schema and proposed MCP tool names are not yet
final contracts. Preserve source/chunk references for audits and reruns.

Use compatible embedding models for stored knowledge units and incoming queries.
Confirm SCC network requirements, API authorization, database/vector support, and
MCP authentication before implementing those integrations. Internal seller-specific
knowledge is a future possibility, not an approved current deliverable.

## Configuration and collaboration

Secrets belong in approved environment variables or secret management; `.env.example`
contains names only. The code does not automatically load `.env`. Never commit
credentials or internal Salesforce data. Heroku hosting does not itself establish
authentication or authorization.

Work on personal branches based on `dev` (this restructuring uses `Jen`). Changes
may be pushed/integrated directly into `dev`; a PR is required from `dev` to `main`.
Do not force-push or include AI co-author lines. The Oct 8 demo remains available at
`oct8-demo`. Keep prompts separate from code and add implementations incrementally.
