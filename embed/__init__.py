"""Shared embedding model: the ONE place both the pipeline and the MCP server get embeddings from.

Stored knowledge units and incoming questions must be embedded with the same model, or vector
search compares incompatible numbers. data_pipeline/embedder.py (batch, on SCC) and mcp_server/
(per question, on Heroku) both import from here. Keep this package free of pipeline imports so
mcp_server/ can depend on it without pulling in scraper/chunking code.
"""
from embed.model import EMBED_MODEL, embed_texts  # noqa: F401
