"""Tests for the schema migration mechanism in tradurre.db."""

import sqlite3

import pytest

from tradurre import db as dbmod
from tradurre.db import (
    _FTS_SCHEMA,
    _FTS_TRIGGERS,
    _SCHEMA,
    MIGRATIONS,
    _m001_pairs,
    get_connection,
    init_db,
)
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.search import search_beads

_V1 = {"pairs", "translation_memory"}


@pytest.fixture()
def conn(tmp_path):
    c = get_connection(tmp_path / "test.db")
    yield c
    c.close()


def _user_version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _tables(conn):
    return {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_fresh_database(conn):
    init_db(conn)
    assert _user_version(conn) == len(MIGRATIONS)
    assert not _V1 & _tables(conn)


def test_runs_and_warnings_tables(conn):
    init_db(conn)
    assert {"runs", "warnings"} <= _tables(conn)
    assert _columns(conn, "runs") == {"id", "project_id", "kind", "created_at", "app_version", "stats"}
    assert _columns(conn, "warnings") == {"id", "run_id", "side", "message"}


def test_init_db_twice(conn):
    init_db(conn)
    init_db(conn)
    assert _user_version(conn) == len(MIGRATIONS)


def test_legacy_database(conn):
    # Built the way v0.1 did: executescript, ad hoc ALTER TABLE, user_version 0.
    conn.executescript(_SCHEMA)
    conn.executescript(_FTS_SCHEMA)
    conn.executescript(_FTS_TRIGGERS)
    for col in ("section", "paragraph"):
        conn.execute(f"ALTER TABLE pairs ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
        "VALUES ('p1', 'Book', 'fr', 'it', 'now', 'now')"
    )
    conn.execute(
        "INSERT INTO pairs (id, project_id, position, source_html, target_html, source_text, target_text, "
        "created_at, updated_at) VALUES ('a1', 'p1', 0, '<p>Bonjour</p>', '<p>Ciao</p>', 'Bonjour', 'Ciao', "
        "'now', 'now')"
    )
    conn.commit()
    assert _user_version(conn) == 0

    init_db(conn)

    # It opens; its v0.1 project and pairs are gone (migration 6).
    assert _user_version(conn) == len(MIGRATIONS)
    assert not _V1 & _tables(conn)
    assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0


def test_m001_alone_keeps_pairs_searchable(conn, monkeypatch):
    monkeypatch.setattr(dbmod, "MIGRATIONS", [_m001_pairs])
    init_db(conn)
    with conn:
        conn.execute(
            "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
            "VALUES ('p1', 'Book', 'fr', 'it', 'now', 'now')"
        )
        conn.execute(
            "INSERT INTO pairs (id, project_id, position, source_html, target_html, source_text, target_text, "
            "created_at, updated_at) VALUES ('a1', 'p1', 0, '<p>Bonjour</p>', '<p>Ciao</p>', 'Bonjour', 'Ciao', "
            "'now', 'now')"
        )
    assert {"section", "paragraph"} <= _columns(conn, "pairs")
    hits = conn.execute(
        "SELECT pair_id FROM translation_memory WHERE translation_memory MATCH 'Bonjour'"
    ).fetchall()
    assert [h[0] for h in hits] == ["a1"]


def test_v5_to_v6_drops_v1_and_keeps_books(conn, monkeypatch):
    monkeypatch.setattr(dbmod, "MIGRATIONS", MIGRATIONS[:5])
    init_db(conn)
    assert _user_version(conn) == 5
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        for pid, title in (("v1", "Old"), ("book", "Livre")):
            conn.execute(
                "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
                "VALUES (?, ?, 'fr', 'it', 'now', 'now')",
                (pid, title),
            )
        conn.execute(
            "INSERT INTO pairs (id, project_id, position, source_html, target_html, source_text, target_text, "
            "created_at, updated_at) VALUES ('a1', 'v1', 0, '<p>Bonjour</p>', '<p>Ciao</p>', 'Bonjour', 'Ciao', "
            "'now', 'now')"
        )
        (s1,), = create_document(conn, "book", "source", "fr.txt", "txt", [NewBlock("paragraph", ["Il partit."])])
        (t1,), = create_document(conn, "book", "target", "it.txt", "txt", [NewBlock("paragraph", ["Partì."])])
        append_beads(conn, "book", [NewBead([s1], [t1], 0.9, "length")])
    monkeypatch.setattr(dbmod, "MIGRATIONS", MIGRATIONS)

    init_db(conn)

    assert _user_version(conn) == 6
    assert not _V1 & _tables(conn)
    assert [r[0] for r in conn.execute("SELECT id FROM projects")] == ["book"]
    assert check_project(conn, "book") == []
    assert [h["project_id"] for h in search_beads(conn, "partit")] == ["book"]


def test_failing_migration_rolls_back(conn, monkeypatch):
    def bad(c):
        c.execute("CREATE TABLE half_done (x INTEGER)")
        raise RuntimeError("migration failed")

    monkeypatch.setattr(dbmod, "MIGRATIONS", [_m001_pairs, bad])
    with pytest.raises(RuntimeError, match="migration failed"):
        init_db(conn)
    assert _user_version(conn) == 1
    assert "half_done" not in _tables(conn)
    assert "pairs" in _tables(conn)


def test_newer_database_refused(conn):
    conn.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError, match="newer"):
        init_db(conn)


def test_run_script_rejects_incomplete_statement(conn):
    with pytest.raises(ValueError):
        dbmod._run_script(conn, "CREATE TABLE t (x INTEGER);\nCREATE TABLE u (")
