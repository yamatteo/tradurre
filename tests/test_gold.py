"""Tests for the gold chapter (`tradurre/services/gold.py`, `scripts/gold_export.py`)."""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tradurre.app import app
from tradurre.db import get_connection
from tradurre.services.gold import book_beads, boundaries, chapter_beads, read_tsv, score, write_tsv

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

def _script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent.parent / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gold_export = _script("gold_export")
gold_score = _script("gold_score")


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


# --- Scoring ---

GOLD = [("1", "1"), ("Marie arriva.", "Marie arrivò."), ("Il pleuvait.", ""), ("Paul partit.", "Paul partì.")]


def _f(result):
    return (result.precision, result.recall, result.f1)


def test_boundaries_count_characters_without_whitespace():
    assert boundaries([("Il pleut.", "Piove."), ("", "Sì.")]) == ("Ilpleut.", "Piove.Sì.", [(8, 6), (8, 9)])


def test_identical_lists_score_one():
    result = score(GOLD, GOLD)
    assert _f(result) == (1, 1, 1)
    assert (result.gold_count, result.predicted_count, result.missed) == (3, 3, [])


def test_merged_beads_lose_recall_not_precision():
    merged = [GOLD[0], ("Marie arriva. Il pleuvait.", "Marie arrivò."), GOLD[3]]
    result = score(GOLD, merged)
    assert (result.precision, result.recall) == (1, 2 / 3)
    assert result.missed == [(1, 1)]


def test_missed_runs_longest_first():
    gold = [(f"S{k}.", f"T{k}.") for k in range(7)]
    # Gold boundaries after beads 0..5: 2 and 3 are missed (one run), then 5.
    predicted = [gold[0], gold[1], ("S2. S3. S4.", "T2. T3. T4."), ("S5. S6.", "T5. T6.")]
    assert score(gold, predicted).missed == [(2, 3), (5, 5)]


def test_chapter_inside_a_longer_book():
    book = [("Avant.", "Prima.")] + GOLD + [("Après.", "Dopo.")]
    assert _f(score(GOLD, book)) == (1, 1, 1)


def test_segmentation_and_whitespace_do_not_matter():
    resegmented = [("1", "1"), ("Marie  arriva.", "Marie\narrivò."), ("Il pleu vait.", ""), ("Paul partit.", "Paul partì.")]
    assert _f(score(GOLD, resegmented)) == (1, 1, 1)


def test_one_sided_gold_bead_predicted_right():
    gold = [("Il pleuvait.", ""), ("Paul partit.", "Paul partì.")]
    assert _f(score(gold, [("Avant.", "Prima.")] + gold)) == (1, 1, 1)


def test_one_sided_gold_bead_predicted_wrong():
    gold = [("Il pleuvait.", ""), ("Paul partit.", "Paul partì.")]
    assert _f(score(gold, [("Il pleuvait. Paul partit.", "Paul partì.")])) == (0, 0, 0)


def test_gold_not_in_the_prediction():
    with pytest.raises(ValueError, match="the gold chapter doesn't match the current extraction"):
        score(GOLD, [("Autre chose.", "Altro.")])


def test_book_beads_returns_every_bead(db_path, book):
    conn = get_connection(db_path)
    try:
        beads = book_beads(conn, book["id"])
    finally:
        conn.close()
    assert len(beads) == 7
    assert beads[0] == ("Un avant-propos.", "Una premessa.", False)


def test_score_script_on_the_docx_pair(tmp_path, capsys):
    (tmp_path / "livre.docx").write_bytes(SOURCE)
    (tmp_path / "libro.docx").write_bytes(TARGET)
    gold = tmp_path / "gold.tsv"
    write_tsv(gold, [("1", "1"), ("Marie arriva.", "Marie arrivò."), ("Il pleuvait.", "Pioveva.")])
    argv = ["--gold", str(gold), "--source", str(tmp_path / "livre.docx"), "--target", str(tmp_path / "libro.docx")]
    assert gold_score.main(argv) == 0
    out = capsys.readouterr().out
    assert "F1 1.000" in out and "7 beads" in out


def test_score_script_refuses_a_missing_file(tmp_path, capsys):
    assert gold_score.main(["--gold", str(tmp_path / "nope.tsv")]) == 1
    assert "not found" in capsys.readouterr().err
