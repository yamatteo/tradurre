"""Tests for the edition export API (/api/v2/books/{id}/export/edition)."""

import io
from urllib.parse import quote

import pytest
from docx import Document
from fastapi.testclient import TestClient

from tradurre.app import app

SOURCE = "Il partit.\n\nIl revint."
TARGET = "Partì.\n\nTornò."


@pytest.fixture()
def client(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr("tradurre.config.DB_PATH", path)
    monkeypatch.setattr("tradurre.app.DB_PATH", path)
    with TestClient(app) as c:
        yield c


def _import(client, title):
    resp = client.post("/api/v2/books", files={"source": ("fr.txt", SOURCE.encode()), "target": ("it.txt", TARGET.encode())},
                       data={"title": title, "source_lang": "fr", "target_lang": "it"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _export(client, book_id, side, fmt):
    return client.get(f"/api/v2/books/{book_id}/export/edition", params={"side": side, "format": fmt})


def test_txt(client):
    book = _import(client, "Contre")
    resp = _export(client, book, "target", "txt")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/plain; charset=utf-8"
    assert resp.headers["content-disposition"] == 'attachment; filename="Contre (IT).txt"'
    assert resp.content == "﻿Partì.\n\nTornò.\n".encode()


def test_docx(client):
    book = _import(client, "Contre")
    resp = _export(client, book, "source", "docx")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert resp.headers["content-disposition"] == 'attachment; filename="Contre (FR).docx"'
    assert [p.text for p in Document(io.BytesIO(resp.content)).paragraphs] == ["Il partit.", "Il revint."]


def test_unsafe_and_non_ascii_title(client):
    book = _import(client, 'Désœuvré: un/deux "trois"?')
    resp = _export(client, book, "target", "txt")
    name = 'Désœuvré_ un_deux _trois__ (IT).txt'
    assert resp.headers["content-disposition"] == (
        'attachment; filename="D_s_uvr__ un_deux _trois__ (IT).txt"; '
        f"filename*=UTF-8''{quote(name)}"
    )


def test_errors(client):
    book = _import(client, "Contre")
    assert _export(client, "nope", "target", "txt").status_code == 404
    assert _export(client, book, "both", "txt").status_code == 422
    assert _export(client, book, "target", "pdf").status_code == 422


def test_bundle_export(client):
    book = _import(client, "Contre")
    resp = client.get(f"/api/v2/books/{book}/export/bundle")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert resp.headers["content-disposition"] == 'attachment; filename="Contre.tradurre.zip"'
    assert client.get("/api/v2/books/nope/export/bundle").status_code == 404


def test_bundle_restore(client):
    book = _import(client, "Contre")
    data = client.get(f"/api/v2/books/{book}/export/bundle").content
    resp = client.post("/api/v2/books/bundle", files={"bundle": ("Contre.tradurre.zip", data)})
    assert resp.status_code == 201
    restored = resp.json()
    assert restored["id"] != book
    assert restored["title"].startswith("Contre (restored ")
    assert restored["warnings"] == []
    listed = client.get("/api/v2/books").json()
    assert listed[0]["id"] == restored["id"]
    books = {b["id"]: b for b in listed}
    assert restored["bead_count"] == books[book]["bead_count"] == books[restored["id"]]["bead_count"]


def test_bundle_restore_refused(client):
    resp = client.post("/api/v2/books/bundle", files={"bundle": ("x.zip", b"garbage")})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Not a Tradurre bundle"
