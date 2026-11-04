# Synthetic internal sample (NOT real Salesforce data)

Made-up documents in the format we expect internal knowledge to arrive in (markdown `.txt` files
plus `metadata.csv`). Every number, rule and name here is invented. They exist so the team can
build and demo the internal-ingest path and access control without touching real internal data.

    INTERNAL_DIR=data/samples/synthetic_internal python3 -m scraper ingest-internal
