"""Tests for the edition export (tradurre.services.edition)."""

import io

import pytest
from docx import Document

from tradurre.db import get_connection, init_db
from tradurre.domain.blocks import include_block
from tradurre.domain.history import transaction
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.segments import edit_text
from tradurre.services.edition import edition_blocks, edition_docx, edition_txt


@pytest.fixture()
def db(tmp_path):
    """Source: heading H [h], running head R [r] excluded, paragraph P1 [s1, s2], footnote F [f] excluded,
    paragraph P2 [s3]; target T [t0..t3]; beads 1:1; s2 edited."""
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with transaction(conn):
        conn.execute(
            "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
            "VALUES ('p1', 'Book', 'fr', 'it', 'now', 'now')"
        )
        (h,), (r,), (s1, s2), (f,), (s3,) = create_document(conn, "p1", "source", "fr.txt", "txt", [
            NewBlock("heading", ["Chapitre un"]),
            NewBlock("running_head", ["Contrefeu"], excluded=True),
            NewBlock("paragraph", ["Il partit.", "Il marcha."]),
            NewBlock("footnote", ["Une note."], excluded=True),
            NewBlock("paragraph", ["Fin."]),
        ])
        (t0, t1, t2, t3), = create_document(conn, "p1", "target", "it.txt", "txt", [
            NewBlock("paragraph", ["Capitolo uno", "Partì.", "Camminò.", "Fine."]),
        ])
        append_beads(conn, "p1", [NewBead([s], [t], 0.9, "length") for s, t in [(h, t0), (s1, t1), (s2, t2), (s3, t3)]])
    with transaction(conn):
        edit_text(conn, "p1", s2, "Il marchait.")
    footnote = conn.execute("SELECT block_id FROM segments WHERE id = ?", (f,)).fetchone()[0]
    assert check_project(conn, "p1") == []
    yield conn, footnote
    conn.close()


def test_txt_is_the_edition_as_reviewed(db):
    conn, _ = db
    blocks = edition_blocks(conn, "p1", "source")
    assert blocks == [("heading", "Chapitre un"), ("paragraph", "Il partit. Il marchait."), ("paragraph", "Fin.")]
    assert edition_txt(blocks) == "﻿Chapitre un\n\nIl partit. Il marchait.\n\nFin.\n".encode("utf-8")


def test_target_side(db):
    conn, _ = db
    assert edition_txt(edition_blocks(conn, "p1", "target")) == "﻿Capitolo uno Partì. Camminò. Fine.\n".encode()


def test_an_included_footnote_is_exported_in_its_place(db):
    conn, footnote = db
    with transaction(conn):
        include_block(conn, "p1", footnote)
    assert [text for _, text in edition_blocks(conn, "p1", "source")] == [
        "Chapitre un", "Il partit. Il marchait.", "Une note.", "Fin.",
    ]


def test_docx_keeps_headings_and_paragraphs(db):
    conn, _ = db
    doc = Document(io.BytesIO(edition_docx(edition_blocks(conn, "p1", "source"))))
    assert [(p.style.name, p.text) for p in doc.paragraphs] == [
        ("Heading 1", "Chapitre un"),
        ("Normal", "Il partit. Il marchait."),
        ("Normal", "Fin."),
    ]
