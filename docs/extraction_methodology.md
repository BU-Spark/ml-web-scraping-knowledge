# Extraction methodology (outline, not final)

Required deliverable: how pages and internal documents become knowledge units.

1. **Sources**: public URL list (`data/urls/public_urls_compiled.txt`) and client-supplied internal
   .txt files. How sources were chosen; robots.txt/ToS handling; what was blocked and skipped.
2. **Scraping and cleaning**: see `data_pipeline/scraper/README.md` (done).
3. **Chunking**: heading-based sections, then semantic splits inside each section.
   The implemented runner preserves source offsets, provenance, confidence markers,
   and visibility/sensitivity. See `docs/chunking.md` for its contract and limits.
4. **Extraction**: prompt (`prompts/extraction_prompt.txt`), knowledge-unit schema
   (`schemas/knowledge_unit_schema.json`), how evidence quotes are checked against source text,
   how [INFERRED]/[UNKNOWN] internal lines become low-confidence units.
5. **Validation and deduplication**: rules and examples.
6. **Embedding**: shared model in `embed/` (choice pending).
7. **Known limitations**: source skew (category 1), blocked sites, PDFs not yet handled.
