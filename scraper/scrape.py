"""Compatibility imports; implementation now lives in data_pipeline."""
from data_pipeline.scraper import (
    allowed_by_robots, fetch, fetch_robots, load_urls, main, scrape_url,
)
from data_pipeline.cleaner import is_promo, split_into_sections

if __name__ == "__main__":
    main()
