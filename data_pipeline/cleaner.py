"""Cleaning stage entry point; the implementation lives in data_pipeline/scraper/.

Cleaning runs inside the scraper for each page (and inside ingest-internal for internal files):
  - data_pipeline/scraper/extract.py  HTML -> main article text with heading-based sections
  - data_pipeline/scraper/clean.py    unicode/whitespace normalization, boilerplate and repeated-line removal
  - data_pipeline/scraper/quality.py  gates: too_short, paywall_or_login, non_english, ...

The Oct 8 demo cleaner (split_into_sections) is preserved at git tag `oct8-demo`.
"""
from data_pipeline.scraper.clean import clean_sections, normalize, sections_to_text  # noqa: F401
from data_pipeline.scraper.extract import extract  # noqa: F401
