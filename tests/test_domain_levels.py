"""Tests for the turn and paragraph ends (tradurre.domain.levels)."""

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain.history import transaction
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.levels import compute_unit_ends, is_speech, unit_ends


@pytest.fixture()
def conn(tmp_path):
    c = get_connection(tmp_path / "test.db")
    init_db(c)
    with transaction(c):
        c.execute(
            "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
            "VALUES ('p1', 'Book', 'fr', 'it', 'now', 'now')"
        )
    yield c
    c.close()


def _book(conn, blocks, beads):
    """`blocks` are (kind, [texts], excluded); `beads` are (source indexes, target indexes: only their number counts) over the included source
    segments in order; the target holds one segment per target index. Returns the bead ids."""
    with transaction(conn):
        segments = create_document(conn, "p1", "source", "a.txt", "txt",
                                   [NewBlock(k, t, excluded=e) for k, t, e in blocks])
        included = [s for (_, _, excluded), ids in zip(blocks, segments) if not excluded for s in ids]
        n_target = sum(len(t) for _, t in beads)
        (targets,) = create_document(conn, "p1", "target", "b.txt", "txt",
                                     [NewBlock("paragraph", ["x"] * n_target)])
        out, k = [], 0
        for source, count in beads:
            out.append(NewBead([included[j] for j in source], targets[k:k + len(count)], 0.9, "length"))
            k += len(count)
        return append_beads(conn, "p1", out)


def _ends(conn, ids):
    found = unit_ends(conn, "p1")
    return [found[b] for b in ids]


def test_is_speech():
    assert is_speech("  — Zut.") and is_speech("« Zut") and not is_speech("Zut.") and not is_speech("")


def test_narrative_paragraph(conn):
    ids = _book(conn, [("paragraph", ["Un.", "Deux.", "Trois."], False), ("paragraph", ["Quatre."], False)],
                [([0], [0]), ([1], [0]), ([2], [0]), ([3], [0])])
    # every sentence is a turn; only the last of the paragraph ends it
    assert _ends(conn, ids) == [(True, False), (True, False), (True, True), (True, True)]


def test_speech_paragraph(conn):
    ids = _book(conn, [("paragraph", ["— Un.", "Deux.", "Trois."], False), ("paragraph", ["Quatre."], False)],
                [([0], [0]), ([1], [0]), ([2], [0]), ([3], [0])])
    assert _ends(conn, ids) == [(False, False), (False, False), (True, True), (True, True)]


def test_bead_crossing_a_paragraph_break(conn):
    ids = _book(conn, [("paragraph", ["Un.", "Deux."], False), ("paragraph", ["Trois.", "Quatre."], False)],
                [([0], [0]), ([1, 2], [0]), ([3], [0])])
    # the 2:1 bead ends in the second paragraph, after its first sentence: not a paragraph end
    assert _ends(conn, ids) == [(True, False), (True, False), (True, True)]


def test_source_empty_bead(conn):
    # inside a paragraph it joins the unit; at a paragraph break it is a unit of its own
    ids = _book(conn, [("paragraph", ["— Un.", "Deux."], False), ("paragraph", ["Trois."], False)],
                [([0], [0]), ([], [0]), ([1], [0]), ([], [0]), ([2], [0])])
    assert _ends(conn, ids) == [(False, False), (False, False), (True, True), (True, True), (True, True)]


def test_source_empty_beads_at_the_start(conn):
    # the start of the book is a paragraph break: each leading source-empty bead is its own unit
    ids = _book(conn, [("paragraph", ["— Un.", "Deux."], False)],
                [([], [0]), ([], [0]), ([0], [0]), ([1], [0])])
    assert _ends(conn, ids) == [(True, True), (True, True), (False, False), (True, True)]


def test_source_empty_beads_at_the_end(conn):
    # the last source-bearing bead ends the unit; each trailing source-empty bead is its own unit
    ids = _book(conn, [("paragraph", ["— Un.", "Deux."], False)],
                [([0], [0]), ([1], [0]), ([], [0]), ([], [0])])
    assert _ends(conn, ids) == [(False, False), (True, True), (True, True), (True, True)]


def test_source_empty_bead_first_and_last(conn):
    ids = _book(conn, [("paragraph", ["Un."], False)], [([], [0]), ([0], [0]), ([], [0])])
    assert _ends(conn, ids) == [(True, True), (True, True), (True, True)]


def test_excluded_block_is_ignored(conn):
    ids = _book(conn, [("paragraph", ["— Un."], False), ("footnote", ["Note."], True),
                       ("paragraph", ["— Deux."], False)],
                [([0], [0]), ([1], [0])])
    assert _ends(conn, ids) == [(True, True), (True, True)]


def test_heading_block_is_a_paragraph(conn):
    ids = _book(conn, [("heading", ["Titre."], False), ("paragraph", ["Un.", "Deux."], False)],
                [([0], [0]), ([1], [0]), ([2], [0])])
    assert _ends(conn, ids) == [(True, True), (True, False), (True, True)]


def test_pure_function_needs_no_database():
    ends = compute_unit_ends([1, 2, 3], [(1, 10, "— a"), (2, 10, "b"), (3, 11, "c")])
    assert ends == {1: (False, False), 2: (True, True), 3: (True, True)}
