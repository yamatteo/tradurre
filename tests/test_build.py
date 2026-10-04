"""Tests for building a project in the new model from two extractions (tradurre.services.build)."""

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain.history import transaction
from tradurre.domain.invariants import check_project
from tradurre.services.build import build_book
from tradurre.services.extract import ExtractedBlock, Extraction


@pytest.fixture()
def conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with transaction(conn):
        conn.execute(
            "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
            "VALUES ('p1', 'Book', 'fr', 'it', 'now', 'now')"
        )
    yield conn
    conn.close()


def _build(conn, source_blocks, target_blocks):
    with transaction(conn):
        build_book(conn, "p1", ("fr.txt", "txt", Extraction(source_blocks)),
                   ("it.docx", "docx", Extraction(target_blocks)))


def _beads(conn):
    """Each bead as (source texts, target texts, confidence, method), in order."""
    beads = []
    for bead_id, confidence, method in conn.execute(
        "SELECT id, confidence, method FROM beads WHERE project_id = 'p1' ORDER BY ord"
    ):
        sides = {"source": [], "target": []}
        for side, text in conn.execute(
            "SELECT d.side, s.text FROM segments s JOIN blocks b ON b.id = s.block_id "
            "JOIN documents d ON d.id = b.document_id WHERE s.bead_id = ? ORDER BY b.ord, s.ord",
            (bead_id,),
        ):
            sides[side].append(text)
        beads.append((sides["source"], sides["target"], confidence, method))
    return beads


def test_build_aligns_included_segments(conn):
    _build(
        conn,
        [
            ExtractedBlock("heading", "Chapitre premier"),
            ExtractedBlock("paragraph", "Marie arriva. Elle vit Paul."),
            ExtractedBlock("footnote", "Note de l'auteur.", page=3),
        ],
        [
            ExtractedBlock("heading", "Capitolo primo"),
            ExtractedBlock("paragraph", "Marie arrivò. Vide Paul."),
        ],
    )
    assert check_project(conn, "p1") == []
    beads = _beads(conn)
    assert [(source, target, method) for source, target, _, method in beads] == [
        (["Chapitre premier"], ["Capitolo primo"], "length"),
        (["Marie arriva."], ["Marie arrivò."], "length"),
        (["Elle vit Paul."], ["Vide Paul."], "length"),
    ]
    assert all(0.8 < confidence <= 1 for _, _, confidence, _ in beads)
    excluded = conn.execute(
        "SELECT b.kind, b.excluded, b.page, s.text, s.bead_id FROM segments s JOIN blocks b ON b.id = s.block_id "
        "WHERE b.excluded = 1"
    ).fetchall()
    assert [tuple(r) for r in excluded] == [("footnote", 1, 3, "Note de l'auteur.", None)]
    documents = conn.execute("SELECT side, filename, format FROM documents ORDER BY side").fetchall()
    assert [tuple(r) for r in documents] == [("source", "fr.txt", "txt"), ("target", "it.docx", "docx")]


def test_extra_source_sentence_joins_a_neighbours_bead(conn):
    # On so little text a 2:1 bead is likelier than a 1:0 one; its low confidence is what flags it for review.
    _build(
        conn,
        [ExtractedBlock("paragraph", "Marie arriva. Il pleuvait. Paul partit.")],
        [ExtractedBlock("paragraph", "Marie arrivò. Paul partì.")],
    )
    assert check_project(conn, "p1") == []
    beads = _beads(conn)
    assert [(source, target, method) for source, target, _, method in beads] == [
        (["Marie arriva.", "Il pleuvait."], ["Marie arrivò."], "length"),
        (["Paul partit."], ["Paul partì."], "length"),
    ]
    assert beads[0][2] < 0.5 < 0.8 < beads[1][2]


def test_block_without_sentence_boundary_is_one_segment(conn):
    _build(conn, [ExtractedBlock("paragraph", "sans point final")], [ExtractedBlock("paragraph", "senza punto")])
    assert check_project(conn, "p1") == []
    assert _beads(conn) == [(["sans point final"], ["senza punto"], 1.0, "length")]
