# Semantic chunking

Implemented on top of the existing LangChain SemanticChunker, HuggingFaceEmbeddings,
and Sentence Transformers design. `data_pipeline/chunker.py` handles inputs, metadata,
size limits and output. `chunking/semantic.py` retains the splitting algorithm and
old demo APIs. The character baseline and comparison tool remain available.

## Run

```bash
# Public clean documents, without the metadata loss of export-sections:
python3 -m data_pipeline.chunker --input data/output/scrape/clean

# Internal input is explicit and writes to a separate output:
python3 -m data_pipeline.chunker --input data/output/internal/clean \
  --output data/output/chunking/internal_chunks.json

# Public sample (old section format):
python3 -m data_pipeline.chunker --input data/samples/sections.json \
  --output data/output/chunking/demo_public_chunks.json

# Model/settings are configurable; CPU is the default:
python3 -m data_pipeline.chunker --input /projectnb/PROJECT/scrape/clean \
  --output /projectnb/PROJECT/chunking/public.json \
  --threshold 90 --min-chunk-chars 200 --max-chunk-chars 2000 \
  --model all-MiniLM-L6-v2 --device cpu --batch-size 32
```

Without --input, the runner uses `$SCRAPER_OUT/clean`, defaulting to
`data/output/scrape/clean`. Repeat --input to select multiple directories/files;
public and internal data are not automatically combined. The previous positional
syntax `python3 -m data_pipeline.chunker 90 200` still reads exported
`data/output/sections.json`; output uses the new chunking subdirectory.
The chunker reads environment variables, not .env; export CHUNK_EMBED_MODEL or use
--model. First use downloads the model; HF_HOME can select a local cache.

## Record contents

- `schema_version`, stable `chunk_id`, source `doc_id`, section/chunk indexes.
- Original `text`, `start`, `end`, `offset_reference: section.text`, character and
  whitespace-delimited word counts. `text == source.sections[section_index].text[start:end]`.
- Source URL/file, title, heading and level, heading ancestry when levels exist,
  domain, primary/secondary categories, visibility and sensitivity.
- Provenance and the source's other document metadata under `source_metadata`,
  including dates, content hash, tag legend, confidence counts, and heading suffix
  when provided by the source. `source_path` locates the input artifact.
- `tags` contains only explicit `[INFERRED]`, `[UNKNOWN]`, `[IN TITLE]` markers
  occurring in this chunk, normalized to INFERRED, UNKNOWN, IN_TITLE. Text is unchanged.
  Whole-document confidence counts remain source metadata; they are not assigned to
  every chunk. Topic, role, segment, stage, action, evidence type and effectiveness
  classifications belong to later extraction and are not invented here.
- Section/chunk SHA-256 hashes, model/settings, installed package versions, and
  `size_limited` indicating that the character ceiling required a safety split.

IDs are deterministic for the same document ID, section position/content and span.
Reordering documents or changing machine paths does not change chunk IDs. Editing
or reordering sections can change IDs. A future uploader must handle superseded
chunks when a source changes; chunking does not perform database deletion/upserts.

The output is a JSON array. A sibling `.summary.json` reports document/chunk counts,
visibility counts, sizes, safety-split counts, settings and run time. Logs show
counts and IDs, never document passages. Input/alignment errors return failure;
chunks are written after all documents succeed, using a temporary-file replacement.
Empty input/output does not overwrite a previous result. Concurrent runs should use
separate output filenames. Summary and chunk replacement are not one transaction.

## Boundaries and limits

Sections never cross document or heading boundaries. Within a section, sentence
embedding distance selects breaks using a percentile threshold. Higher threshold
usually means fewer breaks; it is not a quality/confidence score. Sections with
fewer than four regex-separated sentences stay whole unless size-limited. A small
tail merges into its neighbor. Short sections stay short rather than borrowing text
from another heading. No overlapping chunks are introduced by this runner.

Oversized spans are split near paragraph/sentence boundaries, then words, then
characters when necessary. These safety splits can divide sentences, list items or
tables. Original text and offsets remain auditable. Only intervening whitespace may
be omitted between spans; source text is never rewritten.

The character ceiling is not a token budget. Sentence detection is heuristic;
long model inputs can be truncated by the embedding model. Evaluate thresholds,
model token windows, tables, and bullet lists on the actual corpus before scaling.
The default MiniLM is the existing chunk-boundary model, not a decision on the
shared knowledge/query embedding model in embed/. No retrieval vectors are saved.
No LLM API is used. Embedding inference is local after the model download.

LangChain has sunset langchain-experimental; the prototype keeps the team's existing
splitter isolated and pins tested direct package versions. Revisit that dependency
before production use: https://github.com/langchain-ai/langchain-experimental/issues/87

Internal documents must have explicit visibility and sensitivity. Unknown visibility
is rejected. Legacy section arrays are accepted only as public-source inputs. Output
inside the repo is restricted to ignored data/output/; external SCC outputs must be
placed in team-only directories. Labels support later authorization; chunking does
not implement retrieval access control. Do not return internal chunks to agents yet.

Tests use public samples, invented clean docs and deterministic test embeddings.
Real internal text must never be added to fixtures or examples.

## SCC deployment workflow

Develop and test on Jen locally, commit, then push origin/Jen. On SCC, enter the
existing repository checkout and run `git status --short` before updating. Preserve
any local changes; do not reset them. Then:

```bash
git fetch origin
git switch Jen                  # first time: git switch --track origin/Jen
git pull --ff-only origin Jen
```

Use the Python module/environment your team already uses on SCC. If creating a new
venv, load a supported Python version first (`module avail python3`), then:

```bash
python3 -m venv .venv            # only if an environment does not already exist
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests -q
```

From the repo root, submit the included job script, replacing PROJECT and data paths:

```bash
qsub -P PROJECT data_pipeline/scc/chunk.sh \
  /projectnb/PROJECT/scrape/clean \
  /projectnb/PROJECT/chunking/public_chunks.json
```

If the venv needs a module loaded on compute nodes, pass its actual name:
`qsub -P PROJECT -v PYTHON_MODULE=python3/VERSION data_pipeline/scc/chunk.sh INPUT OUTPUT`.
The version is an example placeholder; verify it on SCC. The script requests a
six-hour CPU job, restricts library threads to the allocated slots, and defaults
the model cache to a model-cache folder next to the output file. It does not run
scraping or install dependencies. First use needs model-download network access;
pre-cache on an allowed node if compute-node internet access is restricted.

Record the job ID returned by qsub; use `qstat -u "$USER"` to see queued/running jobs.
By default, the merged job log is `semantic_chunk.oJOB_ID` in the repo directory.
After completion, inspect that log, `public_chunks.summary.json`, and representative
chunks. A job disappearing from qstat alone does not prove success. The summary's
document count should match the usable clean JSON files supplied to that run.
Internal inputs should use separate outputs in team-restricted project directories.
The job is a complete run, not resumable; allow enough time and use distinct output
names for concurrent experiments. Integrate code into dev after reviewing SCC results.
