# CLAUDE.md: Salesforce Web-Scraping Knowledge MCP (Spark! DS549, Fall 2026)

Context for Claude Code. Compiled Oct 27, 2026 from the project brief, client meeting notes 1-3,
client decks, and planning chats through Oct 26. Items marked **[suggested]** were proposals, not
confirmed team or client decisions. **[unverified]** means not checked against a source.
Update this file when decisions change.

---

## 1. What we are building

A knowledge pipeline plus an MCP server that gives a Salesforce-aware AI agent reliable, cited
knowledge. Public web content is scraped, turned into discrete labeled **knowledge units** (not just
chunked text), embedded, stored, and served through **category-specific MCP tools** (not one generic
search tool). A second goal is to combine this with authorized Salesforce internal knowledge so the
agent can say how Salesforce aligns with or differs from public practice, while keeping internal
content protected.

Example use case (from kickoff): field readiness, a "virtual salesperson" for people who need sales
knowledge but cannot always reach a rep. Answers should explain sales generally and emphasize
Salesforce's own steps and priorities where relevant.

**Deliverables (brief):** scraping pipeline; knowledge-extraction layer; vectorized RAG-ready
library; MCP server with multiple category-scoped tools (at least two by Milestone 4);
documentation of extraction methodology and MCP tool schema; agent demo.

