"""Tests for the bead corrections (tradurre.domain.beads)."""

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain import DomainError
from tradurre.domain.beads import (
    merge_with_next,
    move_first_to_previous,
    move_last_to_next,
    set_reviewed,
    split_bead,
)
from tradurre.domain.history import redo, transaction, undo
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document


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
    """Beads A (s1 | t1), B (s2, s3 | t2), C (s4 | t3, t4); only A reviewed. Project p2 has one bead."""
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with transaction(conn):
        _add_project(conn, "p1")
        _add_project(conn, "p2")
        (s1, s2), (s3, s4) = create_document(conn, "p1", "source", "fr.txt", "txt", [
            NewBlock("paragraph", ["Un.", "Deux."]),
            NewBlock("paragraph", ["Trois.", "Quatre."]),
        ])
        (t1, t2, t3, t4), = create_document(conn, "p1", "target", "it.txt", "txt", [
            NewBlock("paragraph", ["Uno.", "Due e tre.", "Quattro,", "ancora."]),
        ])
        a, b, c = append_beads(conn, "p1", [
            NewBead([s1], [t1], 0.9, "anchor"),
            NewBead([s2, s3], [t2], 0.6, "length"),
            NewBead([s4], [t3, t4], 0.5, "length"),
        ])
        conn.execute("UPDATE beads SET reviewed = 1 WHERE id = ?", (a,))
        (x1,), = create_document(conn, "p2", "source", "x.txt", "txt", [NewBlock("paragraph", ["X."])])
        (other,) = append_beads(conn, "p2", [NewBead([x1], [], 0.5, "length")])
    ids = dict(s1=s1, s2=s2, s3=s3, s4=s4, t1=t1, t2=t2, t3=t3, t4=t4, A=a, B=b, C=c, other=other)
    yield conn, ids
    conn.close()


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


def run(conn, op, *args, **kwargs):
    """Run an operation, check invariants and its undo/redo round trip; return its result."""
    before = snapshot(conn)
    with transaction(conn):
        result = op(conn, "p1", *args, **kwargs)
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


def refused(conn, op, *args, **kwargs):
    before = snapshot(conn)
    ops = conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
    with pytest.raises(DomainError):
        with transaction(conn):
            op(conn, "p1", *args, **kwargs)
    assert snapshot(conn) == before
    assert conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == ops


def test_move_first_to_previous(db):
    conn, i = db
    run(conn, move_first_to_previous, i["C"], "target")
    assert bead(conn, i["B"]) == ([i["s2"], i["s3"]], [i["t2"], i["t3"]], "manual", 1.0, 0)
    assert bead(conn, i["C"]) == ([i["s4"]], [i["t4"]], "manual", 1.0, 0)
    assert bead(conn, i["A"]) == ([i["s1"]], [i["t1"]], "anchor", 0.9, 1)


def test_move_first_without_previous_refused(db):
    conn, i = db
    refused(conn, move_first_to_previous, i["A"], "source")


def test_move_without_segment_on_side_refused(db):
    conn, i = db
    with transaction(conn):
        move_last_to_next(conn, "p1", i["A"], "source")
    refused(conn, move_last_to_next, i["A"], "source")


def test_move_last_to_next(db):
    conn, i = db
    run(conn, move_last_to_next, i["B"], "source")
    assert bead(conn, i["B"]) == ([i["s2"]], [i["t2"]], "manual", 1.0, 0)
    assert bead(conn, i["C"]) == ([i["s3"], i["s4"]], [i["t3"], i["t4"]], "manual", 1.0, 0)


def test_emptied_bead_is_deleted_and_comes_back(db):
    conn, i = db
    start = snapshot(conn)
    with transaction(conn):
        move_last_to_next(conn, "p1", i["A"], "source")
    middle = snapshot(conn)
    assert bead(conn, i["A"]) == ([], [i["t1"]], "manual", 1.0, 1)
    run(conn, move_last_to_next, i["A"], "target")
    assert bead(conn, i["A"]) is None
    assert bead(conn, i["B"]) == ([i["s1"], i["s2"], i["s3"]], [i["t1"], i["t2"]], "manual", 1.0, 0)

    with transaction(conn):
        undo(conn, "p1")
    assert snapshot(conn) == middle
    assert bead(conn, i["A"]) is not None
    with transaction(conn):
        undo(conn, "p1")
    assert snapshot(conn) == start


def test_merge_unreviewed(db):
    conn, i = db
    run(conn, merge_with_next, i["A"])
    assert bead(conn, i["A"]) == ([i["s1"], i["s2"], i["s3"]], [i["t1"], i["t2"]], "manual", 1.0, 0)
    assert bead(conn, i["B"]) is None


def test_merge_reviewed(db):
    conn, i = db
    with transaction(conn):
        set_reviewed(conn, "p1", [i["B"]], True)
    run(conn, merge_with_next, i["A"])
    assert bead(conn, i["A"])[4] == 1


def test_merge_last_refused(db):
    conn, i = db
    refused(conn, merge_with_next, i["C"])


def test_split_source_only(db):
    conn, i = db
    new = run(conn, split_bead, i["B"], i["s3"], None)
    assert bead(conn, i["B"]) == ([i["s2"]], [i["t2"]], "manual", 1.0, 0)
    assert bead(conn, new) == ([i["s3"]], [], "manual", 1.0, 0)
    ords = [r[0] for r in conn.execute("SELECT id FROM beads WHERE project_id = 'p1' ORDER BY ord")]
    assert ords == [i["A"], i["B"], new, i["C"]]


def test_split_both_sides_copies_reviewed(db):
    conn, i = db
    with transaction(conn):
        merge_with_next(conn, "p1", i["A"])  # A (s1, s2, s3 | t1, t2), unreviewed
        set_reviewed(conn, "p1", [i["A"]], True)
    new = run(conn, split_bead, i["A"], i["s2"], i["t2"])
    assert bead(conn, i["A"]) == ([i["s1"]], [i["t1"]], "manual", 1.0, 1)
    assert bead(conn, new) == ([i["s2"], i["s3"]], [i["t2"]], "manual", 1.0, 1)


def test_split_refused(db):
    conn, i = db
    refused(conn, split_bead, i["B"], None, None)
    refused(conn, split_bead, i["B"], i["s2"], i["t2"])  # nothing would stay
    refused(conn, split_bead, i["B"], i["s4"], None)  # not B's segment


def test_set_reviewed(db):
    conn, i = db
    run(conn, set_reviewed, [i["A"], i["B"]], True)
    assert [bead(conn, b)[4] for b in (i["A"], i["B"], i["C"])] == [1, 1, 0]
    with transaction(conn):
        assert set_reviewed(conn, "p1", [i["A"]], True) is None


def test_other_project_refused(db):
    conn, i = db
    refused(conn, move_first_to_previous, i["other"], "source")
    refused(conn, move_last_to_next, i["other"], "source")
    refused(conn, merge_with_next, i["other"])
    refused(conn, split_bead, i["other"], None, None)
    refused(conn, set_reviewed, [i["other"]], True)
