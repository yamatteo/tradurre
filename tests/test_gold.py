"""Tests for the gold book (`tradurre/services/gold.py`, `scripts/gold_export.py`, `scripts/gold_score.py`)."""

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tradurre.app import app
from tradurre.db import get_connection
from tradurre.services.gold import Layer, layer_from_json, layer_to_json, read_layer, score

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


def _read(db_path, book_id):
    conn = get_connection(db_path)
    try:
        return read_layer(conn, book_id)
    finally:
        conn.close()


def _exclude_first_block(client, book):
    block_id = book["beads"][0]["source"][0]["block_id"]  # "Un avant-propos."
    assert client.post(f"/api/v2/books/{book['id']}/blocks/{block_id}/exclude").status_code == 200


def _review_all(client, book_id):
    beads = client.get(f"/api/v2/books/{book_id}").json()["beads"]
    assert client.post(f"/api/v2/books/{book_id}/reviewed",
                       json={"bead_ids": [b["id"] for b in beads], "reviewed": True}).status_code == 200


# --- Scoring, on hand-built layers ---

def _layer(source, target):
    n = 1 + max(bead for _, bead in source + target if bead is not None)
    return Layer(source, target, [True] * n)


GOLD = _layer(
    [("Titre.", None), ("Marie arriva.", 0), ("Il pleuvait.", 1), ("Paul partit.", 2), ("Fin.", 3)],
    [("Titolo.", None), ("Marie arrivò.", 0), ("Pioveva.", 1), ("Paul partì.", 2), ("Fine.", 3)],
)


def _metrics(result):
    return (result.alignment_precision, result.alignment_recall, result.alignment_f1,
            result.exclusion_precision, result.exclusion_recall, result.exclusion_f1)


def test_identical_layers_score_one():
    result = score(GOLD, GOLD)
    assert _metrics(result) == (1, 1, 1, 1, 1, 1)
    assert (result.gold_boundaries, result.predicted_boundaries, result.missed) == (3, 3, [])
    assert result.excluded_chars == {"source": (6, 6), "target": (7, 7)}


def test_merged_beads_lose_recall_not_precision():
    merged = _layer(
        [("Titre.", None), ("Marie arriva.", 0), ("Il pleuvait.", 0), ("Paul partit.", 1), ("Fin.", 2)],
        [("Titolo.", None), ("Marie arrivò.", 0), ("Pioveva.", 0), ("Paul partì.", 1), ("Fine.", 2)],
    )
    result = score(GOLD, merged)
    assert (result.alignment_precision, result.alignment_recall) == (1, 2 / 3)
    assert result.missed == [(0, 0)]


def test_kept_block_is_charged_to_exclusion_only():
    # The prediction keeps the gold's excluded title as a one-sided bead.
    kept = _layer(
        [("Titre.", 0), ("Marie arriva.", 1), ("Il pleuvait.", 2), ("Paul partit.", 3), ("Fin.", 4)],
        [("Titolo.", None), ("Marie arrivò.", 1), ("Pioveva.", 2), ("Paul partì.", 3), ("Fine.", 4)],
    )
    result = score(GOLD, kept)
    assert result.alignment_f1 == 1
    assert (result.exclusion_precision, result.exclusion_recall) == (1, 7 / 13)
    assert result.excluded_chars == {"source": (6, 0), "target": (7, 7)}


def test_excluded_text_block_loses_exclusion_precision():
    dropped = _layer(
        [("Titre.", None), ("Marie arriva.", 0), ("Il pleuvait.", None), ("Paul partit.", 2), ("Fin.", 3)],
        [("Titolo.", None), ("Marie arrivò.", 0), ("Pioveva.", 1), ("Paul partì.", 2), ("Fine.", 3)],
    )
    result = score(GOLD, dropped)
    assert result.exclusion_recall == 1
    assert result.exclusion_precision == 13 / 24
    assert result.alignment_f1 == 1  # "Pioveva." stays a bead of its own on the target side


