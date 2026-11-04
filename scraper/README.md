# Scraper

Turns the public link list into clean documents with heading-based sections and full
provenance, plus a source registry that records what happened to every URL.

```
link file -> manifest -> robots.txt + ToS check -> fetch (cached) -> extract (trafilatura)
          -> clean -> quality gates -> data/output/scrape/clean/<doc_id>.json + registry row
```

## Run it (from the repo root)

```bash
pip install -r requirements.txt
echo "SCRAPER_CONTACT=you@bu.edu" >> .env        # goes in the User-Agent; required

python3 -m scraper parse                          # link file -> data/scrape/manifest.jsonl, checks 155/106/127
python3 -m scraper probe --category 1,2           # robots + headers only: what's usable?
python3 -m scraper run --category 1,2 --sample-per-domain 2   # pilot
python3 -m scraper run --category 1,2             # full run (resumable: skips URLs already ok)
python3 -m scraper show <doc_id or url>           # eyeball one clean doc
python3 -m scraper report                         # rebuild scrape_report.csv + summary.md
python3 -m scraper export-sections                # flat data/output/sections.json for chunking/
python3 -m pytest tests/scraper                   # offline tests
```

Useful `run` flags: `--domain x.com`, `--limit N`, `--refetch` (ignore the raw cache and download
again), `--force` (re-process URLs already `ok`, e.g. after changing cleaning rules; uses the cache).

On SCC: `qsub -P <project> pipeline/scc/scrape.sh` (see the script for settings).

## Where things go

| Path | What | In git? |
|---|---|---|
| `data/scrape/manifest.jsonl` | one row per URL: category, section label, also_categories | yes |
| `data/scrape/scrape_report.csv` | registry mirror: status per URL | yes |
| `data/scrape/summary.md` | counts by status x category, failing domains, ToS review list | yes |
| `data/scrape/probe_report.csv` | probe results | yes |
| `$SCRAPER_OUT/raw/` | raw HTML + headers (cache) | no |
| `$SCRAPER_OUT/clean/<doc_id>.json` | clean docs (`ok` only) | no |
| `$SCRAPER_OUT/registry.jsonl` | source registry (source of truth) | no |

`SCRAPER_OUT` defaults to `data/output/scrape` (gitignored). Scraped text is third-party content,
so it stays out of GitHub. On SCC it lives in project space.

`doc_id` is the first 16 hex chars of sha256(normalized URL), so it's the same on every run.

## Clean doc fields

`doc_id, url, final_url, canonical_url, domain, publisher, category, category_name, also_categories,
section_label, title, author, published_date, modified_date, description, language, retrieved_at,
fetch_method, extractor, content_type, word_count, content_sha256, visibility, clean_stats,
sections [{heading, level, text}], text`

`text` is the whole doc as markdown (`# Title`, `## Heading`, ...). Section text keeps list items as
`- ` lines and table rows as `a | b` lines. `visibility` is always `public` for now.

## Statuses

| status | meaning |
|---|---|
| `ok` | clean doc written |
| `blocked_robots` | robots.txt disallows us, or couldn't be read (403/5xx/timeout = treated as blocked) |
| `blocked_tos` | skipped in `domains.yaml` (terms of service) |
| `timeout` / `fetch_error` | no response (after retries) |
| `http_error` | 4xx/5xx |
| `bot_challenge` | CAPTCHA / Cloudflare-style challenge; never bypassed |
| `redirected_away` | dead link that now redirects to a home/hub page |
| `non_html_skipped` | PDF or other non-HTML (PDFs skipped for the MVP) |
| `paywall_or_login` | login redirect, or paywall/login phrases with little text |
| `js_required_failed` | page needs JavaScript (no Playwright fallback yet) |
| `too_short` | under 150 words after cleaning |
| `non_english` | declared or detected non-English |
| `duplicate_content` | same text or canonical URL as `duplicate_of` |
| `error` | unexpected exception; reason has the message, the run log has the traceback |

## Domain overrides

Edit `scraper/domains.yaml` (keys are hostnames without `www.`; they also match subdomains):

```yaml
example.com:
  skip: true            # never fetched -> blocked_tos. Ask the team before adding one.
  reason: "Terms forbid automated access"
other.com:
  tos_reviewed: true    # someone read the terms; drops it from the review list in summary.md
  delay: 10             # seconds between requests to this host
```

## Tuning

Thresholds (min words, delays, retries) and the boilerplate patterns are in `scraper/config.py`.
After changing them, `run --force` re-processes from the raw cache without re-hitting any site.

## Politeness rules

Honest User-Agent with a contact address; robots.txt checked with Protego (including rules for our
bot name and Crawl-delay); one request at a time per host, 3 s apart by default; retries only for
429/5xx with backoff and `Retry-After`; no cookies, no logins, no working around paywalls or blocks.

## Internal documents (`ingest-internal`)

Internal knowledge arrives as markdown `.txt` files. They are not scraped; this command turns them
into the same clean-doc format, marked `visibility: "internal"`, so chunking and extraction treat
them like any other doc and access control can filter them later.

**Do not put real internal files anywhere until the team has written confirmation from the client.**
Build and demo with the synthetic sample instead.

```bash
# Synthetic sample (committed, invented data)
python3 -m scraper ingest-internal --dir data/samples/synthetic_internal

# Real files: a folder git can't see
INTERNAL_DIR=/projectnb/<project>/internal INTERNAL_OUT=/projectnb/<project>/internal_out \
  python3 -m scraper ingest-internal
```

Input folder: `*.txt` files in this layout (see `data/samples/synthetic_internal/role_glossary_header_format.txt`):

```
TITLE LINE (no #)
Knowledge category: Segmentation and territory (SMB, Commercial, Enterprise)
Provenance: where the data came from
Tags: [INFERRED] = ... [UNKNOWN] = ...
any other intro lines

## SECTION HEADING (shared suffix)
- [INFERRED] bullet text ...
```

- The header (everything before the first `##`) gives the title, category (matched by name to
  1 / 2 / 10), provenance and tag legend. Other intro lines become an untitled first section.
- A `(...)` suffix that every heading shares (e.g. `(Salesforce internal, Org62)`) is removed from
  the headings and stored once as `heading_suffix`.
- `[IN TITLE]` / `[INFERRED]` / `[UNKNOWN]` tags stay in the text (extraction needs them) and are
  counted in `confidence_tags`.
- `metadata.csv` is optional (`file,title,category,sensitivity,owner,doc_date,notes`). When a row
  exists it overrides the header. A file with no category anywhere is flagged `missing_metadata`.
- `sensitivity` is `internal` or `confidential`; **if not given it defaults to `confidential`**
  (most restrictive), never to public.

Output: `$INTERNAL_OUT/clean/<doc_id>.json` and `$INTERNAL_OUT/registry.jsonl`, kept apart from
public docs. Clean docs have `url: null`, `source_file`, `visibility`, `sensitivity`, and
`publisher: "Salesforce (internal)"`. Statuses: `ok`, `missing_metadata`, `bad_metadata`,
`bad_encoding`, `too_short` (< 20 words), `duplicate_content`.

Safety built in:
- Refuses to run if the input or output folder is inside the repo and not gitignored
  (defaults `data/internal/` and `data/output/internal/` are both gitignored).
- Logs file names, ids and counts only, never document text.
- Web clutter rules are off, so lines like "Contact sales ops" are kept.
- `doc_id` comes from the file name, so editing a file updates its doc; removing a file removes
  its clean doc on the next run.
