"""Retrieval boundary; injectable dependencies keep offline tests independent of services."""
import logging

from database import queries
from database.connection import connect
from embed import embed_texts
from mcp_server.filters import (CATEGORIES, allowed_visibility, entity_aliases,
                                required_text, result_limit)
from mcp_server.ranking import result

logger = logging.getLogger(__name__)
EVIDENCE_NOTE = "Citations show what a source states; they do not establish effectiveness."


class RetrievalService:
    def __init__(self, connection_factory=connect, embed_fn=embed_texts):
        self.connection_factory = connection_factory
        self.embed_fn = embed_fn

    def search(self, query, *, category=None, topic=None, entity=None,
               role=None, industry=None, company_size=None, limit=5):
        query = required_text(query)
        limit = result_limit(limit)
        if category is not None and category not in CATEGORIES:
            raise ValueError("Unknown category")
        topic = required_text(topic, "topic", 200) if topic is not None else None
        entities = entity_aliases(entity) if entity is not None else ()
        context = {key: required_text(value, key, 200) for key, value in (
            ("who", role), ("industry", industry), ("company_size", company_size)) if value is not None}
        visibility = allowed_visibility()
        try:
            vectors = self.embed_fn([query])
            if len(vectors) != 1:
                raise ValueError("Expected one query embedding")
            vector = vectors[0]
            queries.vector_literal(vector)
            with self.connection_factory() as conn:
                rows = queries.search(conn, vector, visibility=visibility, limit=limit,
                                      category=category, topic=topic, entities=entities, context=context)
        except Exception as error:
            # Never emit DB URLs, caller text, internal passages, or third-party exception text.
            logger.error("Retrieval failed (%s)", type(error).__name__)
            raise RuntimeError("Knowledge retrieval is unavailable; check database and embedding configuration.") from None
        return {"status": "ok" if rows else "no_results", "query": query,
                "category": category, "results": [result(row) for row in rows],
                "message": ("Results ranked by cosine distance; lower is closer." if rows else
                            "No matching embedded knowledge units. Try a broader question or fewer filters; the store may not be populated."),
                "evidence_note": EVIDENCE_NOTE}

    def source(self, identifier, identifier_type="unit_id", limit=5):
        identifier = required_text(identifier, "identifier", 2000)
        limit = result_limit(limit)
        if identifier_type not in ("unit_id", "chunk_id", "doc_id", "url"):
            raise ValueError("identifier_type must be unit_id, chunk_id, doc_id, or url")
        visibility = allowed_visibility()
        try:
            with self.connection_factory() as conn:
                rows = queries.sources(conn, identifier, identifier_type=identifier_type,
                                       visibility=visibility, limit=limit)
        except Exception as error:
            logger.error("Source lookup failed (%s)", type(error).__name__)
            raise RuntimeError("Source lookup is unavailable; check database configuration.") from None
        results = []
        for row in rows:
            entry = result(row)
            entry["source_passage"] = {"text": row["source_text"],
                "char_start": row["chunk_char_start"], "char_end": row["chunk_char_end"],
                "offset_reference": "section.text"}
            results.append(entry)
        return {"status": "ok" if rows else "no_results", "results": results,
                "message": ("Supporting chunks from the stored corpus; results may be limited."
                            if rows else "No accessible stored source matches this identifier. Use an ID returned by a guidance tool."),
                "evidence_note": EVIDENCE_NOTE}