**Knowledge categories (numbering from Brian's Slack list):**
1. Sales methodology and process: public = MEDDICC, Challenger, SPIN, Command of the Message, BANT.
   Salesforce layer = internal stage definitions, qualification criteria, inspection cadences.
2. Segmentation and territory (SMB, commercial, enterprise): public = segment sales motions and
   posted ranges. Salesforce layer = employee-count bands, routing/overlap rules, team ownership,
   exceptions. Sub-areas: segment definitions, selling motions, coverage models, roles/title
   families (incl. non-AE sellers), territory design, ownership and routing, capacity, competitor
   comparison. Treat headcounts as rough popularity signals, not current totals.
10. Enablement operations: public = content, training, coaching, measurement frameworks.
    Salesforce layer = internal program structure, readiness metrics, certification paths.

**Segmentation is the first and demo-focus category.**

## 2. People and dates

- Client: Salesforce. **Brian Floyd** (Sr. Manager, Productivity Innovation) is day-to-day contact.
  Shawn Waterman (Director of Product Management).
- Team (4): Nora Amer, Tony Wu, Jennifer (Qiyue) Hu, Aaliyah Aman. Spark! staff: Reese Stichter (PM),
  Sai Chava (TPM), Justin Lim (program lead).
- Ownership split by pipeline stage [suggested]: Sources & Scraping, Extraction, Data Platform,
  MCP & Agent. Names per stage not recorded here; fill in.
- Key dates: **Nov 5 midpoint** check-in (demo extraction pipeline turning pages into units);
  Thanksgiving Nov 23-29 off; **Dec 11 final live demo** (Demo Day 4-7pm); Dec 18 final deliverables.
- Plan target [suggested]: thin end-to-end slice for segmentation only (scrape -> extract ->
  store -> MCP tool -> agent answer with citations) working by **Fri Oct 30**, shown at midpoint.
  After midpoint: other categories, Heroku hosting with auth, then the internal-data layer.

## 3. Architecture (current direction)

```
SCC batch jobs (BU Shared Computing Cluster)            Heroku (app: bu-research, Salesforce-owned)
  scrape (robots.txt check)                              Postgres + pgvector
  -> clean/extract text                                   (units, sources, chunks, logs, evals)
  -> semantic chunking                        write ->          ^
  -> Claude API extraction -> labeled units                     | query
  -> embed (same model as server)                         MCP server (Python MCP SDK)
                                                            auth -> per-user access -> category tools
                                                                 -> agent gets short cited answers
```

- **SCC** = compute only (outbound internet works for scraping and Claude API). **No persistent
  storage**, and BU restricts running servers on cluster nodes; jobs end (12h default) and outside
  users can't reach it. So SCC does batch work only and writes results to Heroku.
- **Storage:** Heroku Postgres + pgvector. Moved from ChromaDB -> Qdrant -> pgvector. pgvector is fine
  at our scale (thousands of units) and Postgres also holds sources, chunks, refresh history,
  evals, logs.
- **Serving:** the **whole MCP server runs on Heroku** (Brian approved Oct 19: the more on
  Salesforce-owned domains, the less security worry, and easier later migration).
- **The MCP server lives in this repo** (decided Oct 27), in `mcp_server/`. It may import only
  `embed/`, `common/` and `db/`, never pipeline stages, so it can be split into its own repo later
  (e.g. if Salesforce wants it handed over). Heroku deploy stays lean via a server-only root
  `requirements.txt` plus `.slugignore` [suggested, not set up yet].
- **Agent-based design was discussed and dropped.**

### Pipeline details
- Scraping: requests/BeautifulSoup, Playwright for JS-heavy pages, **Protego** for robots.txt,
  trafilatura for main-text extraction. Strip nav, footers, newsletter prompts; group text under
  headings.
- Chunking: semantic chunking (LangChain semantic chunker with a small local embedding model).
  Uses a tunable similarity threshold. Headings act as boundaries.
- Extraction: Claude API turns chunks into labeled units with fields: `category`, `entity`,
  `evidence` sentence, `source_url`, `confidence` (plus the unit text). Keep units grounded in an
  evidence sentence.
- Embedding: **bge-m3** (~2 GB RAM) was in use; a smaller model (e.g. bge-small) is suggested for the
  hosted server. **SCC and the server must use the same embedding model**, because the server embeds
  each incoming question (model runs in the MCP process, or swap to an embedding API).
- Source quality: prototype uses high-ranking results among roughly the first ~20 search results;
  cross-check claims across sources; flag unsupported single-source outliers. Long term: discover
  sources from a user-provided topic. Brian can provide seed URLs.

### MCP tools
- One tool per category (e.g. segmentation, sales methodology, enablement). Pattern: filter by
  category and entity, then vector-search. The brief's example names: `get_competitive_advantages`,
  performance data.
- Return structured, short results **with citations**; return a helpful message on empty results.
- Weak spot: entity matching. Normalize names / add an alias table.
- Answers should say whether they rely on public or internal sources.

### Access control (required for hosted MCP)
- Must authenticate users and enforce per-user access: separate Salesforce users from external
  users; internal data only for authorized users.
- **Authorization happens before retrieval**, so confidential content never reaches the model for
  an unauthorized user. Vector similarity is not permission.
- Enforce in the tool layer. Keeping internal data in a separate store/table behind separate tools
  [suggested]. Simple access tiers (public / internal) and personal access keys [suggested].
- Brian's design ideas (guidance, not final): audience profile (role, segment, tenure, employment
  status); units tagged by sensitivity (public / internal / confidential) and depth (beginner /
  practitioner / expert). Access permission is separate from explanation style.
- **Open:** how Salesforce user identity/role is obtained. Brian has not answered yet.

## 4. Heroku

- App `bu-research` on Salesforce's fr-agent team (US, heroku-24).
  URL: https://bu-research-7dc3f331235a.herokuapp.com/  Git: https://git.heroku.com/bu-research.git
- Postgres Essential-0 (1 GB), Postgres 18.3, started empty. `DATABASE_URL` is set as a config var.
  No web dyno yet (as of Oct 15).
- Access is via a regular Heroku account (not Salesforce SSO) with 2FA. Teammates need to be added.
- Sizing [suggested]: Standard-2X dyno (~$50/mo) with a small embedding model; bge-m3 would need
  ~Performance-M (~$250/mo); avoid Eco (sleeps); consider Essential-1 (10 GB) for logs/sources.
