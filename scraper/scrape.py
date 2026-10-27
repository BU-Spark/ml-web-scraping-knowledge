"""Scrapes public web pages into clean, heading-based sections.

Usage:
    python3 -m scraper <url> [<url> ...]
    python3 -m scraper data/urls/demo_seed.txt   (one URL per line; lines starting with # are ignored)

Output: data/output/sections.json (every section from every page, in one file)

Before fetching a page, the scraper checks the site's robots.txt and skips
anything it disallows. If one page fails, the rest still run.
"""
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from protego import Protego

USER_AGENT = "Mozilla/5.0 (class project scraper)"
HEADERS = {"User-Agent": USER_AGENT}
NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "form"]

# Short lines containing these are treated as promo clutter, not lesson text.
PROMO_HINTS = ("newsletter", "subscribe", "sign up", "just for you",
               "cookie", "follow us", "share this")
MAX_PROMO_LEN = 150      # only lines shorter than this can be dropped as promos
MIN_SECTION_CHARS = 80   # sections with less text than this are discarded
DELAY_SECONDS = 1        # pause between pages to be polite to the site

_robots_cache = {}
logger = logging.getLogger(__name__)


def fetch(url):
    """Download the raw HTML of a page."""
    logger.info("FETCH: downloading %s", url)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    logger.info("FETCH: HTTP %s; %s bytes; final URL: %s",
                resp.status_code, len(resp.content), resp.url)
    resp.raise_for_status()
    return resp.text


def fetch_robots(root):
    """Return the text of a site's robots.txt, "" if it has none, None if unreachable."""
    logger.info("ROBOTS: requesting %s/robots.txt", root)
    try:
        resp = requests.get(root + "/robots.txt", headers=HEADERS, timeout=10)
    except requests.RequestException as err:
        logger.warning("ROBOTS: request failed: %s", err)
        return None
    logger.info("ROBOTS: HTTP %s", resp.status_code)
    if resp.status_code == 200:
        return resp.text
    if resp.status_code == 404:
        return ""
    return None


def allowed_by_robots(url):
    """True or False per robots.txt, or None if it could not be checked."""
    parts = urlparse(url)
    root = f"{parts.scheme}://{parts.netloc}"
    if root not in _robots_cache:
        body = fetch_robots(root)
        _robots_cache[root] = None if body is None else Protego.parse(body)
    else:
        logger.info("ROBOTS: using cached rules for %s", root)
    rules = _robots_cache[root]
    if rules is None:
        return None
    allowed = rules.can_fetch(url, USER_AGENT)
    logger.info("ROBOTS: page is %s", "allowed" if allowed else "disallowed")
    return allowed


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


def scrape_url(url):
    """Scrape one URL. Returns (sections, status message)."""
    allowed = allowed_by_robots(url)
    if allowed is False:
        return [], "SKIPPED: robots.txt disallows this page"
    note = "" if allowed else " (could not check robots.txt)"
    if allowed is None:
        logger.warning("ROBOTS: rules unavailable; continuing with the page request")
    try:
        sections = split_into_sections(fetch(url), url)
    except requests.RequestException as err:
        return [], f"FAILED: {err}"
    if not sections:
        return [], "EMPTY: no text found (page may need a browser to load)" + note
    return sections, f"OK: {len(sections)} sections" + note


def load_urls(args):
    """URLs come straight from the command line, or from a .txt file."""
    if len(args) == 1 and args[0].endswith(".txt"):
        lines = Path(args[0]).read_text().splitlines()
        return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    return args


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s", stream=sys.stdout)
    urls = load_urls(sys.argv[1:])
    logger.info("INPUT: loaded %s URLs", len(urls))
    if not urls:
        print("Usage: python3 -m scraper <url> [<url> ...]   or   python3 -m scraper data/urls/demo_seed.txt")
        sys.exit(1)

    all_sections = []
    successful_pages = 0
    for i, url in enumerate(urls):
        logger.info("PAGE %s/%s: %s", i + 1, len(urls), url)
        sections, status = scrape_url(url)
        all_sections.extend(sections)
        successful_pages += bool(sections)
        logger.info("RESULT: %s", status)
        if i < len(urls) - 1:
            logger.info("WAIT: pausing %s second(s)", DELAY_SECONDS)
            time.sleep(DELAY_SECONDS)

    out_path = Path("data/output/sections.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_sections, indent=2, ensure_ascii=False))
    logger.info("SAVE: wrote %s sections from %s/%s pages to %s (%s bytes)",
                len(all_sections), successful_pages, len(urls), out_path.resolve(), out_path.stat().st_size)
    if not all_sections:
        logger.error("No content was collected; the output is an empty JSON array")
        sys.exit(1)


if __name__ == "__main__":
    main()
