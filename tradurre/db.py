import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path

from fastapi import Request

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pairs (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    source_html TEXT NOT NULL,
    target_html TEXT NOT NULL DEFAULT '',
    source_text TEXT NOT NULL,
    target_text TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'draft',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE(project_id, position)
);

CREATE INDEX IF NOT EXISTS idx_pairs_project ON pairs(project_id, position);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS translation_memory USING fts5(
    source_text,
    target_text,
    project_id UNINDEXED,
    pair_id UNINDEXED,
    tokenize='unicode61 remove_diacritics 2'
);
"""

_FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS pairs_ai AFTER INSERT ON pairs BEGIN
    INSERT INTO translation_memory(rowid, source_text, target_text, project_id, pair_id)
    VALUES (new.rowid, new.source_text, new.target_text, new.project_id, new.id);
END;

CREATE TRIGGER IF NOT EXISTS pairs_ad AFTER DELETE ON pairs BEGIN
    DELETE FROM translation_memory WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS pairs_au AFTER UPDATE ON pairs BEGIN
    DELETE FROM translation_memory WHERE rowid = old.rowid;
    INSERT INTO translation_memory(rowid, source_text, target_text, project_id, pair_id)
    VALUES (new.rowid, new.source_text, new.target_text, new.project_id, new.id);
END;
"""


_TEXT_SCHEMA = """
CREATE TABLE documents (
    id         INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    side       TEXT NOT NULL CHECK (side IN ('source', 'target')),
    filename   TEXT NOT NULL,
    format     TEXT NOT NULL CHECK (format IN ('pdf', 'docx', 'txt')),
    UNIQUE (project_id, side)
);
CREATE TABLE blocks (
    id          INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ord         INTEGER NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('paragraph', 'heading', 'footnote', 'running_head',
                    'page_number', 'front_matter', 'back_matter', 'other')),
    excluded    INTEGER NOT NULL DEFAULT 0 CHECK (excluded IN (0, 1)),
    page        INTEGER,            -- logical page in the edition, for diagnostics; NULL if unknown
    UNIQUE (document_id, ord)
);
CREATE TABLE beads (
    id         INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ord        INTEGER NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    method     TEXT NOT NULL CHECK (method IN ('anchor', 'length', 'embedding', 'llm', 'manual')),
    reviewed   INTEGER NOT NULL DEFAULT 0 CHECK (reviewed IN (0, 1)),
    UNIQUE (project_id, ord)
);
CREATE TABLE segments (
    id            INTEGER PRIMARY KEY,
    block_id      INTEGER NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    ord           INTEGER NOT NULL,
    text          TEXT NOT NULL,
    original_text TEXT NOT NULL,    -- as extracted; text edits never change it
    bead_id       INTEGER REFERENCES beads(id),   -- NULL iff the block is excluded
    UNIQUE (block_id, ord)
);
CREATE INDEX idx_segments_bead ON segments(bead_id);
"""

_OPERATIONS_SCHEMA = """
CREATE TABLE operations (
    id         INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    changes    TEXT NOT NULL,                -- JSON list of [table, id, before, after]
    undone     INTEGER NOT NULL DEFAULT 0 CHECK (undone IN (0, 1)),
    created_at TEXT NOT NULL
);
CREATE INDEX idx_operations_project ON operations(project_id, id);
"""

# What each import (and, from Stage 5, each alignment run) did: counts, timings and warnings, kept in the project
# (SPEC §3.1.5, §4 "Debuggable"). Not operations: never undone.
_RUNS_SCHEMA = """
CREATE TABLE runs (
    id          INTEGER PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('import', 'align')),
    created_at  TEXT NOT NULL,
    app_version TEXT NOT NULL,
    stats       TEXT NOT NULL              -- JSON object
);
CREATE INDEX idx_runs_project ON runs(project_id, id);
CREATE TABLE warnings (
    id      INTEGER PRIMARY KEY,
    run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    side    TEXT CHECK (side IN ('source', 'target')),   -- NULL: the whole run
    message TEXT NOT NULL
);
"""


# Bead search index (PLAN.md, "Search index"): one FTS5 row per bead, rowid = bead id, kept in sync by triggers
# (which also fire for undo/redo, the layer builder and cascading deletes). The text is folded like
# `tradurre.domain.search.fold`: the tokenizer drops case and accents, ligatures are spelled out here.


def _fold_sql(expr: str) -> str:
    for ligature, spelled in (("œ", "oe"), ("Œ", "OE"), ("æ", "ae"), ("Æ", "AE")):
        expr = f"replace({expr}, '{ligature}', '{spelled}')"
    return expr


