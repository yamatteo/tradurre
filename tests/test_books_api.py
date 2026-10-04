"""Tests for the books API (/api/v2): import into the new model and read back."""

import sys
from io import BytesIO

import pytest
from docx import Document
from fastapi.testclient import TestClient

from tradurre.app import app
from tradurre.db import get_connection
from tradurre.domain.blocks import exclude_block
from tradurre.domain.history import transaction
from tradurre.services.extract import PDF_RUNTIME_MISSING

SOURCE = "Marie arriva.\n\nIl pleuvait.\n\nPaul partit. Il ne dit rien."
TARGET = "Marie arrivò.\n\nPaul partì. Non disse niente."


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


def _import(client, source=("contrefeu.txt", SOURCE.encode()), target=("sacro.txt", TARGET.encode()), **form):
    return client.post("/api/v2/books", files={"source": source, "target": target}, data=form)


def _texts(bead, side):
    return [s["text"] for s in bead[side]]


def _docx(*paragraphs):
    doc = Document()
    for kind, text in paragraphs:
        if kind == "heading":
            doc.add_heading(text, level=1)
        else:
            doc.add_paragraph(text)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_import_txt_and_read_back(client):
    resp = _import(client, title="Contrefeu", source_lang="fr", target_lang="it")
    assert resp.status_code == 201
    body = resp.json()
    assert (body["title"], body["bead_count"], body["warnings"]) == ("Contrefeu", 3, [])

    book = client.get(f"/api/v2/books/{body['id']}").json()
    assert (book["title"], book["source_lang"], book["target_lang"]) == ("Contrefeu", "fr", "it")
    assert [(_texts(b, "source"), _texts(b, "target")) for b in book["beads"]] == [
        # Too little text for the length aligner to leave "Il pleuvait." unpaired (see test_build.py).
        (["Marie arriva."], ["Marie arrivò."]),
        (["Il pleuvait."], ["Paul partì."]),
        (["Paul partit.", "Il ne dit rien."], ["Non disse niente."]),
    ]
    first = book["beads"][0]
    assert (first["method"], first["reviewed"]) == ("length", False)
    assert 0.8 < first["confidence"] <= 1
    assert first["source"][0]["block_kind"] == "paragraph"
    assert book["excluded"] == []


def test_import_records_a_run(client):
    book_id = _import(client).json()["id"]
    runs = client.get(f"/api/v2/books/{book_id}/runs").json()
    assert [(r["kind"], r["warnings"]) for r in runs] == [("import", [])]
    stats = runs[0]["stats"]
    assert {k: stats[k] for k in ("beads", "one_sided_beads", "low_confidence_beads", "bead_shapes")} == {
        "beads": 3, "one_sided_beads": 0, "low_confidence_beads": 1, "bead_shapes": {"1:1": 2, "2:1": 1},
    }
    source = stats["source"]
    assert (source["filename"], source["format"], source["bytes"]) == ("contrefeu.txt", "txt", len(SOURCE.encode()))
    assert (source["blocks"], source["excluded_blocks"], source["segments"], source["pages"]) == (
        {"paragraph": 3}, 0, 4, None)
    assert stats["target"]["segments"] == 3
    assert source["extract_ms"] >= 0 and stats["build_ms"] >= 0
    assert runs[0]["app_version"]


def test_runs_of_unknown_book_is_404(client):
    assert client.get("/api/v2/books/nope/runs").status_code == 404


def test_import_docx_with_heading(client):
    resp = _import(
        client,
        source=("livre.docx", _docx(("heading", "Chapitre premier"), ("paragraph", "Marie arriva."))),
        target=("libro.docx", _docx(("heading", "Capitolo primo"), ("paragraph", "Marie arrivò."))),
    )
    assert resp.status_code == 201
    book = client.get(f"/api/v2/books/{resp.json()['id']}").json()
    assert [(b["source"][0]["block_kind"], b["target"][0]["block_kind"]) for b in book["beads"]] == [
        ("heading", "heading"),
        ("paragraph", "paragraph"),
    ]


def test_title_defaults_to_source_stem(client):
    assert _import(client).json()["title"] == "contrefeu"


def test_latin1_warning_is_prefixed(client):
    resp = _import(client, target=("sacro.txt", "Marie arrivò.".encode("latin-1")))
    assert resp.json()["warnings"] == ["target: The text file is not valid UTF-8; it was read as Latin-1."]
    runs = client.get(f"/api/v2/books/{resp.json()['id']}/runs").json()
    assert runs[0]["warnings"] == [
        {"side": "target", "message": "The text file is not valid UTF-8; it was read as Latin-1."}
    ]


