
<h1 align="center">
  <br>
  <a href="https://www.bu.edu/spark/" target="_blank"><img src="https://www.bu.edu/spark/files/2023/08/logo.png" alt="BUSpark" width="200"></a>
  <br>
  Salesforce Web-Scraping Knowledge MCP
  <br>
</h1>

<h4 align="center">Scrape public sales content, turn it into cited knowledge units, and serve them to an AI agent through category-specific MCP tools.</h4>

<p align="center">
  <a href="#key-features">Key Features</a> •
  <a href="#how-to-use">How To Use</a> •
  <a href="#project-description">Project Description</a> •
  <a href="#data-locations">Data Locations</a>
</p>

## Key Features

The repo has one folder per pipeline stage, so each owner can work in parallel.
Folders marked *(planned)* do not exist yet.

* `scraper/` - fetch public pages, check robots.txt first (Protego), strip clutter, group text under headings
* `chunking/` - split sections into chunks
  - `character.py` fixed-size baseline, `semantic.py` LangChain semantic chunker, `compare.py` side-by-side report
* `extraction/` *(planned)* - Claude API turns chunks into labeled knowledge units with evidence
* `embed/` *(planned)* - the one embedding model wrapper, shared by the pipeline AND the MCP server
* `db/` *(planned)* - Postgres + pgvector schema (numbered SQL migrations) and upsert loader
* `pipeline/` *(planned)* - SCC batch job scripts that chain the stages
* `mcp_server/` *(planned)* - MCP server on Heroku: auth, shared retrieval, one tool per category
  - may import only `embed/`, `common/` and `db/`, so it can be split into its own repo later
* `eval/` *(planned)* - test questions, expected answers, scoring
* `data/urls/` - URL lists (committed)
* `data/samples/` - small reference outputs from the Oct 8 demo (committed)
* `data/output/` - pipeline run outputs (gitignored)

Internal Salesforce data is never committed. Secrets go in `.env` (see `.env.example`), never in git.

## How To Use

```bash
# Clone this repository
$ git clone https://github.com/BU-Spark/ml-web-scraping-knowledge.git
$ cd ml-web-scraping-knowledge
$ python3 -m pip install -r requirements.txt

# All commands run from the repo root.
# 1. Scrape (writes data/output/sections.json)
$ python3 -m scraper data/urls/demo_seed.txt

# 2. Chunk (reads data/output/sections.json)
$ python3 -m chunking.character 500 50
$ python3 -m chunking.semantic 90 200
$ python3 -m chunking.compare          # then open data/output/comparison.html
```

To try chunking without scraping, copy `data/samples/sections.json` to `data/output/sections.json`.

The code exactly as shown at the Oct 8 demo is preserved at the `oct8-demo` tag (`git checkout oct8-demo`).

### Branches

Create a new branch from dev, add changes on the new branch you just created.

```bash
$ git checkout dev && git pull
$ git checkout -b your-branch dev
```

Open a Pull Request to dev. Add your PM and TPM as reviewers.

At the end of the semester during project wrap up open a final Pull Request to main from dev branch.

## Project Description

In this section, you should include the project description, either from the client or spark.

Please make sure it reflects what you see on the documents (project description) you recieved.

* Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nulla facilisi. Donec vel nunc at libero ultrices tincidunt. Vestibulum ante ipsum primis in faucibus orci luctus et ultrices posuere cubilia curae; Mauris ut ligula nec risus posuere ultricies at et ligula. Pellentesque habitant morbi tristique senectus et netus et malesuada fames ac turpis egestas.
* Veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.

## Data locations

In this section, you should include the location of all of your datasets for the project (if applicable)

<a href="dataset-documentation">Dataset Documentation</a>
* Location 1: [location]
  - [description]
* Location 2: [location]
  - [description]
