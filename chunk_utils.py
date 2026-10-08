"""Shared helpers: join scraped sections into one continuous text, then describe
and measure chunks of that text.

Headings are NOT part of the text the chunkers see. They are only remembered so
we can measure afterwards whether a chunk mixes two parts of the article.
"""
import re
from dataclasses import dataclass

# A sentence ends at . ! or ? followed by whitespace and a capital letter, digit or opening quote.
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“‘'(\[])")


@dataclass
class Sentence:
    start: int    # character offset in the joined text
    end: int
    text: str
    section: int  # which scraped section the sentence came from


def normalize_ws(text):
    """Collapse any run of whitespace into one space."""
    return " ".join(text.split())


def build_document(sections):
    """Join the section bodies into one continuous text.

    Returns a dict with the joined text, every sentence with its position,
    and the character range and heading of each section.
    """
    parts, sentences, section_ranges = [], [], []
    base = 0
    for idx, sec in enumerate(sections):
        body = sec["text"].strip()
        section_ranges.append((base, base + len(body)))
        pos = 0
        for match in list(SENTENCE_BREAK.finditer(body)) + [None]:
            end = match.start() if match else len(body)
            piece = body[pos:end]
            if piece.strip():
                sentences.append(Sentence(base + pos, base + end, piece, idx))
            if match:
                pos = match.end()
        parts.append(body)
        base += len(body) + 1  # +1 for the single space that joins sections
    return {
        "text": " ".join(parts),
        "sentences": sentences,
        "section_ranges": section_ranges,
        "headings": [sec["heading"] for sec in sections],
    }


def spans_to_chunks(spans, doc, method, source_url):
    """Turn (start, end) character spans into chunk records with quality flags."""
    sentence_starts = {s.start for s in doc["sentences"]}
    sentence_ends = {s.end for s in doc["sentences"]}
    chunks = []
    for i, (a, b) in enumerate(spans, start=1):
        raw = doc["text"][a:b]
        text = raw.strip()
        a2 = a + (len(raw) - len(raw.lstrip()))
        b2 = a2 + len(text)
        spanned = [
            k for k, (sa, sb) in enumerate(doc["section_ranges"])
            if min(b2, sb) - max(a2, sa) > 0
        ]
        chunks.append({
            "chunk_id": f"{method}-{i:02d}",
            "text": text,
            "source_url": source_url,
            "heading": doc["headings"][spanned[0]] if spanned else "",
            "headings_spanned": [doc["headings"][k] for k in spanned],
            "method": method,
            "char_count": len(text),
            "starts_mid_sentence": a2 not in sentence_starts,
            "ends_mid_sentence": b2 not in sentence_ends,
            "char_start": a2,
            "char_end": b2,
        })
    return chunks


def measure(chunks):
    """Summary numbers for one chunking method."""
    sizes = [c["char_count"] for c in chunks]
    n = len(chunks)
    cut = sum(c["starts_mid_sentence"] or c["ends_mid_sentence"] for c in chunks)
    mixed = sum(len(c["headings_spanned"]) > 1 for c in chunks)
    return {
        "chunks": n,
        "min_chars": min(sizes),
        "avg_chars": round(sum(sizes) / n),
        "max_chars": max(sizes),
        "pct_cut_mid_sentence": round(100 * cut / n),
        "pct_mixing_sections": round(100 * mixed / n),
    }
