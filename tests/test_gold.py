"""Tests for the gold chapter (`tradurre/services/gold.py`, `scripts/gold_export.py`)."""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tradurre.app import app
from tradurre.db import get_connection
from tradurre.services.gold import chapter_beads, read_tsv, write_tsv

from tests.test_books_api import _docx

SOURCE = _docx(
    ("paragraph", "Un avant-propos."),
    ("heading", "1"), ("paragraph", "Marie arriva."), ("paragraph", "Il pleuvait."),
    ("heading", "2"), ("paragraph", "Paul partit. Il ne dit rien."),
)
TARGET = _docx(
    ("paragraph", "Una premessa."),
    ("heading", "1"), ("paragraph", "Marie arrivò."), ("paragraph", "Pioveva."),
    ("heading", "2"), ("paragraph", "Paul partì. Non disse niente."),
)

_spec = importlib.util.spec_from_file_location("gold_export", Path(__file__).parent.parent / "scripts" / "gold_export.py")
gold_export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gold_export)


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr("tradurre.config.DB_PATH", path)
    monkeypatch.setattr("tradurre.app.DB_PATH", path)
    return path


@pytest.fixture()
def client(db_path):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def book(client):
    resp = client.post("/api/v2/books", files={"source": ("livre.docx", SOURCE), "target": ("libro.docx", TARGET)})
    assert resp.status_code == 201
    return client.get(f"/api/v2/books/{resp.json()['id']}").json()


def _chapter(db_path, book_id, chapter):
    conn = get_connection(db_path)
    try:
        return chapter_beads(conn, book_id, chapter)
    finally:
        conn.close()


def _cells(db_path, book_id, chapter):
    return [(source, target) for source, target, _ in _chapter(db_path, book_id, chapter)]


def _segment(book, text):
    return next(s for b in book["beads"] for side in ("source", "target") for s in b[side] if s["text"] == text)


def test_chapters_run_from_their_number_to_the_next(db_path, book):
    assert _cells(db_path, book["id"], 1) == [
        ("1", "1"), ("Marie arriva.", "Marie arrivò."), ("Il pleuvait.", "Pioveva."),
    ]
    assert _cells(db_path, book["id"], 2) == [
        ("2", "2"), ("Paul partit.", "Paul partì."), ("Il ne dit rien.", "Non disse niente."),
    ]


def test_unknown_chapter_or_book(db_path, book):
    with pytest.raises(ValueError, match="chapter 3 not found; the book has 2"):
        _chapter(db_path, book["id"], 3)
    with pytest.raises(ValueError, match="chapter 0 not found"):
        _chapter(db_path, book["id"], 0)
    with pytest.raises(ValueError, match="book nope not found"):
        _chapter(db_path, "nope", 1)


def test_cells_use_the_original_text(client, db_path, book):
    segment = _segment(book, "Marie arriva.")
    assert client.post(f"/api/v2/books/{book['id']}/segments/{segment['segment_id']}/edit",
                       json={"text": "Marie arriva tard."}).status_code == 200
    assert _cells(db_path, book["id"], 1)[1] == ("Marie arriva.", "Marie arrivò.")


def test_a_split_segment_gives_the_same_cell(client, db_path, book):
    before = _cells(db_path, book["id"], 2)
    segment = _segment(book, "Paul partit.")
    split = client.post(f"/api/v2/books/{book['id']}/segments/{segment['segment_id']}/split", json={"offset": 5})
    assert split.status_code == 200
    assert [s["text"] for s in split.json()["beads"][5]["source"]] == ["Paul", "partit."]
    assert _cells(db_path, book["id"], 2) == before


def test_tsv_round_trip(tmp_path):
    cells = [("Marie arriva.", "Marie arrivò."), ("Il pleuvait.", ""), ("", "Pioveva.")]
    path = tmp_path / "gold.tsv"
    write_tsv(path, cells)
    assert read_tsv(path) == cells


def test_export_refuses_an_unreviewed_chapter(client, db_path, book, tmp_path, capsys):
    out = tmp_path / "gold.tsv"
    argv = [book["id"], "1", "--db", str(db_path), "--out", str(out)]
    assert gold_export.main(argv) == 1
    assert "3 of 3 beads of chapter 1 are not reviewed" in capsys.readouterr().err
    assert not out.exists()

    # "Pioveva." moved down to chapter 2: the last bead of chapter 1 becomes one-sided.
    assert client.post(f"/api/v2/books/{book['id']}/beads/{book['beads'][3]['id']}/move",
                       json={"side": "target", "to": "next"}).status_code == 200
    chapter = [b["id"] for b in book["beads"][1:4]]
    assert client.post(f"/api/v2/books/{book['id']}/reviewed",
                       json={"bead_ids": chapter, "reviewed": True}).status_code == 200
    assert gold_export.main(argv) == 0
    assert "3 beads, 1 one-sided" in capsys.readouterr().out
    assert read_tsv(out) == [("1", "1"), ("Marie arriva.", "Marie arrivò."), ("Il pleuvait.", "")]
