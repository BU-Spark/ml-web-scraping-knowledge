"""Split the text where the meaning changes.

How it works:
  1. Turn every sentence into an embedding (a list of numbers capturing meaning).
  2. For each gap between sentences, compare the sentences just before it with
     the sentences just after it. A low similarity means the topic is shifting.
  3. Start a new chunk at the biggest topic shifts.
  4. Clean up: merge chunks that are too small, split chunks that are too big.
"""
import numpy as np

MODEL_NAME = "all-MiniLM-L6-v2"  # small, free, runs on your laptop


def load_embedder(model_name=MODEL_NAME):
    """Load the free sentence-embedding model (downloads it the first time)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)

    def embed(texts):
        vectors = model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors)

    return embed


def _cosine(a, b):
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / denom) if denom else 0.0


def chunk_semantic(sentences, embed_fn, window=2, percentile=15, min_sentences=2, max_chars=1200):
    """Return (start, end) character spans, one per semantic chunk.

    sentences     = list of Sentence objects (see chunk_utils.py)
    window        = how many sentences on each side of a gap to compare
    percentile    = the lowest X% of gap similarities become topic shifts
    min_sentences = chunks smaller than this get merged into a neighbor
    max_chars     = chunks longer than this get split at their weakest gap
    """
    n = len(sentences)
    if n == 0:
        return []
    if n == 1:
        return [(sentences[0].start, sentences[0].end)]

    vectors = embed_fn([s.text for s in sentences])

    # sims[i] = similarity across the gap between sentence i and sentence i+1
    sims = []
    for i in range(n - 1):
        left = vectors[max(0, i - window + 1): i + 1].mean(axis=0)
        right = vectors[i + 1: i + 1 + window].mean(axis=0)
        sims.append(_cosine(left, right))
    sims = np.array(sims)

    # Pick the weakest gaps, but not two shifts right next to each other.
    threshold = np.percentile(sims, percentile)
    candidates = sorted((i for i in range(n - 1) if sims[i] <= threshold), key=lambda i: sims[i])
    breaks = []
    for i in candidates:
        if all(abs(i - j) >= window for j in breaks):
            breaks.append(i)
    breaks.sort()

    # Groups are inclusive (first_sentence, last_sentence) index pairs.
    groups, first = [], 0
    for b in breaks:
        groups.append((first, b))
        first = b + 1
    groups.append((first, n - 1))

    # Merge groups that are too small into the neighbor they are most similar to.
    while len(groups) > 1:
        small = next((k for k, (a, b) in enumerate(groups) if b - a + 1 < min_sentences), None)
        if small is None:
            break
        if small == 0:
            target = 1
        elif small == len(groups) - 1:
            target = small - 1
        else:
            before = sims[groups[small][0] - 1]
            after = sims[groups[small][1]]
            target = small - 1 if before >= after else small + 1
        lo, hi = sorted((small, target))
        groups[lo:hi + 1] = [(groups[lo][0], groups[hi][1])]

    # Split groups that are too long at their weakest internal gap.
    final, stack = [], list(reversed(groups))
    while stack:
        a, b = stack.pop()
        length = sentences[b].end - sentences[a].start
        if length > max_chars and b > a:
            cut = a + int(np.argmin(sims[a:b]))
            stack.append((cut + 1, b))
            stack.append((a, cut))
        else:
            final.append((a, b))

    return [(sentences[a].start, sentences[b].end) for a, b in final]
