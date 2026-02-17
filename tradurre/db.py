import sqlite3
from pathlib import Path

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


def get_db_path() -> Path:
    path = Path.home() / ".tradurre"
    path.mkdir(parents=True, exist_ok=True)
    return path / "tradurre.db"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.executescript(_FTS_SCHEMA)
    conn.executescript(_FTS_TRIGGERS)

    # Migration: add hierarchy columns (section/paragraph)
    for col in ("section", "paragraph"):
        try:
            conn.execute(
                f"ALTER TABLE pairs ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()
