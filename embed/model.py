"""Planned: shared embedding interface. Structure placeholder; the model is not chosen yet.

Candidates discussed: bge-m3 (~2 GB RAM, too big for a small Heroku dyno), bge-small, or a hosted
embedding API. Whatever is chosen, the pipeline and the MCP server must use it identically
(same model, same normalization), and the vector size must match the database column.
"""
import os

# Set via env var so SCC jobs and the Heroku server are configured the same way.
EMBED_MODEL = os.environ.get("EMBED_MODEL")


def embed_texts(texts):
    """Return one vector (list of floats) per input string, normalized for cosine similarity.

    Contract for both callers:
      - data_pipeline/embedder.py: embed_texts([unit["embed_text"] for unit in units])
      - mcp_server/retrieval.py:   embed_texts([question])[0]
    """
    raise NotImplementedError("Embedding model not chosen yet; see embed/model.py docstring.")
