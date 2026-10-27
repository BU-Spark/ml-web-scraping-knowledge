"""Compare character chunking with semantic chunking on one scraped page.

Usage:
    python3 -m chunking.compare
    python3 -m chunking.compare --size 500 --overlap 50 --window 2 --percentile 15

Reads:   data/output/sections.json   (made by the scraper)
         questions.json              (optional: your test questions)
Writes:  data/output/chunks_character.json
         data/output/chunks_semantic.json
         data/output/comparison.html (open this in your browser for the demo)
"""
import argparse
import html
import json
from pathlib import Path

import numpy as np

from chunking.character import chunk_characters
from chunking.semantic import chunk_semantic, load_embeddings, make_chunker
from chunking.utils import build_document, measure, normalize_ws, spans_to_chunks


def find_section(headings, wanted):
    """Index of the heading that matches the wanted text (exact first, then 'contains')."""
    wanted = wanted.strip().lower()
    for i, h in enumerate(headings):
        if h.strip().lower() == wanted:
            return i
    for i, h in enumerate(headings):
        if wanted in h.lower():
            return i
    return None


def evaluate_questions(questions, chunks, doc, embed_fn):
    """For each question, find the single best chunk and judge it."""
    chunk_vectors = embed_fn([c["text"] for c in chunks])
    results = []
    for q in questions:
        section = find_section(doc["headings"], q["expected_heading"])
        if section is None:
            results.append({"question": q["question"], "verdict": "heading not found"})
            continue
        sa, sb = doc["section_ranges"][section]
        best = int(np.argmax(chunk_vectors @ embed_fn([q["question"]])[0]))
        chunk = chunks[best]
        overlap = max(0, min(chunk["char_end"], sb) - max(chunk["char_start"], sa))
        off_topic = round(100 * (1 - overlap / max(1, chunk["char_count"])))
        on_topic = overlap > 0
        has_answer = normalize_ws(q["answer_sentence"]) in normalize_ws(chunk["text"])
        if not on_topic:
            verdict = "wrong section"
        elif not has_answer:
            verdict = "answer cut off"
        elif off_topic >= 30:
            verdict = "complete, but padded with other topics"
        else:
            verdict = "clean hit"
        results.append({
            "question": q["question"],
            "expected_heading": doc["headings"][section],
            "chunk_id": chunk["chunk_id"],
            "off_topic_pct": off_topic,
            "answer_complete": has_answer,
            "verdict": verdict,
        })
    return results


def load_questions(path):
    """Questions that are fully filled in; blank template entries are skipped."""
    p = Path(path)
    if not p.exists():
        return []
    entries = json.loads(p.read_text())
    return [
        e for e in entries
        if e.get("question", "").strip() and e.get("expected_heading", "").strip()
        and e.get("answer_sentence", "").strip()
    ]


def render_html(source_url, settings, metrics, chunks_by_method, questions, retrieval):
    e = html.escape
    out = [
        "<!doctype html><html><head><meta charset='utf-8'><title>Chunking comparison</title><style>",
        "body{font-family:-apple-system,system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#222}",
        "table{border-collapse:collapse;margin:12px 0}td,th{border:1px solid #ccc;padding:6px 12px;text-align:left}",
        ".cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}",
        ".chunk{border-left:4px solid #2e8b57;background:#f4faf6;padding:8px 12px;margin:10px 0;font-size:14px}",
        ".chunk.mix{border-left-color:#d68910;background:#fef9ec}",
        ".chunk.warn{border-left-color:#c0392b;background:#fdf3f2}",
        ".tag{font-size:12px;color:#555;margin-bottom:4px}.bad{color:#c0392b;font-weight:600}",
        ".meta{color:#555;font-size:14px}",
        "</style></head><body>",
        "<h1>Character vs semantic chunking</h1>",
        f"<p class='meta'>Source: {e(source_url)}<br>Settings: {e(settings)}</p>",
        "<h2>Numbers</h2><table><tr><th></th><th>Character</th><th>Semantic</th></tr>",
    ]
    c, s = metrics["character"], metrics["semantic"]
    rows = [
        ("Chunks", c["chunks"], s["chunks"]),
        ("Smallest / average / largest (chars)",
         f"{c['min_chars']} / {c['avg_chars']} / {c['max_chars']}",
         f"{s['min_chars']} / {s['avg_chars']} / {s['max_chars']}"),
        ("Chunks cut mid-sentence", f"{c['pct_cut_mid_sentence']}%", f"{s['pct_cut_mid_sentence']}%"),
        ("Chunks mixing 2+ sections", f"{c['pct_mixing_sections']}%", f"{s['pct_mixing_sections']}%"),
    ]
    for label, a, b in rows:
        out.append(f"<tr><td>{e(label)}</td><td>{e(str(a))}</td><td>{e(str(b))}</td></tr>")
    out.append("</table>")

    if questions:
        out.append("<h2>Retrieval test</h2><table><tr><th>Question</th><th>Right section</th>"
                   "<th>Character: best chunk</th><th>Semantic: best chunk</th></tr>")
        for i, q in enumerate(questions):
            rc, rs = retrieval["character"][i], retrieval["semantic"][i]
            out.append(
                f"<tr><td>{e(q['question'])}</td><td>{e(rc.get('expected_heading', '?'))}</td>"
                f"<td>{e(rc['verdict'])}</td><td>{e(rs['verdict'])}</td></tr>")
        out.append("</table>")

    out.append("<h2>The chunks</h2><p class='meta'>Red = cut mid-sentence. Orange = mixes sections. Green = clean.</p>")
    out.append("<div class='cols'>")
    for method, title in (("character", "Character chunking"), ("semantic", "Semantic chunking")):
        out.append(f"<div><h3>{title}</h3>")
        for ch in chunks_by_method[method]:
            cut = ch["starts_mid_sentence"] or ch["ends_mid_sentence"]
            mixed = len(ch["headings_spanned"]) > 1
            cls = "warn" if cut else ("mix" if mixed else "")
            flags = []
            if cut:
                flags.append("<span class='bad'>cut mid-sentence</span>")
            if mixed:
                flags.append("mixes: " + e(" + ".join(ch["headings_spanned"])))
            tag = f"{e(ch['chunk_id'])} &middot; {ch['char_count']} chars"
            if flags:
                tag += " &middot; " + " &middot; ".join(flags)
            out.append(f"<div class='chunk {cls}'><div class='tag'>{tag}</div>{e(ch['text'])}</div>")
        out.append("</div>")
    out.append("</div></body></html>")
    return "\n".join(out)


