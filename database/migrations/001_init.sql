-- 001_init: Postgres + pgvector schema for the knowledge store.
--
--   categories                      category names (every table refers to these)
--   scrape_log                      one row per URL the scraper tried (audit only)
--   documents -< chunks -< units    doc_id links documents/chunks; chunk_id links units
--   served_units (view)             what the MCP server reads
--
-- Column names follow each stage's own output: documents = scraper, chunks = Jen's chunker
-- (start/end stored as char_start/char_end), units = Tony/Aaliyah's knowledge_unit_schema v0.1.
-- Run with: python3 -m database.migrate   (applies each migration once, in order)
--
-- Embedding: vector(384) = all-MiniLM-L6-v2. Changing the model means a new migration and
-- re-embedding every unit. No vector index yet: at our size an exact search is fast and always
-- returns the full number of results, even with category/visibility filters.

CREATE EXTENSION IF NOT EXISTS vector;

-- Categories are names, so new ones (e.g. found by automated scraping) are just new rows.
CREATE TABLE categories (
    name        text PRIMARY KEY,
    description text                 -- definition; to be written
);
INSERT INTO categories (name) VALUES
    ('Sales Methodology and Process'),
    ('Segmentation and Territory'),
    ('Enablement Operations');

-- Scraper registry: every URL attempted, any status. Not linked to documents by foreign key
-- (failed URLs have no document; internal files have no registry row).
CREATE TABLE scrape_log (
    doc_id          text PRIMARY KEY,
    url             text NOT NULL UNIQUE,
    final_url       text,
    domain          text,
    category        text REFERENCES categories (name),
    section_label   text,
    status          text NOT NULL,
    reason          text,
    http_status     integer,
    fetch_method    text,
    content_type    text,
    word_count      integer,
    content_sha256  text,
    retrieved_at    timestamptz,
    robots_allowed  boolean,
    tos_flag        text,
    duplicate_of    text,
    loaded_at       timestamptz NOT NULL DEFAULT now()
);

-- One row per clean document (public web page or internal file). Text lives in chunks.
CREATE TABLE documents (
    doc_id          text PRIMARY KEY,
    url             text,                -- null for internal files
    canonical_url   text,
    source_file     text,                -- internal files only
    domain          text,
    publisher       text,
    title           text,
    author          text,
    published_date  text,                -- as found on the page; formats vary
    retrieved_at    timestamptz,
    category        text NOT NULL REFERENCES categories (name),
    also_categories text[] NOT NULL DEFAULT '{}',
    visibility      text NOT NULL CHECK (visibility IN ('public', 'internal')),
    sensitivity     text NOT NULL DEFAULT 'public'
                    CHECK (sensitivity IN ('public', 'internal', 'confidential')),
    loaded_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (url IS NOT NULL OR source_file IS NOT NULL)
);

-- One row per semantic chunk (data_pipeline/chunker.py).
CREATE TABLE chunks (
    chunk_id        text PRIMARY KEY,
    doc_id          text NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    section_id      text NOT NULL,       -- "<doc_id>:section:<n>"
    section_index   integer NOT NULL,
    chunk_index     integer NOT NULL,
    heading         text,
    heading_level   integer,
    heading_path    text[] NOT NULL DEFAULT '{}',
    char_start      integer NOT NULL,    -- chunker "start"/"end": offsets into the section text
    char_end        integer NOT NULL,
    text            text NOT NULL,
    tags            text[] NOT NULL DEFAULT '{}',   -- e.g. {INFERRED, UNKNOWN}
    category        text NOT NULL REFERENCES categories (name),
    visibility      text NOT NULL CHECK (visibility IN ('public', 'internal')),
    sensitivity     text NOT NULL DEFAULT 'public'
                    CHECK (sensitivity IN ('public', 'internal', 'confidential')),
    strategy        text,
    schema_version  text,
    loaded_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (char_end > char_start)
);
CREATE INDEX chunks_doc_id_idx ON chunks (doc_id);

-- One row per knowledge unit, in the extractor's format (knowledge_unit_schema v0.1).
-- A unit reaches its document through its chunk.
CREATE TABLE units (
    unit_id         text PRIMARY KEY,
    chunk_id        text NOT NULL REFERENCES chunks (chunk_id) ON DELETE CASCADE,
    section_id      integer,             -- the chunk's section_index
    claim           text NOT NULL CHECK (claim <> ''),
    evidence_quote  text NOT NULL CHECK (evidence_quote <> ''),
    level           text NOT NULL CHECK (level IN ('know_how', 'knowledge')),
    unit_type       text NOT NULL CHECK (unit_type IN ('how_to', 'definition', 'statistic', 'example')),
    context         jsonb NOT NULL DEFAULT '{}',   -- {who, industry, company_size, situation}
    outcome         text,                -- measured result stated by the source; null if only recommended
    topic           text,
    category        text NOT NULL REFERENCES categories (name),
    source_url      text,                -- null for internal files
    domain          text,
    publisher       text,
    published_date  text,
    page_title      text,
    heading         text,
    char_start      integer,
    char_end        integer,
    source_type     text NOT NULL CHECK (source_type IN ('external', 'internal')),
    sensitivity     text NOT NULL CHECK (sensitivity IN ('public', 'internal', 'confidential')),
    source_tier     smallint CHECK (source_tier IN (1, 2, 3)),
    extracted_at    date,
    embed_text      text,
    embedding       vector(384),
    loaded_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX units_chunk_id_idx ON units (chunk_id);
CREATE INDEX units_category_idx ON units (category);

-- What the MCP server reads: each unit with its chunk and document, plus ONE effective access
-- label. A unit counts as internal if the unit, its chunk or its document is internal, and takes
-- the strictest sensitivity of the three. The server filters on visibility (MCP_ALLOWED_VISIBILITY).
CREATE VIEW served_units AS
SELECT u.unit_id, u.chunk_id, c.doc_id, u.section_id, u.claim, u.evidence_quote, u.level,
       u.unit_type, u.context, u.outcome, u.topic, u.category, u.source_url, d.canonical_url,
       d.source_file, u.domain, u.publisher, u.published_date, u.page_title, d.title AS doc_title,
       u.heading, c.heading_path, u.char_start, u.char_end, u.source_tier, c.tags, u.extracted_at,
       u.embedding,
       CASE WHEN u.source_type = 'external' AND c.visibility = 'public' AND d.visibility = 'public'
                 AND 'public' = ALL (ARRAY[u.sensitivity, c.sensitivity, d.sensitivity])
            THEN 'public' ELSE 'internal' END AS visibility,
       CASE WHEN 'confidential' = ANY (ARRAY[u.sensitivity, c.sensitivity, d.sensitivity]) THEN 'confidential'
            WHEN 'internal' = ANY (ARRAY[u.sensitivity, c.sensitivity, d.sensitivity]) THEN 'internal'
            ELSE 'public' END AS sensitivity
FROM units u
JOIN chunks c ON c.chunk_id = u.chunk_id
JOIN documents d ON d.doc_id = c.doc_id;
