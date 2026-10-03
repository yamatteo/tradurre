"""Tests for tradurre.config."""

import importlib
from pathlib import Path

import tradurre.config


def test_db_path_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADURRE_DB", str(tmp_path / "other.db"))
    try:
        assert importlib.reload(tradurre.config).DB_PATH == tmp_path / "other.db"
    finally:
        monkeypatch.delenv("TRADURRE_DB")
        importlib.reload(tradurre.config)


def test_db_path_default(monkeypatch):
    monkeypatch.delenv("TRADURRE_DB", raising=False)
    assert importlib.reload(tradurre.config).DB_PATH == Path.home() / ".tradurre" / "tradurre.db"
