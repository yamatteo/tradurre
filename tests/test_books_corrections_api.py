"""Tests for the corrections of the books API (/api/v2/books/{id}/…): every SPEC §3.3 correction over HTTP."""

import pytest
from fastapi.testclient import TestClient

from tradurre.app import app

# Beads after import (length aligner): (Marie arriva. | Marie arrivò.), (Il pleuvait. | Paul partì.),
# (Paul partit. Il ne dit rien. | Non disse niente.). The `gap` fixture corrects that into
# A (Marie arriva. | Marie arrivò.), B (Il pleuvait. | ), C (Paul partit. | Paul partì.),
# D (Il ne dit rien. | Non disse niente.), the layout with a one-sided bead most tests start from.
SOURCE = "Marie arriva.\n\nIl pleuvait.\n\nPaul partit. Il ne dit rien."
TARGET = "Marie arrivò.\n\nPaul partì. Non disse niente."


@pytest.fixture()
def client(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr("tradurre.config.DB_PATH", path)
    monkeypatch.setattr("tradurre.app.DB_PATH", path)
    with TestClient(app) as c:
        yield c


def _import(client, title="Contrefeu"):
    resp = client.post(
        "/api/v2/books",
        files={"source": ("fr.txt", SOURCE.encode()), "target": ("it.txt", TARGET.encode())},
        data={"title": title},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture()
def book(client):
    book_id = _import(client)
    return book_id, client.get(f"/api/v2/books/{book_id}").json()


@pytest.fixture()
def gap(client, book):
    """The book after two corrections: B's target segment moved on to C, then C split back into C and D."""
    book_id, data = book
    b = data["beads"][1]["id"]
    data = _post(client, book_id, f"beads/{b}/move", {"side": "target", "to": "next"}).json()
    c = data["beads"][2]
    data = _post(client, book_id, f"beads/{c['id']}/split", {
        "source_at": c["source"][1]["segment_id"], "target_at": c["target"][1]["segment_id"],
    }).json()
    assert _rows(data) == [
        (["Marie arriva."], ["Marie arrivò."]),
        (["Il pleuvait."], []),
        (["Paul partit."], ["Paul partì."]),
        (["Il ne dit rien."], ["Non disse niente."]),
    ]
    return book_id, data


def _post(client, book_id, path, body=None):
    return client.post(f"/api/v2/books/{book_id}/{path}", json=body)


def _ok(client, book_id, path, body=None):
    resp = _post(client, book_id, path, body)
    assert resp.status_code == 200, resp.json()
    assert client.get(f"/api/v2/books/{book_id}/check").json() == []
    return resp.json()


def _rows(book):
    return [([s["text"] for s in b["source"]], [s["text"] for s in b["target"]]) for b in book["beads"]]


def _segment(book, text):
    for bead in book["beads"]:
        for side in ("source", "target"):
            for seg in bead[side]:
                if seg["text"] == text:
                    return seg
    raise KeyError(text)


def test_fresh_book_has_nothing_to_undo(client, book):
    book_id, data = book
    assert (data["can_undo"], data["can_redo"]) == (False, False)
    resp = _post(client, book_id, "undo")
    assert (resp.status_code, resp.json()["detail"]) == (409, "Nothing to undo")
    assert _post(client, book_id, "redo").status_code == 409


def test_move_to_previous_and_next(client, gap):
    book_id, data = gap
    a, b = data["beads"][0]["id"], data["beads"][1]["id"]
    result = _ok(client, book_id, f"beads/{b}/move", {"side": "source", "to": "previous"})
    assert _rows(result)[0] == (["Marie arriva.", "Il pleuvait."], ["Marie arrivò."])
    assert len(result["beads"]) == 3  # B was left empty and deleted
    assert result["can_undo"] is True
    result = _ok(client, book_id, f"beads/{a}/move", {"side": "source", "to": "next"})
    assert _rows(result)[:2] == [
        (["Marie arriva."], ["Marie arrivò."]),
        (["Il pleuvait.", "Paul partit."], ["Paul partì."]),  # A's next bead is now C
    ]


def test_merge_next_and_split(client, gap):
    book_id, data = gap
    b = data["beads"][1]["id"]
    result = _ok(client, book_id, f"beads/{b}/merge-next")
    assert _rows(result)[1] == (["Il pleuvait.", "Paul partit."], ["Paul partì."])
    merged = result["beads"][1]
    assert (merged["method"], merged["confidence"]) == ("manual", 1.0)
    at = _segment(result, "Paul partit.")["segment_id"]
    result = _ok(client, book_id, f"beads/{b}/split", {"source_at": at, "target_at": None})
    assert _rows(result)[1:3] == [(["Il pleuvait."], ["Paul partì."]), (["Paul partit."], [])]


def test_reviewed(client, gap):
    book_id, data = gap
    ids = [data["beads"][0]["id"], data["beads"][2]["id"]]
    result = _ok(client, book_id, "reviewed", {"bead_ids": ids, "reviewed": True})
    assert [b["reviewed"] for b in result["beads"]] == [True, False, True, False]
    result = _ok(client, book_id, "reviewed", {"bead_ids": ids[:1], "reviewed": False})
    assert [b["reviewed"] for b in result["beads"]] == [False, False, True, False]


def test_reviewed_run_is_one_undo(client, gap):
    book_id, data = gap
    ids = [b["id"] for b in data["beads"][:3]]
    result = _ok(client, book_id, "reviewed", {"bead_ids": ids, "reviewed": True})
    assert [b["reviewed"] for b in result["beads"]] == [True, True, True, False]
    result = _ok(client, book_id, "undo")
    assert [b["reviewed"] for b in result["beads"]] == [False, False, False, False]


def test_reviewed_ignores_an_old_skim_field(client, gap):
    book_id, data = gap
    body = {"bead_ids": [data["beads"][0]["id"]], "reviewed": True, "skim": True}
    result = _ok(client, book_id, "reviewed", body)
    assert [b["reviewed"] for b in result["beads"]] == [True, False, False, False]


def test_edit_split_join_segment(client, gap):
    book_id, data = gap
    seg = _segment(data, "Il pleuvait.")["segment_id"]
    result = _ok(client, book_id, f"segments/{seg}/edit", {"text": "Il pleuvait fort."})
    assert _rows(result)[1] == (["Il pleuvait fort."], [])
    result = _ok(client, book_id, f"segments/{seg}/split", {"offset": 11})
    assert _rows(result)[1] == (["Il pleuvait", "fort."], [])
    result = _ok(client, book_id, f"segments/{seg}/join-next")
    assert _rows(result)[1] == (["Il pleuvait fort."], [])


def test_join_across_beads_merges_them(client, gap):
    book_id, data = gap
    seg = _segment(data, "Paul partit.")["segment_id"]
    result = _ok(client, book_id, f"segments/{seg}/join-next")
    assert _rows(result)[2] == (["Paul partit. Il ne dit rien."], ["Paul partì.", "Non disse niente."])


def test_exclude_and_include_block(client, book):
    book_id, data = book
    block = _segment(data, "Il pleuvait.")["block_id"]
    result = _ok(client, book_id, f"blocks/{block}/exclude")
    assert len(result["beads"]) == 3
    assert [e["block_id"] for e in result["excluded"]] == [block]
    result = _ok(client, book_id, f"blocks/{block}/include")
    assert _rows(result)[1] == (["Il pleuvait."], [])
    assert result["excluded"] == []


def test_exclude_and_include_range(client, gap):
    book_id, data = gap
    b, c = data["beads"][1]["id"], data["beads"][2]["id"]
    result = _ok(client, book_id, "blocks/exclude-range", {"bead_id": b, "side": "source", "to": "start"})
    assert _rows(result) == [
        ([], ["Marie arrivò."]),
        (["Paul partit."], ["Paul partì."]),
        (["Il ne dit rien."], ["Non disse niente."]),
    ]
    assert len(result["excluded"]) == 2
    result = _ok(client, book_id, "undo")
    assert _rows(result) == _rows(data)
    _ok(client, book_id, "redo")
    result = _ok(client, book_id, "blocks/include-range", {"bead_id": c, "side": "source", "to": "start"})
    assert _rows(result) == [
        (["Marie arriva."], []),
        (["Il pleuvait."], []),
        ([], ["Marie arrivò."]),
        (["Paul partit."], ["Paul partì."]),
        (["Il ne dit rien."], ["Non disse niente."]),
    ]
    assert result["excluded"] == []


def test_realign(client, gap):
    book_id, data = gap
    b, d = data["beads"][1]["id"], data["beads"][3]["id"]
    result = _ok(client, book_id, "beads/realign", {"first_bead_id": b, "last_bead_id": d})
    assert result["beads"][0] == data["beads"][0]
    assert all(not bead["reviewed"] and bead["method"] == "length" for bead in result["beads"][1:])
    assert _ok(client, book_id, "undo")["beads"] == data["beads"]


def test_range_refusals(client, gap):
    book_id, data = gap
    b = data["beads"][1]["id"]
    resp = _post(client, book_id, "blocks/exclude-range", {"bead_id": b, "side": "target", "to": "end"})
    assert (resp.status_code, resp.json()["detail"]) == (409, "The bead has no target segment")
    resp = _post(client, book_id, "blocks/include-range", {"bead_id": b, "side": "source", "to": "end"})
    assert (resp.status_code, resp.json()["detail"]) == (409, "Nothing to include")
    resp = _post(client, book_id, "blocks/exclude-range", {"bead_id": b, "side": "source", "to": "middle"})
    assert resp.status_code == 422
    assert client.get(f"/api/v2/books/{book_id}").json() == data


def _originals(book):
    return [s["original"] for b in book["beads"] for side in ("source", "target") for s in b[side]]


def test_original_and_restore(client, book):
    book_id, data = book
    assert set(_originals(data)) == {None}
    seg = _segment(data, "Il pleuvait.")["segment_id"]
    result = _ok(client, book_id, f"segments/{seg}/edit", {"text": "Il neigeait."})
    assert _segment(result, "Il neigeait.")["original"] == "Il pleuvait."
    assert _originals(result).count(None) == len(_originals(result)) - 1
    result = _ok(client, book_id, f"segments/{seg}/restore")
    assert _segment(result, "Il pleuvait.")["original"] is None
    assert set(_originals(result)) == {None}
    resp = _post(client, book_id, f"segments/{seg}/restore")
    assert (resp.status_code, resp.json()["detail"]) == (409, "The sentence is not edited")


def test_undo_redo_round_trip(client, book):
    book_id, data = book
    seg = _segment(data, "Il pleuvait.")["segment_id"]
    _ok(client, book_id, f"segments/{seg}/edit", {"text": "Il neigeait."})
    result = _ok(client, book_id, "undo")
    assert _rows(result) == _rows(data)
    assert (result["can_undo"], result["can_redo"]) == (False, True)
    result = _ok(client, book_id, "redo")
    assert _rows(result)[1] == (["Il neigeait."], ["Paul partì."])
    assert (result["can_undo"], result["can_redo"]) == (True, False)


def test_refused_corrections_are_409_and_change_nothing(client, book):
    book_id, data = book
    last = data["beads"][-1]["id"]
    seg = _segment(data, "Il pleuvait.")["segment_id"]
    for path, body in ((f"beads/{last}/merge-next", None), (f"segments/{seg}/edit", {"text": "  "})):
        resp = _post(client, book_id, path, body)
        assert resp.status_code == 409
        assert resp.json()["detail"]
    after = client.get(f"/api/v2/books/{book_id}").json()
    assert after == data


def test_no_op_edit_is_200(client, book):
    book_id, data = book
    seg = _segment(data, "Il pleuvait.")["segment_id"]
    result = _ok(client, book_id, f"segments/{seg}/edit", {"text": "Il pleuvait."})
    assert _rows(result) == _rows(data)
    assert result["can_undo"] is False


def test_bead_of_another_book_is_409(client, book):
    book_id, _ = book
    other_id = _import(client, title="Other")
    other_bead = client.get(f"/api/v2/books/{other_id}").json()["beads"][0]["id"]
    assert _post(client, book_id, f"beads/{other_bead}/merge-next").status_code == 409


def test_unknown_book_is_404(client):
    assert _post(client, "nope", "undo").status_code == 404
    assert _post(client, "nope", "beads/1/merge-next").status_code == 404


def test_correction_moves_book_to_top_of_list(client, book):
    book_id, data = book
    other_id = _import(client, title="Other")
    assert [b["id"] for b in client.get("/api/v2/books").json()] == [other_id, book_id]
    _ok(client, book_id, "reviewed", {"bead_ids": [data["beads"][0]["id"]], "reviewed": True})
    assert [b["id"] for b in client.get("/api/v2/books").json()] == [book_id, other_id]
