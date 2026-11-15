"""Read-only, parameterized queries against migration 001's served_units view.

Never select embeddings into tool output. Cosine distance is used for ranking,
not as a probability or evidence-quality score. No approximate index is required.
"""
import math

# Every selected column belongs to served_units in migration 001.
FIELDS = """s.unit_id, s.chunk_id, s.doc_id, s.section_id, s.claim, s.evidence_quote,
 s.level, s.unit_type, s.context, s.outcome, s.topic, s.category, s.source_url,
 s.canonical_url, s.source_file, s.domain, s.publisher, s.published_date,
 s.page_title, s.doc_title, s.heading, s.heading_path, s.char_start, s.char_end,
 s.source_tier, s.tags, s.extracted_at, s.visibility, s.sensitivity"""


def literal_pattern(text):
    """Escape LIKE metacharacters so filters match user text literally."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def vector_literal(vector):
    values = [float(v) for v in vector]
    if len(values) != 384 or not all(math.isfinite(v) for v in values) or not any(values):
        raise ValueError("Search requires a finite, nonzero 384-dimensional vector")
    return "[" + ",".join(repr(v) for v in values) + "]"


def search(conn, vector, *, visibility, limit, category=None, topic=None,
           entities=(), context=None):
    from psycopg.rows import dict_row
    where = ["s.embedding IS NOT NULL", "s.visibility = ANY(%s)"]
    params = [list(visibility)]
    if category:
        where.append("s.category = %s")
        params.append(category)
    if topic:
        where.append("s.topic ILIKE %s")
        params.append(literal_pattern(topic))
    if entities:
        where.append("(" + " OR ".join(
            "concat_ws(' ', s.topic, s.claim, s.heading) ILIKE %s" for _ in entities) + ")")
        params.extend(literal_pattern(e) for e in entities)
    for key, value in (context or {}).items():
        where.append("s.context ->> %s ILIKE %s")
        params.extend((key, literal_pattern(value)))
    literal = vector_literal(vector)
    sql = f"""SELECT {FIELDS}, s.embedding <=> %s::vector AS cosine_distance
        FROM served_units s WHERE {' AND '.join(where)}
        ORDER BY cosine_distance, s.unit_id LIMIT %s"""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, [literal, *params, limit])
        return cur.fetchall()


def sources(conn, identifier, *, identifier_type, visibility, limit):
    from psycopg.rows import dict_row
    columns = {"unit_id": "s.unit_id", "chunk_id": "s.chunk_id",
               "doc_id": "s.doc_id", "url": "s.source_url"}
    if identifier_type not in columns:
        raise ValueError("identifier_type must be unit_id, chunk_id, doc_id, or url")
    sql = f"""SELECT {FIELDS}, c.text AS source_text,
        c.char_start AS chunk_char_start, c.char_end AS chunk_char_end
        FROM served_units s JOIN chunks c ON c.chunk_id = s.chunk_id
        WHERE {columns[identifier_type]} = %s AND s.visibility = ANY(%s)
        ORDER BY s.unit_id LIMIT %s"""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (identifier, list(visibility), limit))
        return cur.fetchall()
