"""Shared, normalized MiniLM embeddings for ingestion and query processing.

Migration 001 fixes the store to all-MiniLM-L6-v2 (384 dimensions). A different
model requires a migration and re-embedding, even if its dimensions happen to match.

Two backends run the SAME model weights, so their vectors are interchangeable:
  - "sentence-transformers" (default): PyTorch. Used by the batch pipeline on SCC.
  - "onnx": ONNX Runtime with the official ONNX export of the same model. Used by the
    MCP server, because it needs ~1/3 of the memory and a much smaller install.
Choose with EMBED_BACKEND. tests/test_embed_model.py checks the two agree (parity test).
"""
import os
from functools import lru_cache
from threading import Lock

EMBED_MODEL = "all-MiniLM-L6-v2"
MODEL_LOCK = Lock()

BACKENDS = ("sentence-transformers", "onnx")
# Official model repo, pinned so a silent upstream change cannot alter our vectors.
HF_REPO = "sentence-transformers/all-MiniLM-L6-v2"
HF_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
ONNX_FILE = "onnx/model.onnx"  # full precision; the quantized variants change vectors more
MAX_TOKENS = 256  # sentence_bert_config.json max_seq_length (tokenizer.json alone says 512)
ONNX_BATCH = 32   # bounds padding memory for large pipeline batches


def backend():
    name = os.environ.get("EMBED_BACKEND", BACKENDS[0])
    if name not in BACKENDS:
        raise ValueError(f"EMBED_BACKEND must be one of {', '.join(BACKENDS)}")
    return name


@lru_cache(maxsize=1)
def _load_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL, device="cpu")


@lru_cache(maxsize=1)
def _load_onnx():
    """Return (tokenizer, session); downloads the pinned files once into the HF cache."""
    import onnxruntime
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(hf_hub_download(HF_REPO, "tokenizer.json", revision=HF_REVISION))
    tokenizer.enable_truncation(MAX_TOKENS)
    tokenizer.enable_padding(pad_id=tokenizer.token_to_id("[PAD]"), pad_token="[PAD]")
    session = onnxruntime.InferenceSession(
        hf_hub_download(HF_REPO, ONNX_FILE, revision=HF_REVISION), providers=["CPUExecutionProvider"])
    return tokenizer, session


def _encode_onnx(texts):
    """The three steps sentence-transformers does for MiniLM: tokenize, mean-pool, normalize."""
    import numpy as np

    tokenizer, session = _load_onnx()
    out = []
    for start in range(0, len(texts), ONNX_BATCH):
        encoded = tokenizer.encode_batch(texts[start:start + ONNX_BATCH])
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        inputs = {"input_ids": np.array([e.ids for e in encoded], dtype=np.int64),
                  "attention_mask": mask,
                  "token_type_ids": np.array([e.type_ids for e in encoded], dtype=np.int64)}
        token_vectors = session.run(None, {i.name: inputs[i.name] for i in session.get_inputs()})[0]
        weights = mask[..., None].astype(np.float32)  # padding positions get weight 0
        pooled = (token_vectors * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        out.extend(pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None))
    return out


def embed_texts(texts):
    """Return normalized 384-dimensional vectors; load the model on first use."""
    if os.environ.get("EMBED_MODEL", EMBED_MODEL) != EMBED_MODEL:
        raise ValueError("EMBED_MODEL must match migration 001: all-MiniLM-L6-v2")
    use_onnx = backend() == "onnx"
    texts = list(texts)
    if not texts:
        return []
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("Embedding inputs must be nonempty strings")
    with MODEL_LOCK:
        if use_onnx:
            vectors = _encode_onnx(texts)
        else:
            vectors = _load_model().encode(texts, normalize_embeddings=True)
    return [[float(value) for value in vector] for vector in vectors]
