"""Character chunking: cut each section's text every N characters, ignoring meaning.

Usage:
    python3 -m chunking.character [size] [overlap]
    python3 -m chunking.character 500 50

Reads  data/output/sections.json         (output of the scraper)
Writes data/output/chunks_character.json (one record per chunk)
"""
import json
import sys
from pathlib import Path

IN_PATH = Path("data/output/sections.json")
OUT_PATH = Path("data/output/chunks_character.json")


def chunk_characters(text, size=500, overlap=50):
    """Return (start, end) character spans covering the text.

    size    = characters per chunk
    overlap = characters repeated at the start of the next chunk
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    spans = []
    start = 0
    step = size - overlap
    while start < len(text):
        end = min(start + size, len(text))
        spans.append((start, end))
        if end == len(text):
            break
        start += step
    return spans


def chunk_sections(sections, size=500, overlap=50):
    """Chunk each section separately so no chunk crosses a heading or page.

    start/end are offsets inside that section's "text" field.
    """
    chunks = []
    for sec_id, sec in enumerate(sections):
        text = sec["text"]
        for i, (start, end) in enumerate(chunk_characters(text, size, overlap)):
            chunks.append({
                "chunk_id": f"char-{sec_id}-{i}",
                "strategy": "character",
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
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    overlap = int(sys.argv[2]) if len(sys.argv) > 2 else 50

    sections = json.loads(IN_PATH.read_text())
    chunks = chunk_sections(sections, size, overlap)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(chunks, indent=2, ensure_ascii=False))
    print(f"{len(sections)} sections (size={size}, overlap={overlap}) -> {summarize(chunks)}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()