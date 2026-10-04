"""Tests for the books search API (/api/v2/search)."""

import pytest
from fastapi.testclient import TestClient

from tradurre.app import app

SOURCE_1 = "Le désœuvrement de l’homme.\n\nIl partit sans un mot."
TARGET_1 = "L'ozio dell'uomo.\n\nPartì senza una parola."
SOURCE_2 = "Un désœuvré passait."
TARGET_2 = "Un ozioso passava."


@pytest.fixture()
def client(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr("tradurre.config.DB_PATH", path)
    monkeypatch.setattr("tradurre.app.DB_PATH", path)
    with TestClient(app) as c:
        yield c


def _import(client, title, source, target):
    resp = client.post("/api/v2/books", files={"source": ("fr.txt", source.encode()), "target": ("it.txt", target.encode())},
                       data={"title": title})
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture()
def books(client):
    return _import(client, "Contre", SOURCE_1, TARGET_1), _import(client, "Saisons", SOURCE_2, TARGET_2)


def _joined(spans):
    return "".join(f"[{s['text']}]" if s["match"] else s["text"] for s in spans)


def test_word_beginning_across_books(client, books):
    one, two = books
    hits = client.get("/api/v2/search", params={"q": "désœuvr"}).json()
    assert {h["book_id"] for h in hits} == {one, two}
    by_book = {h["book_id"]: h for h in hits}
    assert _joined(by_book[one]["source"]) == "Le [désœuvrement] de l’homme."
    assert _joined(by_book[two]["source"]) == "Un [désœuvré] passait."
    assert (by_book[two]["title"], by_book[two]["position"], by_book[two]["reviewed"]) == ("Saisons", 1, False)
    assert _joined(by_book[two]["target"]) == "Un ozioso passava."


def test_book_scope_and_side(client, books):
    one, two = books
    assert [h["book_id"] for h in client.get("/api/v2/search", params={"q": "désœuvr", "book": two}).json()] == [two]
    assert client.get("/api/v2/search", params={"q": "désœuvr", "side": "target"}).json() == []
    hits = client.get("/api/v2/search", params={"q": "ozio", "side": "target"}).json()
    assert {h["book_id"] for h in hits} == {one, two}


def test_unknown_book_and_empty_query(client, books):
    assert client.get("/api/v2/search", params={"q": "mot", "book": "nope"}).status_code == 404
    assert client.get("/api/v2/search", params={"q": ""}).json() == []
    assert client.get("/api/v2/search", params={"q": "mot", "side": "both"}).status_code == 422


def _beads(client, book):
    return [b["id"] for b in client.get(f"/api/v2/books/{book}").json()["beads"]]


def test_context(client, books):
    one, two = books
    a, b = _beads(client, one)
    ctx = client.get(f"/api/v2/books/{one}/beads/{b}/context", params={"around": 1}).json()
    assert [(c["bead_id"], c["position"]) for c in ctx] == [(a, 1), (b, 2)]
    assert ctx[0]["source"] == "Le désœuvrement de l’homme."
    assert ctx[1]["target"] == "Partì senza una parola."
    assert ctx[1]["reviewed"] is False


def test_context_window(client):
    text = "\n\n".join(f"Phrase {k}." for k in range(5))
    book = _import(client, "Five", text, text.replace("Phrase", "Frase"))
    ids = _beads(client, book)
    assert len(ids) == 5
    second = client.get(f"/api/v2/books/{book}/beads/{ids[1]}/context", params={"around": 1}).json()
    assert [c["bead_id"] for c in second] == ids[0:3]
    first = client.get(f"/api/v2/books/{book}/beads/{ids[0]}/context", params={"around": 1}).json()
    assert [c["bead_id"] for c in first] == ids[0:2]
    default = client.get(f"/api/v2/books/{book}/beads/{ids[2]}/context").json()
    assert [(c["bead_id"], c["position"]) for c in default] == [(i, k + 1) for k, i in enumerate(ids)]


def test_context_errors(client, books):
    one, two = books
    (c,) = _beads(client, two)
    assert client.get(f"/api/v2/books/{one}/beads/{c}/context").status_code == 404
    assert client.get(f"/api/v2/books/nope/beads/{c}/context").status_code == 404
    assert client.get(f"/api/v2/books/{two}/beads/{c}/context", params={"around": 11}).status_code == 422


def test_counts_per_book(client, books):
    one, two = books
    counts = client.get("/api/v2/search/books", params={"q": "désœuvr"}).json()
    # Library order: "Saisons" was imported last, so it was worked on most recently.
    assert counts == [{"book_id": two, "title": "Saisons", "count": 1}, {"book_id": one, "title": "Contre", "count": 1}]
    assert [h["book_id"] for h in client.get("/api/v2/search", params={"q": "désœuvr"}).json()] == [two, one]
    assert client.get("/api/v2/search/books", params={"q": "u", "book": one}).json() == [
        {"book_id": one, "title": "Contre", "count": 2},
    ]
    assert client.get("/api/v2/search/books", params={"q": "ozio", "side": "source"}).json() == []
    assert client.get("/api/v2/search/books", params={"q": ""}).json() == []
    assert client.get("/api/v2/search/books", params={"q": "mot", "book": "nope"}).status_code == 404