- **To verify:** pgvector enabled (`CREATE EXTENSION vector;`), whether SCC IPs need allowlisting,
  an SCC -> Heroku write test, dyno size for the embedding model, whether the server's embedding
  model fits Heroku's slug size limit.
- Dev path [suggested]: GitHub is the code home; teammates may run the MCP server locally against
  Heroku Postgres with a read-only login during development; the hosted server is the real target.

## 5. Current status (as of Oct 27)

- **Oct 8 demo:** scraper (URL -> robots.txt check -> download -> clean -> group by heading) and a
  chunking comparison on one Salesforce blog article ("A Beginner's Guide to the 7 Steps of the Sales
  Process"). Fixed-size (500 chars, 50 overlap) vs semantic: both ~480 chars average; fixed-size cut
  every chunk mid-sentence and 47% mixed two sections; semantic did neither. **Caveat:** fixed-size
  ran on the whole article, semantic one section at a time, so the section result partly reflects
  using headings as boundaries. One article, one setting, measures structure not answer quality.
  The exact demo code is preserved at git tag **`oct8-demo`**; the `Demo` branch is frozen.
- **Public URL lists (Oct 21-22):** links were gathered with AI assistants and compiled into
  `public_urls_compiled.txt` (deduplicated, category labels and comments kept) plus
  `sources_by_category.txt`. `data/urls/public_urls_compiled.txt` is committed (Nov 3); the
  per-category file is not. 388 links total:
  - Cat 1 sales methodology: 155 links from 8 domains, heavily concentrated
    (forcemanagement.com 80, trailhead 17, meddicc.com 15, huthwaiteinternational.com 13,
    salesforce.com 13, challengerinc.com 7, handbook.gitlab.com 7, blog.hubspot.com 3).
  - Cat 2 segmentation: 106 links from 52 domains (salesforce.com 19, gitlab handbook 7, sec.gov 6,
    alexandergroup.com 6, trailhead 5, hubspot 5, plus census.gov, sba.gov, bls.gov, etc.).
  - Cat 10 enablement: 127 links from 55 domains (gartner, trainingindustry, salesenablementcollective
    8 each; forrester 6; mckinsey 5; chieflearningofficer 5; ...).
  - Note: some of these (Gartner, Forrester, SEC filings) may be paywalled, PDFs or poor scraping
    targets; check before relying on them.
- **Production scraper (Nov 3, `feature/scraper`):** `python3 -m scraper parse|probe|run|report|show|
  export-sections`; see `scraper/README.md`. Page text goes to `$SCRAPER_OUT` (gitignored; SCC project
  space), manifest and reports to `data/scrape/`. UA contact comes from `SCRAPER_CONTACT` in `.env`.
  PDFs skipped for the MVP; sec.gov filings trimmed to the business item. Pilot (cat 1-2, 2 URLs per
  domain): 56/73 usable. Blocked/bot-challenged sites are logged and skipped, never worked around.
- A 46-item backlog and week-by-week plan exist in a shared plan doc (not in this repo).
- Not yet built: extraction prompt, DB schema, full SCC pipeline (only `pipeline/scc/scrape.sh`), MCP server, evaluation set,
  shared record shapes (`common/records.py`), shared embedding wrapper (`embed/model.py`).

## 6. Rules and constraints (follow these)

- **Respect robots.txt and site terms.** Check with Protego before fetching. If a site disallows
  automated access or its ToS forbids it (some forbid AI training, e.g. Close.com; OpenStax blocks
  some bots on book paths), **log it and skip; never work around blocks.** Rate-limit politely and
  set an honest user agent.
- **Data scope conflict is unresolved.** The brief says public web pages only and no proprietary
  client data, yet also lists internal knowledge as a goal and "public & private layers". Brian
  shared curated samples and approved Claude API processing for them, but written scope
  confirmation is pending. **Do not ingest, commit, or store internal Salesforce data until the team
  confirms it is allowed.** Fallback: demo access control on a clearly labeled synthetic internal
  sample (would live in `data/samples/synthetic_internal/`). `data/internal/` is gitignored.
- **Never commit secrets:** `DATABASE_URL`, `ANTHROPIC_API_KEY`, Heroku credentials, access keys.
  Use env vars / `.env` (gitignored; see `.env.example`) / Heroku config vars.
- Keep a source registry: every scraped page logged with URL, fetch time, robots/ToS status, and
  whether it was used, so provenance and citations are traceable.
- Reruns must not create duplicate units (upsert by a stable key, e.g. hash of source_url + text).
- Demo focus is **text-heavy blog/article sources**, not textbooks, PDFs or Trailhead modules.

## 7. Open questions and risks

| Item | Status / fallback |
|---|---|
| Internal data allowed under the brief? | Ask for written confirmation; synthetic sample fallback |
| How Salesforce user identity/role is supplied for auth | Asked Brian; unanswered |
| SCC -> Heroku Postgres connectivity (IP allowlisting) | Test early; fallback: load step from laptop or GitHub Actions |
| Embedding model / dyno size | bge-small on both sides, or a hosted embedding API |
| Extraction quality | Narrow to blogs, tighten prompt, keep only units with evidence |
| Demo questions + expected answers for segmentation | To choose; no numeric KPIs agreed |
| Sales-process and enablement example data | Pending from Brian |
| Source licensing/ToS | Not verified for any site |
| Brief also asks how to keep data current as pages change | Refresh/re-check is a stretch goal |
| Will Salesforce take over the MCP server code? | Ask Brian; affects whether it splits into its own repo |

KPIs proposed (no targets set): accuracy (F1 on extraction and tool routing), time saved vs current
methods, adoption (users, queries).

## 8. How to work with me (the user)

- I want to understand the technology deeply: explain in plain terms, briefly say *why* for choices.
- Keep solutions focused; don't over-engineer. Prefer the simplest thing that works for the demo.
- Mark assumptions clearly and ask before decisions that are hard to reverse (schema changes on the
  shared Heroku DB, deleting data, deploying, anything touching internal data).
- Python. Prefer small, testable modules per pipeline stage so the four owners can work in parallel.
- **No AI co-author lines** on commits or PRs in this repo (no `Co-Authored-By: Claude`, no
  "Generated with Claude Code").

## 9. Repo layout and git workflow

Run everything from the repo root with `python3 -m <package>` (see README). Folders marked
(planned) don't exist yet; create them when the stage is started.

```
scraper/        links/policy/fetch/extract/clean/quality/registry modules; domains.yaml; README.md
tests/          offline pytest suites (tests/scraper/)
data/scrape/    scraper manifest + reports (committed; no page text)
chunking/       character.py baseline, semantic.py, compare.py + utils.py
common/         (planned) config.py for env vars, records.py = Section/Chunk/Unit contracts
extraction/     (planned) Claude prompt + unit schema + validation
embed/          (planned) shared embedding model wrapper (used by pipeline AND server)
db/             (planned) migrations/NNN_*.sql, connect, load/upsert
pipeline/       (planned) run.py chaining stages; scc/ job scripts
mcp_server/     (planned) tools/ per category, retrieval.py, aliases.py, auth.py
eval/           (planned) questions, expected answers, scoring
docs/           (planned) extraction methodology, MCP tool schema, architecture
data/urls/      URL lists (committed)
data/samples/   small reference outputs (committed)
data/output/    pipeline run outputs (gitignored)
```

- Stages pass data as files of records (Section -> Chunk -> Unit); changing a record's fields
  affects the next stage's owner, so tell the team.
- Git: branch from `dev`, PR into `dev` (PM + TPM as reviewers); `dev` -> `main` PR at milestones
  and at wrap-up. `Demo` is frozen; `oct8-demo` tag marks the Oct 8 demo code.
- `requirements.txt` currently holds pipeline deps. When the MCP server is added, split into a
  server-only root `requirements.txt` (Heroku installs from it) and `requirements-pipeline.txt`.
