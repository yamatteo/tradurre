"""Tests for the segment text corrections (tradurre.domain.segments)."""

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain import DomainError
from tradurre.domain.history import redo, transaction, undo
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.segments import _map_offset, edit_text, join_with_next, split_segment


def snapshot(conn):
    return {
        table: sorted(tuple(r) for r in conn.execute(f"SELECT * FROM {table}"))
        for table in ("documents", "blocks", "segments", "beads")
    }


def _add_project(conn, project_id):
    conn.execute(
        "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
        "VALUES (?, 'Book', 'fr', 'it', 'now', 'now')",
        (project_id,),
    )


@pytest.fixture()
def db(tmp_path):
    """Source S1 [s1, s2, s3], S2 [f1] excluded, S3 [s4]; target T1 [t1..t4];
    beads A (s1 | t1), X ( | t2), B (s2, s3 | t3), C (s4 | t4); A and B reviewed. Project p2 has one segment."""
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with transaction(conn):
        _add_project(conn, "p1")
        _add_project(conn, "p2")
        (s1, s2, s3), (f1,), (s4,) = create_document(conn, "p1", "source", "fr.txt", "txt", [
            NewBlock("paragraph", ["Il partit.", "Il marcha.", "Puis il revint."]),
            NewBlock("footnote", ["Une note."], excluded=True),
            NewBlock("paragraph", ["Il mar- cha. Fin."]),
        ])
        (t1, t2, t3, t4), = create_document(conn, "p1", "target", "it.txt", "txt", [
            NewBlock("paragraph", ["Partì.", "Nota.", "Camminò e tornò.", "Fine."]),
        ])
        a, x, b, c = append_beads(conn, "p1", [
            NewBead([s1], [t1], 0.9, "anchor"),
            NewBead([], [t2], 0.2, "length"),
            NewBead([s2, s3], [t3], 0.7, "length"),
            NewBead([s4], [t4], 0.8, "anchor"),
        ])
        conn.execute("UPDATE beads SET reviewed = 1 WHERE id IN (?, ?)", (a, b))
        (other, other2), = create_document(conn, "p2", "source", "x.txt", "txt", [
            NewBlock("paragraph", ["X.", "Y."]),
        ])
        append_beads(conn, "p2", [NewBead([other, other2], [], 0.5, "length")])
    ids = dict(s1=s1, s2=s2, s3=s3, s4=s4, f1=f1, t1=t1, t2=t2, t3=t3, t4=t4, A=a, X=x, B=b, C=c, other=other)
    yield conn, ids
    conn.close()


def seg(conn, segment_id):
    """(text, original_text, bead_id), or None if the segment is gone."""
    row = conn.execute("SELECT text, original_text, bead_id FROM segments WHERE id = ?", (segment_id,)).fetchone()
    return None if row is None else tuple(row)


def bead(conn, bead_id):
    """(source ids, target ids, method, confidence, reviewed), or None if the bead is gone."""
    row = conn.execute("SELECT method, confidence, reviewed FROM beads WHERE id = ?", (bead_id,)).fetchone()
    if row is None:
        return None
    sides = []
    for side in ("source", "target"):
        sides.append([r[0] for r in conn.execute(
            "SELECT s.id FROM segments s JOIN blocks b ON b.id = s.block_id "
            "JOIN documents d ON d.id = b.document_id WHERE s.bead_id = ? AND d.side = ? ORDER BY b.ord, s.ord",
            (bead_id, side),
        )])
    return (*sides, *row)


def valid(conn):
    return check_project(conn, "p1") == [] and check_project(conn, "p2") == []


def run(conn, op, *args):
    """Run an operation, check invariants and its undo/redo round trip; return its result."""
    before = snapshot(conn)
    with transaction(conn):
        result = op(conn, "p1", *args)
    after = snapshot(conn)
    assert valid(conn)
    with transaction(conn):
        undo(conn, "p1")
    assert snapshot(conn) == before
    assert valid(conn)
    with transaction(conn):
        redo(conn, "p1")
    assert snapshot(conn) == after
    assert valid(conn)
    return result


