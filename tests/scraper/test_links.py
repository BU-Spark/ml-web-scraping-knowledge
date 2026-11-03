from scraper import config, links

SAMPLE = """# Compiled public URL list: knowledge categories 1, 2 and 10
# Duplicate URLs were removed (first occurrence kept).

# Knowledge category 1: Sales methodology and process
# Total URLs: 3
#
# Challenger: official methodology (2)
https://challengerinc.com/a/
https://meddicc.com/spiced-vs-meddpicc
# Also tagged for Segmentation and territory: maps SPICED to mid-market
#
# HubSpot: BANT (1)
https://blog.hubspot.com/sales/bant?utm_source=x#top

# Knowledge category 2: Segmentation and territory (SMB, Commercial, Enterprise)
# Total URLs: 1
# Segment definitions: SMB cutoffs (1)
https://www.sba.gov/size-standards
# Shared with category 1 (listed as comments; tag them for this category too)

# Enablement operations: external public sources, tier 1 and 2 only
# One URL per line. Lines starting with # are ignored.
# Run with:  python scraper.py urls.txt
# === Coaching (1) ===
https://www.gartner.com/en/sales/coaching
"""


def test_categories_labels_and_also_tags():
    rows = links.parse_link_file(SAMPLE)
    assert [r["category"] for r in rows] == [1, 1, 1, 2, 10]
    assert [r["section_label"] for r in rows] == [
        "Challenger: official methodology", "Challenger: official methodology", "HubSpot: BANT",
        "Segment definitions: SMB cutoffs", "Coaching"]
    assert rows[1]["also_categories"] == [2]
    assert rows[0]["also_categories"] == []
    assert rows[4]["category_name"] == "enablement_operations"


def test_comments_are_never_urls():
    rows = links.parse_link_file(SAMPLE)
    assert all(r["url"].startswith("https://") for r in rows)
    assert len(rows) == 5


def test_normalize_and_stable_doc_id():
    rows = links.parse_link_file(SAMPLE)
    assert rows[0]["url_normalized"] == "https://challengerinc.com/a"
    assert rows[2]["url_normalized"] == "https://blog.hubspot.com/sales/bant"  # utm + fragment dropped
    assert rows[3]["domain"] == "sba.gov"
    assert rows[0]["doc_id"] == links.doc_id_for("https://challengerinc.com/a") == \
        links.parse_link_file(SAMPLE)[0]["doc_id"]
    assert len(rows[0]["doc_id"]) == 16


def test_real_link_file_counts():
    rows = links.parse_link_file(config.LINK_FILE.read_text(encoding="utf-8"))
    assert links.check_counts(rows) == []
