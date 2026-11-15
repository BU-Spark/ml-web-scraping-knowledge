"""Shared, normalized MiniLM embeddings for ingestion and query processing.

Migration 001 fixes the store to all-MiniLM-L6-v2 (384 dimensions). A different
model requires a migration and re-embedding, even if its dimensions happen to match.
"""
import os
from functools import lru_cache
from threading import Lock

EMBED_MODEL = "all-MiniLM-L6-v2"
MODEL_LOCK = Lock()


@lru_cache(maxsize=1)
def _load_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL, device="cpu")


def embed_texts(texts):
    """Return normalized 384-dimensional vectors; load the model on first use."""
    if os.environ.get("EMBED_MODEL", EMBED_MODEL) != EMBED_MODEL:
        raise ValueError("EMBED_MODEL must match migration 001: all-MiniLM-L6-v2")
    texts = list(texts)
    if not texts:
        return []
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("Embedding inputs must be nonempty strings")
    with MODEL_LOCK:
        vectors = _load_model().encode(texts, normalize_embeddings=True)
    return [[float(value) for value in vector] for vector in vectors]