def _op_count(conn):
    return conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]


def refused(conn, op, *args):
    before = snapshot(conn)
    ops = _op_count(conn)
    with pytest.raises(DomainError):
        with transaction(conn):
            op(conn, "p1", *args)
    assert snapshot(conn) == before
    assert _op_count(conn) == ops


def test_map_offset():
    assert _map_offset("Il partit.", "Il partit.", 3) == 3
    assert _map_offset("Il marcha. Fin.", "Il mar- cha. Fin.", 11) == 13
    assert _map_offset("Il marcha. Fin.", "Il mar- cha. Fin.", 6) == 8
    assert _map_offset("Il fut là. Fin.", "Il fnt lâ. Fin.", 4) == 4


def test_edit_text(db):
    conn, i = db
    run(conn, edit_text, i["s1"], "Il partit!")
    assert seg(conn, i["s1"]) == ("Il partit!", "Il partit.", i["A"])
    assert bead(conn, i["A"]) == ([i["s1"]], [i["t1"]], "anchor", 0.9, 1)


def test_edit_text_unchanged_records_nothing(db):
    conn, i = db
    with transaction(conn):
        assert edit_text(conn, "p1", i["s1"], "Il partit.") is None
    assert _op_count(conn) == 0


def test_edit_text_empty_refused(db):
    conn, i = db
    refused(conn, edit_text, i["s1"], "  ")


def test_edit_excluded_segment(db):
    conn, i = db
    run(conn, edit_text, i["f1"], "Une autre note.")
    assert seg(conn, i["f1"]) == ("Une autre note.", "Une note.", None)


def test_split_segment(db):
    conn, i = db
    new = run(conn, split_segment, i["s3"], 4)
    assert seg(conn, i["s3"]) == ("Puis", "Puis", i["B"])
    assert seg(conn, new) == ("il revint.", "il revint.", i["B"])
    assert bead(conn, i["B"]) == ([i["s2"], i["s3"], new], [i["t3"]], "length", 0.7, 1)


def test_split_refused(db):
    conn, i = db
    refused(conn, split_segment, i["s3"], 0)
    refused(conn, split_segment, i["s3"], len("Puis il revint."))
    with transaction(conn):
        edit_text(conn, "p1", i["s1"], "Il partit.   ")
    refused(conn, split_segment, i["s1"], 11)  # second part whitespace only


def test_split_after_edit_maps_original(db):
    conn, i = db
    with transaction(conn):
        edit_text(conn, "p1", i["s4"], "Il marcha. Fin.")
    new = run(conn, split_segment, i["s4"], 11)
    assert seg(conn, i["s4"]) == ("Il marcha.", "Il mar- cha.", i["C"])
    assert seg(conn, new) == ("Fin.", "Fin.", i["C"])


def test_join_same_bead(db):
    conn, i = db
    run(conn, join_with_next, i["s2"])
    assert seg(conn, i["s2"]) == ("Il marcha. Puis il revint.", "Il marcha. Puis il revint.", i["B"])
    assert seg(conn, i["s3"]) is None
    assert bead(conn, i["B"]) == ([i["s2"]], [i["t3"]], "length", 0.7, 1)


def test_join_across_beads_merges_run(db):
    conn, i = db
    start = snapshot(conn)
    run(conn, join_with_next, i["s1"])
    assert seg(conn, i["s1"]) == ("Il partit. Il marcha.", "Il partit. Il marcha.", i["A"])
    assert seg(conn, i["s2"]) is None
    assert bead(conn, i["A"]) == ([i["s1"], i["s3"]], [i["t1"], i["t2"], i["t3"]], "manual", 1.0, 0)
    assert bead(conn, i["X"]) is None
    assert bead(conn, i["B"]) is None
    with transaction(conn):
        undo(conn, "p1")
    assert snapshot(conn) == start


def test_join_refused(db):
    conn, i = db
    refused(conn, join_with_next, i["s3"])  # last of its block
    refused(conn, join_with_next, i["other"])
    refused(conn, edit_text, i["other"], "Z.")
    refused(conn, split_segment, i["other"], 1)
