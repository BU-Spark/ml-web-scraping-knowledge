"""HTML -> metadata + heading-structured sections.

Primary: trafilatura (finds the main article and drops nav/ads) in XML mode, so headings,
lists and tables survive. Fallback: BeautifulSoup on <article>/<main>/largest text block.

Output sections: [{"heading": str|None, "level": int, "text": str}] in page order.
Text before the first heading is a section with heading None (level 0). List items become
lines starting with "- "; table rows become "a | b | c" lines.
"""
import re

import trafilatura
from bs4 import BeautifulSoup
from lxml import etree

HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
DROP_TAGS = ["nav", "header", "footer", "aside", "form", "script", "style", "noscript", "iframe", "svg"]


def _clean_ws(text):
    return re.sub(r"\s+", " ", text or "").strip()


class _SectionBuilder:
    def __init__(self):
        self.sections = []
        self.current = {"heading": None, "level": 0, "lines": []}

    def heading(self, text, level):
        self._flush()
        self.current = {"heading": text, "level": level, "lines": []}

    def line(self, text):
        if text:
            self.current["lines"].append(text)

    def _flush(self):
        cur = self.current
        if cur["lines"] or cur["heading"]:
            self.sections.append({"heading": cur["heading"], "level": cur["level"],
                                  "text": "\n".join(cur["lines"])})

    def result(self):
        self._flush()
        return self.sections


# ---- trafilatura path ----

def _walk_xml(el, b):
    tag = el.tag
    if tag == "head":
        rend = el.get("rend", "h2")
        level = int(rend[1]) if re.fullmatch(r"h[1-6]", rend) else 2
        b.heading(_clean_ws("".join(el.itertext())), level)
    elif tag == "p" or tag == "quote" or tag == "code":
        b.line(_clean_ws("".join(el.itertext())))
    elif tag == "list":
        for item in el.iterchildren("item"):
            nested = [c for c in item if c.tag == "list"]
            own = _clean_ws((item.text or "") + "".join(
                etree.tostring(c, method="text", encoding="unicode") for c in item if c.tag != "list"))
            b.line(f"- {own}" if own else "")
            for sub in nested:
                _walk_xml(sub, b)
    elif tag == "table":
        for row in el.iter("row"):
            cells = [_clean_ws("".join(c.itertext())) for c in row.iter("cell")]
            if any(cells):
                b.line(" | ".join(cells))
    else:
        if el.text and el.text.strip() and tag not in ("main", "doc", "comments"):
            b.line(_clean_ws(el.text))
        for child in el:
            _walk_xml(child, b)


def _trafilatura_xml(html, url=None):
    xml = trafilatura.extract(html, url=url, output_format="xml", include_tables=True,
                              include_comments=False, favor_precision=True, include_formatting=False)
    if not xml:
        return None
    root = etree.fromstring(xml.encode("utf-8"))
    main = root.find("main")
    return main if main is not None else root


def sections_trafilatura(html, url=None):
    main = _trafilatura_xml(html, url)
    if main is None:
        return []
    b = _SectionBuilder()
    for child in main:
        _walk_xml(child, b)
    return b.result()


def _key(text):
    """Whitespace- and case-insensitive key, so DOM text and trafilatura text compare equal."""
    return re.sub(r"\W+", "", text).lower()


def sections_hybrid(html, url=None):
    """Trafilatura decides WHAT is article text; the page's DOM supplies the headings around it.

    Trafilatura sometimes drops headings (e.g. salesforce.com blog). Here we walk the page in
    order and keep a paragraph/list item/table row only if trafilatura also kept it. Headings are
    kept as-is; any heading with no kept text under it is dropped later by clean.py.
    """
    main = _trafilatura_xml(html, url)
    if main is None:
        return []
    keep = {_key("".join(el.itertext())) for el in main.iter("p", "item", "row", "quote", "code")}
    keep.discard("")
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(DROP_TAGS):
        tag.decompose()
    b = _SectionBuilder()
    for el in (soup.body or soup).find_all(HEADING_TAGS + ["p", "li", "tr", "blockquote", "pre"]):
        if el.name in HEADING_TAGS:
            b.heading(_clean_ws(el.get_text(" ")), int(el.name[1]))
            continue
        if el.name == "li" and el.find(["p", "li"]):
            continue
        if el.name in ("blockquote", "pre") and el.find("p"):
            continue
        if el.name == "tr":
            cells = [_clean_ws(c.get_text(" ")) for c in el.find_all(["td", "th"])]
            text = " | ".join(cells)
            if _key("".join(cells)) in keep:
                b.line(text)
            continue
        text = _clean_ws(el.get_text(" "))
        if _key(text) in keep:
            b.line(("- " + text) if el.name == "li" else text)
    return [s for s in b.result() if s["text"]] or []


