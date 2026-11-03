"""Settings for the scraper: paths, user agent, politeness, gate thresholds.

Everything tunable lives here so the other modules stay free of magic numbers.
The contact address comes from the SCRAPER_CONTACT env var (or .env), never from code.
"""
import os
from pathlib import Path

# ---- Paths (run from the repo root) ----
LINK_FILE = Path("data/urls/public_urls_compiled.txt")
DOMAINS_FILE = Path(__file__).parent / "domains.yaml"

# Committed: manifest and reports (URLs and statuses only, no page text).
SCRAPE_DIR = Path("data/scrape")
MANIFEST = SCRAPE_DIR / "manifest.jsonl"
REPORT_CSV = SCRAPE_DIR / "scrape_report.csv"
PROBE_CSV = SCRAPE_DIR / "probe_report.csv"
SUMMARY_MD = SCRAPE_DIR / "summary.md"

# Gitignored (data/output/): third-party page text. On SCC this lives in project space;
# set SCRAPER_OUT to point there.
OUT_DIR = Path(os.environ.get("SCRAPER_OUT", "data/output/scrape"))
RAW_DIR = OUT_DIR / "raw"
CLEAN_DIR = OUT_DIR / "clean"
REGISTRY = OUT_DIR / "registry.jsonl"
LOG_DIR = OUT_DIR / "logs"
SECTIONS_EXPORT = Path("data/output/sections.json")  # old flat format the chunker reads

# ---- Categories (numbers from the client's list) ----
CATEGORY_NAMES = {1: "sales_methodology", 2: "segmentation_territory", 10: "enablement_operations"}
EXPECTED_COUNTS = {1: 155, 2: 113, 10: 127}  # cat 2: +7 competitor GTM links (Nov 3)


# ---- Identity ----
def _load_dotenv(path=Path(".env")):
    """Tiny .env reader (KEY=value lines) so we don't need python-dotenv."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()
BOT_NAME = "BU-Spark-DS549-KnowledgeBot"  # the token robots.txt rules are matched against


def user_agent():
    """Honest UA with a contact address. sec.gov rejects requests without one."""
    contact = os.environ.get("SCRAPER_CONTACT")
    if not contact:
        raise SystemExit("Set SCRAPER_CONTACT (e.g. in .env) to the team contact email before fetching.")
    return f"{BOT_NAME}/0.1 (+BU Spark! DS549 research project; contact: {contact})"


# ---- Politeness ----
DEFAULT_DELAY = 3.0       # seconds between requests to the same host
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
MAX_RETRIES = 3           # for 429 and 5xx only
BACKOFF_BASE = 2.0        # 2, 4, 8 seconds
MAX_RETRY_AFTER = 60      # cap on a server's Retry-After so one site can't stall the run

# ---- Quality gates ----
MIN_WORDS = 150           # below this after cleaning -> too_short
PAYWALL_MAX_WORDS = 400   # paywall phrases only count when the page has little body text
MAX_REPEATS = 2           # a line seen more than this many times on a page is boilerplate
MAX_BOILERPLATE_LEN = 150 # only lines shorter than this can be dropped as CTAs

# Short lines matching these are dropped (case-insensitive substrings). Conservative on
# purpose: keeping a stray CTA is cheaper than losing real content.
BOILERPLATE_LINE_PATTERNS = [
    "subscribe to our newsletter", "sign up for our newsletter", "subscribe now",
    "join our newsletter", "get the latest", "delivered to your inbox",
    "book a demo", "request a demo", "schedule a demo", "get a demo", "start your free trial",
    "we use cookies", "cookie policy", "accept cookies", "cookie settings",
    "share this article", "share this post", "share on linkedin", "share on twitter",
    "follow us on", "related posts", "related articles", "you may also like",
    "recommended for you", "read more:", "back to top", "all rights reserved",
]
# Sections whose heading matches these are dropped whole (the heading is the giveaway).
BOILERPLATE_HEADING_PATTERNS = [
    "related posts", "related articles", "related resources", "you may also like",
    "recommended reading", "share article", "share this", "subscribe", "newsletter",
    "about the author", "more from", "popular posts", "recent posts", "leave a comment",
]
