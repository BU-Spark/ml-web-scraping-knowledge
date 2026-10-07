"""Semantic chunking: cut each section's text where the meaning changes.

Uses LangChain's SemanticChunker. It embeds the sentences, measures how far
apart neighbouring sentences are in meaning, and starts a new chunk wherever
that distance jumps.

Usage:
    python3 semantic_chunker.py [threshold] [min_chunk_chars]
    python3 semantic_chunker.py 90 200

    threshold       = percentile (0-100) of sentence-to-sentence distances.
                      A gap becomes a chunk break only if its distance is above
                      this percentile. Higher = fewer, bigger chunks.
    min_chunk_chars = chunks shorter than this are merged into a neighbour.

Reads  data/sections.json         (output of scraper.py)
Writes data/chunks_semantic.json  (same record format as chunks_character.json)
"""
import json
import re
import sys
from pathlib import Path

IN_PATH = Path("data/sections.json")
OUT_PATH = Path("data/chunks_semantic.json")

MODEL_NAME = "all-MiniLM-L6-v2"  # small, free, runs on your laptop
SENTENCE_SPLIT = r"(?<=[.?!])\s+"  # same default LangChain uses
MIN_SENTENCES_TO_SPLIT = 4  # sections with fewer sentences stay as one chunk


def load_embeddings(model_name=MODEL_NAME):
    """Load the free sentence-embedding model (downloads it the first time)."""
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=model_name,
        encode_kwargs={"normalize_embeddings": True},
    )


def make_chunker(embeddings, threshold=90, min_chunk_chars=200):
    """Build the LangChain chunker. `embeddings` is any LangChain Embeddings object."""
    from langchain_experimental.text_splitter import SemanticChunker

    return SemanticChunker(
        embeddings,
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=threshold,
        min_chunk_size=min_chunk_chars,
        sentence_split_regex=SENTENCE_SPLIT,
    )


def _locate_spans(text, pieces):
    """Find where each chunk sits in the original text, as (start, end) offsets.

    LangChain returns chunk strings, and it re-joins sentences with single
    spaces, so a chunk can differ from the original in whitespace. We match
    word by word, ignoring whitespace differences, so the offsets always point
    at the original text. (LangChain's own add_start_index is not used because
    it drifts: it adds up chunk lengths and ignores the removed whitespace.)
    """
    spans = []
    cursor = 0
    for piece in pieces:
        words = piece.split()
        if not words:
            continue
        pattern = re.compile(r"\s*(" + r"\s+".join(re.escape(w) for w in words) + ")")
        match = pattern.match(text, cursor)
        if match is None:  # should not happen; fall back to searching ahead
            match = pattern.search(text, cursor)
        if match is None:
            raise ValueError(f"could not locate chunk in section text: {piece[:60]!r}")
        spans.append((match.start(1), match.end(1)))
        cursor = match.end(1)
    return spans


def _merge_small_tail(spans, min_chunk_chars):
    """LangChain only merges small chunks forward, so fix a tiny last chunk here."""
    if len(spans) > 1 and spans[-1][1] - spans[-1][0] < min_chunk_chars:
        spans[-2:] = [(spans[-2][0], spans[-1][1])]
    return spans


def chunk_semantic(text, chunker, min_chunk_chars=200):
    """Return (start, end) character spans, one per semantic chunk.

    Same idea as chunk_characters() in character_chunker.py: you give it one
    section's text, it gives back spans into that text.
    """
    if not text.strip():
        return []
    if len(re.split(SENTENCE_SPLIT, text)) < MIN_SENTENCES_TO_SPLIT:
        return [(0, len(text))]
    spans = _locate_spans(text, chunker.split_text(text))
    return _merge_small_tail(spans, min_chunk_chars)


def chunk_sections(sections, chunker, min_chunk_chars=200):
    """Chunk each section separately so no chunk crosses a heading or page.

    start/end are offsets inside that section's "text" field.
    """
    chunks = []
    for sec_id, sec in enumerate(sections):
        text = sec["text"]
        for i, (start, end) in enumerate(chunk_semantic(text, chunker, min_chunk_chars)):
            chunks.append({
                "chunk_id": f"sem-{sec_id}-{i}",
                "strategy": "semantic",
                "source_url": sec["source_url"],
                "domain": sec["domain"],
                "page_title": sec["page_title"],
                "heading": sec["heading"],
                "section_id": sec_id,
                "start": start,
                "end": end,
                "text": text[start:end],
            })
    return chunks


def summarize(chunks):
    lengths = [len(c["text"]) for c in chunks]
    return (f"{len(chunks)} chunks | chars min/mean/max = "
            f"{min(lengths)}/{sum(lengths) // len(lengths)}/{max(lengths)}")


def main():
    threshold = float(sys.argv[1]) if len(sys.argv) > 1 else 90
    min_chunk_chars = int(sys.argv[2]) if len(sys.argv) > 2 else 200

    sections = json.loads(IN_PATH.read_text())
    chunker = make_chunker(load_embeddings(), threshold, min_chunk_chars)
    chunks = chunk_sections(sections, chunker, min_chunk_chars)
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(chunks, indent=2, ensure_ascii=False))
    print(f"{len(sections)} sections (threshold={threshold}, min_chunk_chars={min_chunk_chars}) "
          f"-> {summarize(chunks)}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
