"""Tests for the database snapshots at start (tradurre.backup)."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from tradurre.app import app
from tradurre.backup import snapshot
from tradurre.db import get_connection, init_db

NOON = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db_path(tmp_path):
    """A database with one project row."""
    path = tmp_path / "tradurre.db"
    conn = get_connection(path)
    init_db(conn)
    with conn:
        conn.execute(
            "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
            "VALUES ('p1', 'Livre', 'fr', 'it', 'now', 'now')"
        )
    conn.close()
    return path


def _names(path):
    return sorted(p.name for p in (path.parent / "backups").iterdir())


def test_no_database(tmp_path):
    assert snapshot(tmp_path / "tradurre.db") is None
    assert not (tmp_path / "backups").exists()
    assert not (tmp_path / "tradurre.db").exists()


def test_snapshot_holds_the_data(db_path):
    target = snapshot(db_path, now=NOON)
    assert target == db_path.parent / "backups" / "tradurre-20261004-120000.db"
    conn = sqlite3.connect(target)
    try:
        assert conn.execute("SELECT title FROM projects").fetchall() == [("Livre",)]
    finally:
        conn.close()


def test_keeps_the_newest(db_path):
    for k in range(12):
        snapshot(db_path, now=NOON + timedelta(minutes=k))
    assert _names(db_path) == [f"tradurre-20261004-12{k:02d}00.db" for k in range(2, 12)]


def test_same_second(db_path):
    first = snapshot(db_path, now=NOON)
    second = snapshot(db_path, now=NOON)
    assert (first.name, second.name) == ("tradurre-20261004-120000.db", "tradurre-20261004-120000-2.db")
    assert _names(db_path) == ["tradurre-20261004-120000-2.db", "tradurre-20261004-120000.db"]


def test_newer_in_the_same_second_survives(db_path):
    snapshot(db_path, now=NOON)
    snapshot(db_path, now=NOON, keep=1)
    assert _names(db_path) == ["tradurre-20261004-120000-2.db"]


def test_failure_never_raises(db_path, capsys):
    (db_path.parent / "backups").write_text("not a folder")
    assert snapshot(db_path, now=NOON) is None
    assert capsys.readouterr().out.startswith("Tradurre: database snapshot failed:")


def _start(db_path, monkeypatch):
    monkeypatch.setattr("tradurre.config.DB_PATH", db_path)
    monkeypatch.setattr("tradurre.app.DB_PATH", db_path)
    with TestClient(app):
        pass


def test_app_start_takes_a_snapshot(db_path, monkeypatch):
    monkeypatch.delenv("TRADURRE_DEV", raising=False)
    _start(db_path, monkeypatch)
    (name,) = _names(db_path)
    assert name.startswith("tradurre-") and name.endswith(".db")


def test_dev_start_takes_none(db_path, monkeypatch):
    monkeypatch.setenv("TRADURRE_DEV", "1")
    _start(db_path, monkeypatch)
    assert not (db_path.parent / "backups").exists()


def test_default_name_is_local_time(db_path):
    # Read the clock on both sides of the call, so a minute boundary in between can't fail the test.
    before = datetime.now()
    target = snapshot(db_path)
    after = datetime.now()
    stamp = target.stem.removeprefix("tradurre-")[:13]
    assert stamp in {f"{before:%Y%m%d-%H%M}", f"{after:%Y%m%d-%H%M}"}
