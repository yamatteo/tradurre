"""The checklist fixtures (`scripts/make_fixtures.py`): the .docx + .pdf pair imports like the .txt pair."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tradurre.app import app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr("tradurre.config.DB_PATH", path)
    monkeypatch.setattr("tradurre.app.DB_PATH", path)
    with TestClient(app) as c:
        yield c


def _import(client, source, target, title):
    files = {name: (filename, (FIXTURES / filename).read_bytes())
             for name, filename in (("source", source), ("target", target))}
    resp = client.post("/api/v2/books", files=files, data={"title": title})
    assert resp.status_code == 201
    assert resp.json()["warnings"] == []
    return resp.json()


def _excluded(client, book_id):
    excluded = client.get(f"/api/v2/books/{book_id}").json()["excluded"]
    return {side: sum(1 for b in excluded if b["side"] == side) for side in ("source", "target")}


def test_docx_and_pdf_import_like_txt(client):
    txt = _import(client, "easy.source.txt", "easy.target.txt", "Easy txt")
    other = _import(client, "easy.source.docx", "easy.target.pdf", "Easy docx pdf")

    assert abs(other["bead_count"] - txt["bead_count"]) <= 0.15 * txt["bead_count"]
    assert client.get(f"/api/v2/books/{other['id']}/check").json() == []
    assert _excluded(client, txt["id"]) == {"source": 0, "target": 0}
    # The PDF's running head and page number on each of its 3 pages, nothing else.
    assert _excluded(client, other["id"]) == {"source": 0, "target": 6}

    # A word of the last paragraph: the PDF's text reaches the end of the book and is searchable.
    last_word = (FIXTURES / "easy.target.txt").read_text(encoding="utf-8").split()[-1].strip(".")
    hits = client.get("/api/v2/search", params={"q": last_word}).json()
    assert {h["book_id"] for h in hits} == {txt["id"], other["id"]}
