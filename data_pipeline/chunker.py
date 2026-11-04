"""Semantic chunking entry point; retain chunking/ implementations and baseline.

Run from the repository root: python3 -m data_pipeline.chunker [threshold] [min_chunk_chars]
"""
from chunking.semantic import chunk_sections, chunk_semantic, load_embeddings, make_chunker, main

if __name__ == "__main__":
    main()
