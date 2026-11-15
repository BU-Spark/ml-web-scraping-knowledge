"""Response formatting. Preserve citations and uncertainty; never expose vectors."""


def result(row):
    return {
        "unit_id": row["unit_id"], "claim": row["claim"], "level": row["level"],
        "unit_type": row["unit_type"], "category": row["category"],
        "topic": row.get("topic"), "context": row.get("context") or {},
        "outcome": row.get("outcome"), "tags": row.get("tags") or [],
        "visibility": row["visibility"], "sensitivity": row["sensitivity"],
        "cosine_distance": row.get("cosine_distance"),
        "citation": {
            "unit_id": row["unit_id"], "chunk_id": row["chunk_id"], "doc_id": row["doc_id"],
            "url": row.get("source_url") or row.get("canonical_url"),
            "source_file": row.get("source_file"),
            "title": row.get("page_title") or row.get("doc_title"),
            "publisher": row.get("publisher"), "published_date": row.get("published_date"),
            "heading": row.get("heading"), "heading_path": row.get("heading_path") or [],
            "evidence_quote": row["evidence_quote"],
            "section_index": row.get("section_id"),
            "char_start": row.get("char_start"), "char_end": row.get("char_end"),
            "offset_reference": "section.text",
        },
    }
