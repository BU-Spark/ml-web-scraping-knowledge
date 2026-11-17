"""Database schema tests.

Static checks always run. Live checks need a local, disposable Postgres with pgvector (e.g.
Postgres.app or Docker) AND the scraped pages in data/output/scrape/clean/ (gitignored; nothing
scraped is stored in this file):
    createdb ku_test
    TEST_DATABASE_URL=postgresql://<user>@localhost:5432/ku_test python3 -m pytest tests/test_database.py
Each live test runs in its own schema that is dropped afterwards. Never point TEST_DATABASE_URL at the
shared database. Live tests load one real public page (the Bain page behind the pilot unit), read
at runtime.
"""
import json
import os
import re
import uuid
from pathlib import Path

import pytest

from database import migrate

TEST_URL = os.environ.get("TEST_DATABASE_URL")
SQL = (migrate.MIGRATIONS_DIR / "001_init.sql").read_text(encoding="utf-8")
CLEAN_DOC = Path("data/output/scrape/clean/b6fe62e39020a043.json")
CATEGORIES = {"Sales Methodology and Process", "Segmentation and Territory", "Enablement Operations"}


# ---------- static checks (no database needed) ----------

def test_migrations_are_numbered_and_unique():
    names = [p.name for p in migrate.migration_files()]
    assert names and names[0] == "001_init.sql"
    numbers = [n[:3] for n in names]
    assert len(numbers) == len(set(numbers))


def test_embedding_dimension_is_384():
    assert re.findall(r"embedding\s+vector\((\d+)\)", SQL) == ["384"]


def test_three_categories_seeded_by_name():
    seeded = re.search(r"INSERT INTO categories \(name\) VALUES(.*?);", SQL, re.S).group(1)
    assert set(re.findall(r"'([^']+)'", seeded)) == CATEGORIES


def test_served_view_checks_every_level():
    view = SQL[SQL.index("CREATE VIEW served_units"):]
    for col in ("u.source_type", "c.visibility", "d.visibility", "u.sensitivity", "c.sensitivity", "d.sensitivity"):
        assert col in view
    assert "public_units" not in SQL


# ---------- live checks ----------

live = pytest.mark.skipif(not TEST_URL or not CLEAN_DOC.exists(),
                          reason="needs TEST_DATABASE_URL and the scraped pages in data/output")


@pytest.fixture
def conn():
    psycopg = pytest.importorskip("psycopg")
    schema = "test_" + uuid.uuid4().hex[:8]
    with psycopg.connect(TEST_URL, autocommit=True) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        c.execute(f"CREATE SCHEMA {schema}")
        c.execute(f"SET search_path TO {schema}, public")
        try:
            migrate.migrate(c, log=lambda *_: None)
            yield c
        finally:
            c.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture
def bain(conn):
    """Load the real Bain document, its first chunk, and a unit shaped like the pilot unit."""
    doc = json.loads(CLEAN_DOC.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO documents (doc_id, url, canonical_url, domain, publisher, title, author, "
        "published_date, retrieved_at, category, visibility) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Enablement Operations', %s)",
        (doc["doc_id"], doc["url"], doc["canonical_url"], doc["domain"], doc["publisher"], doc["title"],
         doc["author"], doc["published_date"], doc["retrieved_at"], doc["visibility"]))
    section = doc["sections"][0]
    text = section["text"][:884]
    chunk_id = "sem-test-" + doc["doc_id"]
    conn.execute(
        "INSERT INTO chunks (chunk_id, doc_id, section_id, section_index, chunk_index, heading, "
        "char_start, char_end, text, category, visibility) "
        "VALUES (%s, %s, %s, 0, 0, %s, 0, %s, %s, 'Enablement Operations', 'public')",
        (chunk_id, doc["doc_id"], f"{doc['doc_id']}:section:0", section["heading"], len(text), text))
    first_sentence = text.split(". ")[0]
    add_unit(conn, "ku-" + chunk_id + "-0", chunk_id, first_sentence)
    return {"doc_id": doc["doc_id"], "chunk_id": chunk_id, "unit_id": "ku-" + chunk_id + "-0",
            "sentence": first_sentence}


def add_unit(c, unit_id, chunk_id, sentence, category="Enablement Operations", embedding=None):
    """Insert a unit with the pilot unit's field values; claim and quote are real text from the chunk."""
    c.execute(
        "INSERT INTO units (unit_id, chunk_id, section_id, claim, evidence_quote, level, unit_type, "
        "context, category, source_url, domain, publisher, source_type, sensitivity, source_tier, "
        "embedding) VALUES (%s, %s, 0, %s, %s, 'knowledge', 'statistic', "
        "'{\"company_size\": \"unknown\"}', %s, NULL, 'bain.com', 'Bain', 'external', 'public', 3, %s)",
        (unit_id, chunk_id, sentence, sentence, category, embedding))


@live
def test_migrate_is_idempotent(conn):
    assert migrate.migrate(conn, log=lambda *_: None) == []


@live
def test_real_unit_is_served_as_public(conn, bain):
    row = conn.execute("SELECT doc_id, visibility, sensitivity FROM served_units WHERE unit_id = %s",
                       (bain["unit_id"],)).fetchone()
    assert row == (bain["doc_id"], "public", "public")


@pytest.mark.parametrize("table,where", [
    ("documents", "doc_id = %s"), ("chunks", "doc_id = %s"),
])
@live
def test_internal_at_any_level_makes_unit_internal(conn, bain, table, where):
    conn.execute(f"UPDATE {table} SET visibility = 'internal', sensitivity = 'confidential' WHERE {where}",
                 (bain["doc_id"],))
    row = conn.execute("SELECT visibility, sensitivity FROM served_units").fetchone()
    assert row == ("internal", "confidential")


@live
def test_internal_unit_is_internal(conn, bain):
    conn.execute("UPDATE units SET source_type = 'internal', sensitivity = 'confidential'")
    assert conn.execute("SELECT visibility FROM served_units").fetchone()[0] == "internal"


@live
def test_unit_needs_existing_chunk(conn, bain):
    psycopg = pytest.importorskip("psycopg")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        add_unit(conn, "ku-orphan", "sem-missing", bain["sentence"])


@live
def test_unknown_category_rejected(conn, bain):
    psycopg = pytest.importorskip("psycopg")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        add_unit(conn, "ku-x", bain["chunk_id"], bain["sentence"], category="10. Enablement Operations")


@live
def test_dropped_levels_rejected(conn, bain):
    psycopg = pytest.importorskip("psycopg")
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("UPDATE units SET level = 'common_sense'")


@live
def test_wrong_vector_size_rejected(conn, bain):
    psycopg = pytest.importorskip("psycopg")
    with pytest.raises(psycopg.errors.DataException):
        conn.execute("UPDATE units SET embedding = '[0.1,0.2,0.3]'")


@live
def test_deleting_document_removes_its_chunks_and_units(conn, bain):
    conn.execute("DELETE FROM documents WHERE doc_id = %s", (bain["doc_id"],))
    assert conn.execute("SELECT count(*) FROM units").fetchone()[0] == 0
