"""Embed validated knowledge units using the shared sentence-transformers model.

Run from the repository root:
    python3 -m data_pipeline.embedder [input_units_path] [output_units_path]
"""
import argparse
import json
import logging
from pathlib import Path
import sys

from chunking.semantic import MODEL_NAME, load_embeddings
from data_pipeline.extractor import build_embed_text

logger = logging.getLogger(__name__)

DEFAULT_IN_PATH = Path("data/output/knowledge_units_validated.json")
DEFAULT_OUT_PATH = Path("data/output/knowledge_units_embedded.json")


def embed_units(units, embed_fn=None, model_name=MODEL_NAME):
    """Populate `embed_text` and `embedding` (list of floats) for each knowledge unit."""
    if not units:
        return []

    for unit in units:
        if not unit.get("embed_text"):
            unit["embed_text"] = build_embed_text(unit)

    if embed_fn is None:
        model = load_embeddings(model_name=model_name)
        embed_fn = model.embed_documents

    texts = [u["embed_text"] for u in units]
    vectors = embed_fn(texts)

    embedded_units = []
    for unit, vec in zip(units, vectors):
        copy_unit = dict(unit)
        copy_unit["embedding"] = [float(x) for x in vec]
        embedded_units.append(copy_unit)

    logger.info(
        "EMBED: generated %s embeddings (dim=%s)",
        len(embedded_units),
        len(embedded_units[0]["embedding"]) if embedded_units else 0,
    )
    return embedded_units


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", nargs="?", default=str(DEFAULT_IN_PATH))
    parser.add_argument("output_path", nargs="?", default=str(DEFAULT_OUT_PATH))
    parser.add_argument("--model", default=MODEL_NAME)
    args = parser.parse_args()

    units = json.loads(Path(args.input_path).read_text(encoding="utf-8"))
    embedded = embed_units(units, model_name=args.model)

    out_path = Path(args.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(embedded, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("SAVE: wrote %s embedded units to %s", len(embedded), out_path)


if __name__ == "__main__":
    main()
