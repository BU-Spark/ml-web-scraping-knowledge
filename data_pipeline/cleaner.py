"""Clean downloaded HTML and extract source-traceable heading sections."""
import logging
from datetime import date
from urllib.parse import urlparse

from bs4 import BeautifulSoup

NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "form"]

# Short lines containing these are treated as promo clutter, not lesson text.
PROMO_HINTS = ("newsletter", "subscribe", "sign up", "just for you",
               "cookie", "follow us", "share this")
MAX_PROMO_LEN = 150      # only lines shorter than this can be dropped as promos
MIN_SECTION_CHARS = 80   # sections with less text than this are discarded

logger = logging.getLogger(__name__)


def is_promo(text):
    """Short lines that look like newsletter, cookie or sharing prompts."""
    return len(text) < MAX_PROMO_LEN and any(h in text.lower() for h in PROMO_HINTS)


def split_into_sections(html, url):
    """Strip page clutter, then group text under the heading it belongs to."""
    soup = BeautifulSoup(html, "html.parser")
    removed = 0
    for tag in soup(NOISE_TAGS):
        tag.decompose()
        removed += 1

    root = soup.find("main") or soup.find("article") or soup.body or soup
    page_title = soup.title.get_text(strip=True) if soup.title else url
    logger.info("CLEAN: removed %s clutter elements; reading <%s>; title: %s",
                removed, root.name, page_title)

    sections = []
    current = {"heading": page_title, "text": []}
    seen = set()
    promos = duplicates = 0
    for el in root.find_all(["h1", "h2", "h3", "p", "li"]):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if el.name in ("h1", "h2", "h3"):
            if current["text"]:
                sections.append(current)
            current = {"heading": text, "text": []}
        else:
            if is_promo(text):
                promos += 1
                continue
            if text in seen and len(text) < MAX_PROMO_LEN:
                duplicates += 1
                continue
            seen.add(text)
            current["text"].append(text)
    if current["text"]:
        sections.append(current)

    scraped_at = date.today().isoformat()
    result = [
        {
            "source_url": url,
            "domain": urlparse(url).netloc,
            "page_title": page_title,
            "heading": s["heading"],
            "text": " ".join(s["text"]),
            "scraped_at": scraped_at,
        }
        for s in sections
        if len(" ".join(s["text"])) >= MIN_SECTION_CHARS
    ]
    logger.info("SPLIT: %s candidate sections; dropped %s promo lines, %s duplicate lines, and %s sections under %s characters",
                len(sections), promos, duplicates, len(sections) - len(result), MIN_SECTION_CHARS)
    for i, section in enumerate(result, 1):
        logger.info("SECTION %s: %s (%s characters)", i, section["heading"], len(section["text"]))
    return result

