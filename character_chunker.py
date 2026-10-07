"""Cut the text every N characters, ignoring what it means."""


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