def _project_without_documents(db_path):
    """A projects row with no documents (a v0.1 project before migration 6): not a book."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
                "VALUES ('old', 'Old', 'fr', 'it', 'now', 'now')"
            )
    finally:
        conn.close()
    return "old"


def test_list_only_books_with_counts(client, db_path):
    _project_without_documents(db_path)
    book_id = _import(client).json()["id"]
    assert client.get("/api/v2/books").json() == [{
        "id": book_id, "title": "contrefeu", "source_lang": "fr", "target_lang": "it",
        "bead_count": 3, "reviewed_count": 0,
    }]


def test_excluded_block_sits_after_previous_bead(client, db_path):
    book_id = _import(client).json()["id"]
    book = client.get(f"/api/v2/books/{book_id}").json()
    first_bead = book["beads"][0]["id"]
    block_id = book["beads"][1]["source"][0]["block_id"]  # "Il pleuvait."
    conn = get_connection(db_path)
    try:
        with transaction(conn):
            exclude_block(conn, book_id, block_id)
    finally:
        conn.close()

    book = client.get(f"/api/v2/books/{book_id}").json()
    assert len(book["beads"]) == 3
    assert book["excluded"] == [{
        "block_id": block_id, "side": "source", "kind": "paragraph", "page": None,
        "segments": [{"segment_id": book["excluded"][0]["segments"][0]["segment_id"], "text": "Il pleuvait."}],
        "after_bead_id": first_bead,
    }]


def _pdf(pages) -> bytes:
    """PDF bytes, one portrait page per list of `(x, baseline_y, text, fontsize)`, in an embedded font (as in
    `tests/test_extract_pdf.py`)."""
    pymupdf = pytest.importorskip("pymupdf")
    font = pymupdf.Font("helv")
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=439, height=651)
        page.insert_font(fontname="F0", fontbuffer=font.buffer)
        for x, y, text, size in lines:
            page.insert_text((x, y), text, fontsize=size, fontname="F0")
    return doc.tobytes()


def _pdf_book(paragraphs):
    """One indented paragraph per page, and the page number at the bottom."""
    return _pdf([[(74, 120, text, 11.9), (210, 576, str(k + 1), 10)] for k, text in enumerate(paragraphs)])


def test_import_pdf_excludes_page_numbers(client):
    resp = _import(
        client,
        source=("livre.pdf", _pdf_book(["Marie arriva.", "Il pleuvait.", "Paul partit."])),
        target=("libro.pdf", _pdf_book(["Marie arrivò.", "Pioveva.", "Paul partì."])),
    )
    assert resp.status_code == 201
    book = client.get(f"/api/v2/books/{resp.json()['id']}").json()
    assert [(_texts(b, "source"), _texts(b, "target")) for b in book["beads"]] == [
        (["Marie arriva."], ["Marie arrivò."]),
        (["Il pleuvait."], ["Pioveva."]),
        (["Paul partit."], ["Paul partì."]),
    ]
    assert book["beads"][0]["source"][0]["block_kind"] == "paragraph"
    assert sorted((b["side"], b["kind"], b["page"], b["segments"][0]["text"]) for b in book["excluded"]) == sorted(
        (side, "page_number", k, str(k)) for side in ("source", "target") for k in (1, 2, 3)
    )
    stats = client.get(f"/api/v2/books/{resp.json()['id']}/runs").json()[0]["stats"]
    for side in ("source", "target"):
        assert (stats[side]["pages"], stats[side]["blocks"]["page_number"]) == (3, 3)


def test_unreadable_pdf_is_refused_and_writes_nothing(client):
    resp = _import(client, source=("livre.pdf", b"%PDF-1.4"))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "The file is not a readable PDF"
    assert client.get("/api/v2/books").json() == []


def test_pdf_runtime_missing_is_explained_and_writes_nothing(client, monkeypatch):
    # As on a Windows without the Visual C++ Redistributable: pymupdf's DLL doesn't load.
    monkeypatch.setitem(sys.modules, "pymupdf", None)
    resp = _import(client, target=("libro.pdf", b"%PDF-1.4"))
    assert resp.status_code == 400
    assert resp.json()["detail"] == PDF_RUNTIME_MISSING
    assert client.get("/api/v2/books").json() == []
    assert _import(client).status_code == 201  # text files still import


def test_empty_txt_is_refused_and_writes_nothing(client, db_path):
    resp = _import(client, target=("vide.txt", b"  \n\n"))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "no text found in vide.txt"
    assert client.get("/api/v2/books").json() == []
    conn = get_connection(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    finally:
        conn.close()


def test_unknown_extension_is_refused(client):
    assert _import(client, source=("livre.epub", b"x")).status_code == 400


def test_unknown_book_is_404(client):
    assert client.get("/api/v2/books/nope").status_code == 404
    assert client.get("/api/v2/books/nope/check").status_code == 404


def test_old_project_is_not_a_book(client, db_path):
    project_id = _project_without_documents(db_path)
    assert client.get(f"/api/v2/books/{project_id}").status_code == 404


def test_check_is_clean(client):
    book_id = _import(client).json()["id"]
    assert client.get(f"/api/v2/books/{book_id}/check").json() == []


def test_delete_book(client, db_path):
    book_id = _import(client).json()["id"]
    bead = client.get(f"/api/v2/books/{book_id}").json()["beads"][0]["id"]
    # A correction, so the book has an operation to lose.
    assert client.post(f"/api/v2/books/{book_id}/reviewed", json={"bead_ids": [bead], "reviewed": True}).status_code == 200
    conn = get_connection(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM operations WHERE project_id = ?", (book_id,)).fetchone()[0] > 0
    finally:
        conn.close()
    assert client.get("/api/v2/search", params={"q": "pleuvait"}).json() != []
    assert client.delete(f"/api/v2/books/{book_id}").status_code == 204
    assert client.get(f"/api/v2/books/{book_id}").status_code == 404
    assert client.get("/api/v2/books").json() == []
    assert client.get("/api/v2/search", params={"q": "pleuvait"}).json() == []
    conn = get_connection(db_path)
    try:
        for table in ("documents", "beads", "operations", "runs"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id = ?", (book_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM bead_index").fetchone()[0] == 0
    finally:
        conn.close()
    assert client.delete(f"/api/v2/books/{book_id}").status_code == 404