def semantic_spans(doc, sections, chunker, min_chunk_chars):
    """Chunk each section on its own, then shift the spans to fit the joined text."""
    spans = []
    for idx, sec in enumerate(sections):
        base = doc["section_ranges"][idx][0]
        for start, end in chunk_semantic(sec["text"].strip(), chunker, min_chunk_chars):
            spans.append((base + start, base + end))
    return spans


def run(sections, source_url, chunker, embed_fn, questions, size=500, overlap=50,
        threshold=90, min_chunk_chars=200, out_dir="data/output"):
    """Chunk the page both ways, measure, test retrieval, and write the outputs."""
    doc = build_document(sections)
    chunks_by_method = {
        "character": spans_to_chunks(chunk_characters(doc["text"], size, overlap), doc, "character", source_url),
        "semantic": spans_to_chunks(semantic_spans(doc, sections, chunker, min_chunk_chars), doc, "semantic", source_url),
    }
    metrics = {m: measure(c) for m, c in chunks_by_method.items()}
    retrieval = {m: evaluate_questions(questions, c, doc, embed_fn) for m, c in chunks_by_method.items()} if questions else {}

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for m, c in chunks_by_method.items():
        (out / f"chunks_{m}.json").write_text(json.dumps(c, indent=2, ensure_ascii=False))
    settings = (f"character size={size}, overlap={overlap}; "
                f"semantic threshold={threshold}, min chunk chars={min_chunk_chars}")
    (out / "comparison.html").write_text(
        render_html(source_url, settings, metrics, chunks_by_method, questions, retrieval))
    return {"metrics": metrics, "retrieval": retrieval, "chunks": chunks_by_method}



def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sections", default="data/output/sections.json")
    parser.add_argument("--questions", default="questions.json")
    parser.add_argument("--url", help="which page to use if sections.json has several")
    parser.add_argument("--size", type=int, default=500, help="character chunk size")
    parser.add_argument("--overlap", type=int, default=50, help="character chunk overlap")
    parser.add_argument("--threshold", type=float, default=90,
                        help="semantic split sensitivity (percentile; higher = fewer, bigger chunks)")
    parser.add_argument("--min-chunk-chars", type=int, default=200,
                        help="semantic chunks shorter than this get merged into a neighbour")
    args = parser.parse_args()

    all_sections = json.loads(Path(args.sections).read_text())
    url = args.url or all_sections[0]["source_url"]
    sections = [s for s in all_sections if s["source_url"] == url]
    print(f"Page: {url} ({len(sections)} sections)")

    questions = load_questions(args.questions)
    if questions:
        print(f"Test questions: {len(questions)}")

    try:
        print("Loading the embedding model (the first run downloads it, then it works offline)...")
        embeddings = load_embeddings()
        chunker = make_chunker(embeddings, args.threshold, args.min_chunk_chars)
    except ImportError:
        raise SystemExit("Missing library. Run: python -m pip install -r requirements.txt")

    # Only used by the optional questions test.
    embed_fn = lambda texts: np.asarray(embeddings.embed_documents(list(texts)))

    result = run(sections, url, chunker, embed_fn, questions, args.size, args.overlap,
                 args.threshold, args.min_chunk_chars)

    print(f"\n{'':36}{'character':>12}{'semantic':>12}")
    c, s = result["metrics"]["character"], result["metrics"]["semantic"]
    for label, key in (("chunks", "chunks"), ("avg chars", "avg_chars"),
                       ("% cut mid-sentence", "pct_cut_mid_sentence"),
                       ("% mixing 2+ sections", "pct_mixing_sections")):
        print(f"{label:36}{c[key]:>12}{s[key]:>12}")
    print("\nOpen data/output/comparison.html in your browser to see the side-by-side.")


if __name__ == "__main__":
    main()