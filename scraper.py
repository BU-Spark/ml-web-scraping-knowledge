"""Scrapes public web pages into clean, heading-based sections.

Usage:
    python3 scraper.py <url> [<url> ...]
    python3 scraper.py urls.txt      (one URL per line; lines starting with # are ignored)

Output: data/sections.json (every section from every page, in one file)

Before fetching a page, the scraper checks the site's robots.txt and skips
anything it disallows. If one page fails, the rest still run.
"""
import json
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


def fetch(url):
    """Download the raw HTML of a page."""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def fetch_robots(root):
    """Return the text of a site's robots.txt, "" if it has none, None if unreachable."""
    try:
        resp = requests.get(root + "/robots.txt", headers=HEADERS, timeout=10)
    except requests.RequestException:
        return None
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
    rules = _robots_cache[root]
    if rules is None:
        return None
    return rules.can_fetch(url, USER_AGENT)


def is_promo(text):
    """Short lines that look like newsletter, cookie or sharing prompts."""
    return len(text) < MAX_PROMO_LEN and any(h in text.lower() for h in PROMO_HINTS)


def split_into_sections(html, url):
    """Strip page clutter, then group text under the heading it belongs to."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(NOISE_TAGS):
        tag.decompose()

    root = soup.find("main") or soup.find("article") or soup.body or soup
    page_title = soup.title.get_text(strip=True) if soup.title else url

    sections = []
    current = {"heading": page_title, "text": []}
    seen = set()
    for el in root.find_all(["h1", "h2", "h3", "p", "li"]):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if el.name in ("h1", "h2", "h3"):
            if current["text"]:
                sections.append(current)
            current = {"heading": text, "text": []}
        else:
            if is_promo(text) or (text in seen and len(text) < MAX_PROMO_LEN):
                continue
            seen.add(text)
            current["text"].append(text)
    if current["text"]:
        sections.append(current)

    scraped_at = date.today().isoformat()
    return [
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


def scrape_url(url):
    """Scrape one URL. Returns (sections, status message)."""
    allowed = allowed_by_robots(url)
    if allowed is False:
        return [], "SKIPPED: robots.txt disallows this page"
    note = "" if allowed else " (could not check robots.txt)"
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
    urls = load_urls(sys.argv[1:])
    if not urls:
        print("Usage: python3 scraper.py <url> [<url> ...]   or   python3 scraper.py urls.txt")
        sys.exit(1)

    all_sections = []
    for i, url in enumerate(urls):
        sections, status = scrape_url(url)
        all_sections.extend(sections)
        print(f"{status}\n    {url}")
        if i < len(urls) - 1:
            time.sleep(DELAY_SECONDS)

    out_path = Path("data/sections.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(all_sections, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(all_sections)} sections from {len(urls)} URLs to {out_path}")


if __name__ == "__main__":
    main()
