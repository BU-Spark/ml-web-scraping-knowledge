"""Planned: shared embedding interface. Structure placeholder; the model is not chosen yet.

Candidates discussed: bge-m3 (~2 GB RAM, too big for a small Heroku dyno), bge-small, or a hosted
embedding API. Whatever is chosen, the pipeline and the MCP server must use it identically
(same model, same normalization), and the vector size must match the database column.
"""
import os

# Set via env var so SCC jobs and the Heroku server are configured the same way.
# Defaults to the model already used for chunking (384 numbers per vector).
EMBED_MODEL = os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2")

_model = None


def _load():
  """Load the model once, the first time it is needed."""
  global _model
  if _model is None:
      from sentence_transformers import SentenceTransformer
      _model = SentenceTransformer(EMBED_MODEL)
  return _model


def embed_texts(texts):
  """Return one vector (list of floats) per input string, normalized for cosine similarity."""
  vectors = _load().encode(list(texts), normalize_embeddings=True)
  return [[float(x) for x in v] for v in vectors]