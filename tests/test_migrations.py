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
    assert {"section", "paragraph"} <= _columns(conn, "pairs")


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

    assert _user_version(conn) == len(MIGRATIONS)
    assert conn.execute("SELECT source_text FROM pairs WHERE id = 'a1'").fetchone()[0] == "Bonjour"
    hits = conn.execute(
        "SELECT pair_id FROM translation_memory WHERE translation_memory MATCH 'Bonjour'"
    ).fetchall()
    assert [h[0] for h in hits] == ["a1"]


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
