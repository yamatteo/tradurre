"""Tests for block exclude/include (tradurre.domain.blocks)."""

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain import DomainError
from tradurre.domain.history import redo, transaction, undo
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.beads import merge_with_next
from tradurre.domain.blocks import exclude_block, include_block


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
    block = lambda s: conn.execute("SELECT block_id FROM segments WHERE id = ?", (s,)).fetchone()[0]
    ids = dict(S1=block(s1), S2=block(f1), S3=block(s4), T1=block(t1), other_block=block(other), s1=s1, s2=s2, s3=s3, s4=s4, f1=f1, t1=t1, t2=t2, t3=t3, t4=t4, A=a, X=x, B=b, C=c, other=other)
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


def bead_ords(conn):
    return [r[0] for r in conn.execute("SELECT id FROM beads WHERE project_id = 'p1' ORDER BY ord")]


def test_exclude_keeps_bead_with_other_side(db):
    conn, i = db
    run(conn, exclude_block, i["S3"])
    assert seg(conn, i["s4"])[2] is None
    assert bead(conn, i["C"]) == ([], [i["t4"]], "manual", 1.0, 0)


def test_exclude_deletes_emptied_bead(db):
    conn, i = db
    start = snapshot(conn)
    run(conn, exclude_block, i["T1"])  # X ( | t2) is left empty
    assert bead(conn, i["X"]) is None
    assert bead(conn, i["A"]) == ([i["s1"]], [], "manual", 1.0, 1)
    with transaction(conn):
        undo(conn, "p1")
    assert snapshot(conn) == start
    assert bead(conn, i["X"]) == ([], [i["t2"]], "length", 0.2, 0)


def test_exclude_corrects_remaining_beads(db):
    conn, i = db
    run(conn, exclude_block, i["S1"])
    assert bead(conn, i["A"]) == ([], [i["t1"]], "manual", 1.0, 1)
    assert bead(conn, i["B"]) == ([], [i["t3"]], "manual", 1.0, 1)
    assert bead(conn, i["X"]) == ([], [i["t2"]], "length", 0.2, 0)
    assert [seg(conn, i[s])[2] for s in ("s1", "s2", "s3")] == [None, None, None]


def test_include_between_beads_makes_new_bead(db):
    conn, i = db
    new = run(conn, include_block, i["S2"])
    new_bead = seg(conn, i["f1"])[2]
    assert new_bead not in (i["A"], i["X"], i["B"], i["C"])
    assert bead(conn, new_bead) == ([i["f1"]], [], "manual", 0.0, 0)
    assert bead_ords(conn) == [i["A"], i["X"], i["B"], new_bead, i["C"]]
    assert new is not None


def test_include_inside_bead_joins_it(db):
    conn, i = db
    with transaction(conn):
        merge_with_next(conn, "p1", i["B"])
    run(conn, include_block, i["S2"])
    assert bead(conn, i["B"]) == ([i["s2"], i["s3"], i["f1"], i["s4"]], [i["t3"], i["t4"]], "manual", 1.0, 0)


def test_include_without_preceding_goes_first(db):
    conn, i = db
    with transaction(conn):
        exclude_block(conn, "p1", i["S1"])
    run(conn, include_block, i["S1"])
    new_bead = seg(conn, i["s1"])[2]
    assert bead(conn, new_bead) == ([i["s1"], i["s2"], i["s3"]], [], "manual", 0.0, 0)
    assert bead_ords(conn)[0] == new_bead
    assert valid(conn)


def test_refused(db):
    conn, i = db
    refused(conn, exclude_block, i["S2"])
    refused(conn, include_block, i["S1"])
    refused(conn, exclude_block, i["other_block"])
    refused(conn, include_block, i["other_block"])