def _side_text_sql(side: str) -> str:
    return (
        "coalesce((SELECT group_concat(s.text, ' ' ORDER BY bl.ord, s.ord) FROM segments s "
        "JOIN blocks bl ON bl.id = s.block_id JOIN documents d ON d.id = bl.document_id "
        f"WHERE s.bead_id = b.id AND d.side = '{side}'), '')"
    )


def _reindex_sql(bead: str) -> str:
    """Statements (one per line, inside a trigger body) that rebuild the index row of bead `bead`."""
    return (
        f"    DELETE FROM bead_index WHERE rowid = {bead};\n"
        f"    INSERT INTO bead_index (rowid, source, target, project_id) SELECT b.id, "
        f"{_fold_sql(_side_text_sql('source'))}, {_fold_sql(_side_text_sql('target'))}, b.project_id "
        f"FROM beads b WHERE b.id = {bead};\n"
    )


_BEAD_INDEX_SCHEMA = f"""
CREATE VIRTUAL TABLE bead_index USING fts5(
    source, target, project_id UNINDEXED, tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TRIGGER segments_bi_ai AFTER INSERT ON segments BEGIN
{_reindex_sql("new.bead_id")}END;
CREATE TRIGGER segments_bi_ad AFTER DELETE ON segments BEGIN
{_reindex_sql("old.bead_id")}END;
CREATE TRIGGER segments_bi_au AFTER UPDATE OF text, ord, bead_id ON segments BEGIN
{_reindex_sql("old.bead_id")}{_reindex_sql("new.bead_id")}END;
CREATE TRIGGER beads_bi_ai AFTER INSERT ON beads BEGIN
{_reindex_sql("new.id")}END;
CREATE TRIGGER beads_bi_ad AFTER DELETE ON beads BEGIN
    DELETE FROM bead_index WHERE rowid = old.id;
END;
INSERT INTO bead_index (rowid, source, target, project_id) SELECT b.id, {_fold_sql(_side_text_sql('source'))}, \
{_fold_sql(_side_text_sql('target'))}, b.project_id FROM beads b;
"""


def get_db_path() -> Path:
    path = Path.home() / ".tradurre"
    path.mkdir(parents=True, exist_ok=True)
    return path / "tradurre.db"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = get_db_path()
    # timeout: a writer waits this long for the write lock (e.g. behind a big import's writes) before failing.
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request, closed when it ends."""
    conn = get_connection(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def _run_script(conn: sqlite3.Connection, script: str) -> None:
    """Run a multi-statement SQL script one statement at a time.

    Unlike `executescript`, this doesn't commit first, so it stays inside the
    caller's transaction.
    """
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            conn.execute(buffer)
            buffer = ""
    if buffer.strip():
        raise ValueError(f"Incomplete SQL statement: {buffer.strip()[:80]}")


def _m001_pairs(conn: sqlite3.Connection) -> None:
    """The v0.1 schema; a pre-migration database (user_version 0) passes through."""
    _run_script(conn, _SCHEMA)
    _run_script(conn, _FTS_SCHEMA)
    _run_script(conn, _FTS_TRIGGERS)

    # Hierarchy columns (section/paragraph), added after the first v0.1 release
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(pairs)")}
    for col in ("section", "paragraph"):
        if col not in columns:
            conn.execute(f"ALTER TABLE pairs ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")


def _m002_text_alignment(conn: sqlite3.Connection) -> None:
    """Text layer (documents, blocks, segments) and alignment layer (beads); SPEC §2."""
    _run_script(conn, _TEXT_SCHEMA)


def _m003_operations(conn: sqlite3.Connection) -> None:
    """Operation log for undo/redo (tradurre.domain.history)."""
    _run_script(conn, _OPERATIONS_SCHEMA)


def _m004_bead_index(conn: sqlite3.Connection) -> None:
    """FTS5 search index over beads, kept in sync by triggers (PLAN.md, "Search index")."""
    _run_script(conn, _BEAD_INDEX_SCHEMA)


def _m005_runs(conn: sqlite3.Connection) -> None:
    """Import/alignment runs and their warnings (PLAN.md, "Import warnings and run metadata")."""
    _run_script(conn, _RUNS_SCHEMA)


# Applied in order; migration n sets PRAGMA user_version = n. Never edit an applied one.
MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [
    _m001_pairs,
    _m002_text_alignment,
    _m003_operations,
    _m004_bead_index,
    _m005_runs,
]


def init_db(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > len(MIGRATIONS):
        raise RuntimeError(
            f"database schema version {current} is newer than this version of Tradurre "
            f"supports ({len(MIGRATIONS)}); upgrade Tradurre"
        )
    for version, migrate in enumerate(MIGRATIONS, start=1):
        if version <= current:
            continue
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            migrate(conn)
            conn.execute(f"PRAGMA user_version = {version}")