def test_segmentation_and_whitespace_do_not_matter():
    resegmented = _layer(
        [("Titre.", None), ("Marie", 0), (" arriva.", 0), ("Il  pleuvait.", 1), ("Paul partit.", 2), ("Fin.", 3)],
        [("Titolo.", None), ("Marie\narrivò.", 0), ("Pioveva.", 1), ("Paul partì.", 2), ("Fine.", 3)],
    )
    assert _metrics(score(GOLD, resegmented)) == (1, 1, 1, 1, 1, 1)


def test_different_text_is_refused_naming_the_side():
    other = _layer(GOLD.source, [("Altro.", 0)])
    with pytest.raises(ValueError, match=r"the gold doesn't match the current extraction \(target\)"):
        score(GOLD, other)


def test_empty_set_conventions():
    one = _layer([("Une phrase.", 0)], [("Una frase.", 0)])
    # No boundaries and no exclusions on either side: everything is 1.
    assert _metrics(score(one, one)) == (1, 1, 1, 1, 1, 1)
    # The gold has a boundary and excludes nothing; the prediction finds no boundary and excludes something.
    gold = _layer([("Un.", 0), ("Deux.", 1)], [("Uno.", 0), ("Due.", 1)])
    predicted = _layer([("Un.", None), ("Deux.", 0)], [("Uno.", 0), ("Due.", 0)])
    result = score(gold, predicted)
    assert (result.alignment_precision, result.alignment_recall, result.alignment_f1) == (0, 0, 0)
    # Exclusion: nothing in the gold, something predicted → precision 0 (no hits), recall 0 (only the gold set is
    # empty). Alignment above: only the predicted set is empty → precision 0.
    assert (result.exclusion_precision, result.exclusion_recall, result.exclusion_f1) == (0, 0, 0)


def test_json_round_trip():
    assert layer_from_json(json.loads(json.dumps(layer_to_json(GOLD)))) == GOLD
    with pytest.raises(ValueError, match="unknown gold format"):
        layer_from_json({"format": 2})


# --- Reading a book, and the scripts ---

def test_read_layer_marks_excluded_segments(client, db_path, book):
    _exclude_first_block(client, book)
    layer = _read(db_path, book["id"])
    assert layer.source[0] == ("Un avant-propos.", None)
    assert layer.target[0] == ("Una premessa.", 0)  # the target side is still in a (now one-sided) bead
    assert layer.source[1] == ("1", 1)
    assert len(layer.reviewed) == 7


def test_read_layer_unknown_book(db_path, book):
    with pytest.raises(ValueError, match="book nope not found"):
        _read(db_path, "nope")


def test_export_refuses_an_unreviewed_book_then_writes(client, db_path, book, tmp_path, capsys):
    _exclude_first_block(client, book)
    out = tmp_path / "gold.json"
    argv = [book["id"], "--db", str(db_path), "--out", str(out)]
    assert gold_export.main(argv) == 1
    assert "7 of 7 beads of the book are not reviewed" in capsys.readouterr().err
    assert not out.exists()

    _review_all(client, book["id"])
    assert gold_export.main(argv) == 0
    assert "7 beads, 1 one-sided; excluded segments: source 1, target 0" in capsys.readouterr().out
    assert layer_from_json(json.loads(out.read_text(encoding="utf-8"))) == _read(db_path, book["id"])


def test_score_script_on_the_docx_pair(client, db_path, book, tmp_path, capsys):
    _exclude_first_block(client, book)
    _review_all(client, book["id"])
    gold = tmp_path / "gold.json"
    assert gold_export.main([book["id"], "--db", str(db_path), "--out", str(gold)]) == 0
    (tmp_path / "livre.docx").write_bytes(SOURCE)
    (tmp_path / "libro.docx").write_bytes(TARGET)
    capsys.readouterr()

    argv = ["--gold", str(gold), "--source", str(tmp_path / "livre.docx"), "--target", str(tmp_path / "libro.docx")]
    assert gold_score.main(argv) == 0
    out = capsys.readouterr().out
    assert "alignment: precision 1.000  recall 1.000  F1 1.000" in out
    assert "exclusion: precision 0.000  recall 0.000" in out
    assert "beads: 7 gold, 7 predicted" in out


def test_score_script_refuses_a_missing_file(tmp_path, capsys):
    assert gold_score.main(["--gold", str(tmp_path / "nope.json")]) == 1
    assert "not found" in capsys.readouterr().err