# ---- BeautifulSoup fallback ----

def _main_block(soup):
    for sel in ("article", "main", "[role=main]"):
        found = soup.select_one(sel)
        if found and len(found.get_text(" ", strip=True).split()) > 50:
            return found
    # Largest text-dense block: the div/section with the most paragraph text.
    best, best_words = soup.body or soup, 0
    for el in soup.find_all(["div", "section"]):
        words = sum(len(p.get_text(" ", strip=True).split()) for p in el.find_all("p", recursive=False))
        if words > best_words:
            best, best_words = el, words
    return best


def sections_soup(html):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(DROP_TAGS):
        tag.decompose()
    block = _main_block(soup)
    b = _SectionBuilder()
    for el in block.find_all(HEADING_TAGS + ["p", "li", "tr"]):
        if el.name in HEADING_TAGS:
            b.heading(_clean_ws(el.get_text(" ")), int(el.name[1]))
        elif el.name == "li":
            if el.find(["p", "li"]):  # its text is picked up via the nested elements
                continue
            b.line("- " + _clean_ws(el.get_text(" ")))
        elif el.name == "tr":
            cells = [_clean_ws(c.get_text(" ")) for c in el.find_all(["td", "th"])]
            if any(cells):
                b.line(" | ".join(cells))
        elif not el.find_parent("li"):
            b.line(_clean_ws(el.get_text(" ")))
    return b.result()


# ---- metadata ----

def _meta(soup, *names):
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _iso_date(value):
    if not value:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    return m.group(1) if m else None


def extract_metadata(html, url, domain):
    soup = BeautifulSoup(html, "lxml")
    md = trafilatura.extract_metadata(html, default_url=url)
    md = md.as_dict() if md else {}
    canonical = soup.find("link", rel="canonical")
    html_tag = soup.find("html")
    title_tag = soup.title.get_text(strip=True) if soup.title else None
    return {
        "title": md.get("title") or _meta(soup, "og:title") or title_tag,
        "author": md.get("author") or _meta(soup, "author", "article:author"),
        "published_date": _iso_date(md.get("date"))
                          or _iso_date(_meta(soup, "article:published_time", "datePublished")),
        "modified_date": _iso_date(_meta(soup, "article:modified_time", "og:updated_time", "dateModified")),
        "publisher": _meta(soup, "og:site_name") or (md.get("sitename") if md.get("sitename") != md.get("hostname") else None) or domain,
        "description": md.get("description"),
        "language": (html_tag.get("lang") if html_tag else None) or _meta(soup, "og:locale", "language"),
        "canonical_url": canonical.get("href") if canonical and canonical.get("href") else None,
    }


def extract(html, url, domain):
    """Returns (metadata dict, sections list, extractor name)."""
    meta = extract_metadata(html, url, domain)
    sections = sections_trafilatura(html, url)
    method = "trafilatura"
    # If the page has more headings than trafilatura kept, rebuild the outline from the DOM,
    # but only if that keeps nearly all of trafilatura's text.
    hybrid = sections_hybrid(html, url)
    words = lambda secs: sum(len(x["text"].split()) for x in secs)
    heads = lambda secs: sum(1 for x in secs if x["heading"])
    if heads(hybrid) > heads(sections) and words(hybrid) >= 0.9 * words(sections):
        sections, method = hybrid, "trafilatura+dom_headings"
    if sum(len(s["text"].split()) for s in sections) < 50:
        fallback = sections_soup(html)
        if sum(len(s["text"].split()) for s in fallback) > sum(len(s["text"].split()) for s in sections):
            sections, method = fallback, "beautifulsoup"
    return meta, sections, method
