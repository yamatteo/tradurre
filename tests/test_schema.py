"""Tests for the text and alignment tables (migration 2)."""

import sqlite3

import pytest

from tradurre.db import get_connection, init_db

NEW_TABLES = ("documents", "blocks", "segments", "beads")


@pytest.fixture()
def conn(tmp_path):
    c = get_connection(tmp_path / "test.db")
    init_db(c)
    c.execute(
        "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
        "VALUES ('p1', 'Book', 'fr', 'it', 'now', 'now')"
    )
    c.execute("INSERT INTO documents (id, project_id, side, filename, format) VALUES (1, 'p1', 'source', 'a.pdf', 'pdf')")
    c.execute("INSERT INTO documents (id, project_id, side, filename, format) VALUES (2, 'p1', 'target', 'b.pdf', 'pdf')")
    c.execute("INSERT INTO blocks (id, document_id, ord, kind) VALUES (1, 1, 0, 'paragraph')")
    c.execute("INSERT INTO blocks (id, document_id, ord, kind) VALUES (2, 2, 0, 'paragraph')")
    c.execute("INSERT INTO beads (id, project_id, ord, confidence, method) VALUES (1, 'p1', 0, 0.9, 'anchor')")
    c.execute("INSERT INTO beads (id, project_id, ord, confidence, method) VALUES (2, 'p1', 1024, 0.5, 'length')")
    for seg_id, block_id, ord_, text, bead_id in [
        (1, 1, 0, "Bonjour.", 1),
        (2, 1, 1024, "Au revoir.", 2),
        (3, 2, 0, "Ciao.", 1),
        (4, 2, 1024, "Arrivederci.", 2),
    ]:
        c.execute(
            "INSERT INTO segments (id, block_id, ord, text, original_text, bead_id) VALUES (?, ?, ?, ?, ?, ?)",
            (seg_id, block_id, ord_, text, text, bead_id),
        )
    c.commit()
    yield c
    c.close()


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_user_version(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2


def test_delete_bead_with_segments_fails(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM beads WHERE id = 1")


def test_delete_project_cascades(conn):
    conn.execute("DELETE FROM projects WHERE id = 'p1'")
    assert [_count(conn, t) for t in NEW_TABLES] == [0, 0, 0, 0]


def test_duplicate_segment_ord(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO segments (block_id, ord, text, original_text) VALUES (1, 0, 'x', 'x')")


def test_duplicate_bead_ord(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO beads (project_id, ord, confidence, method) VALUES ('p1', 0, 1.0, 'manual')")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO blocks (document_id, ord, kind) VALUES (1, 1, 'chapter')",
        "INSERT INTO beads (project_id, ord, confidence, method) VALUES ('p1', 2, 1.0, 'magic')",
        "INSERT INTO beads (project_id, ord, confidence, method) VALUES ('p1', 2, 1.5, 'manual')",
        "INSERT INTO beads (project_id, ord, confidence, method) VALUES ('p1', 2, NULL, 'manual')",
        "INSERT INTO documents (project_id, side, filename, format) VALUES ('p1', 'left', 'c.txt', 'txt')",
    ],
    ids=["kind", "method", "confidence-range", "confidence-null", "side"],
)
def test_check_constraints(conn, sql):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql)
