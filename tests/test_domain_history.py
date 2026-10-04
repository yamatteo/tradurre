"""Tests for the Recorder and undo/redo (tradurre.domain.history)."""

import json

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain.history import Recorder, record, redo, transaction, undo
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document


def snapshot(conn):
    return {
        table: sorted(tuple(r) for r in conn.execute(f"SELECT * FROM {table}"))
        for table in ("documents", "blocks", "segments", "beads")
    }


def valid(conn):
    return check_project(conn, "p1") == []


@pytest.fixture()
def db(tmp_path):
    """Project p1: beads b1 (s1, s2 | t1, t2) and b2 (s3, s4 | t3, t4)."""
    path = tmp_path / "test.db"
    conn = get_connection(path)
    init_db(conn)
    with transaction(conn):
        conn.execute(
            "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
            "VALUES ('p1', 'Book', 'fr', 'it', 'now', 'now')"
        )
        (s1, s2, s3, s4), = create_document(conn, "p1", "source", "fr.txt", "txt", [
            NewBlock("paragraph", ["Un.", "Deux.", "Trois.", "Quatre."]),
        ])
        (t1, t2, t3, t4), = create_document(conn, "p1", "target", "it.txt", "txt", [
            NewBlock("paragraph", ["Uno.", "Due.", "Tre.", "Quattro."]),
        ])
        b1, b2 = append_beads(conn, "p1", [
            NewBead([s1, s2], [t1, t2], 0.8, "anchor"),
            NewBead([s3, s4], [t3, t4], 0.8, "anchor"),
        ])
    ids = dict(s1=s1, s2=s2, s3=s3, s4=s4, t1=t1, t2=t2, t3=t3, t4=t4, b1=b1, b2=b2)
    assert valid(conn)
    yield conn, ids, path
    conn.close()


def _edit_and_new_bead(conn, ids, kind="edit"):
    """Update s1's text, insert a bead between b1 and b2, move s2 into it."""
    with transaction(conn):
        rec = Recorder(conn)
        rec.update("segments", ids["s1"], text="Un!")
        new = rec.insert("beads", {"project_id": "p1", "ord": 512, "confidence": 1.0, "method": "manual"})
        rec.update("segments", ids["s2"], bead_id=new)
        op = record(conn, "p1", kind, rec)
    return op, new


def test_undo_redo_round_trip(db):
    conn, ids, _ = db
    before = snapshot(conn)
    _, new = _edit_and_new_bead(conn, ids)
    after = snapshot(conn)
    assert valid(conn)

    with transaction(conn):
        undo(conn, "p1")
    assert snapshot(conn) == before
    assert valid(conn)

    with transaction(conn):
        redo(conn, "p1")
    assert snapshot(conn) == after
    assert conn.execute("SELECT bead_id FROM segments WHERE id = ?", (ids["s2"],)).fetchone()[0] == new
    assert valid(conn)


def test_undo_merge_restores_deleted_bead(db):
    conn, ids, _ = db
    before = snapshot(conn)
    with transaction(conn):
        rec = Recorder(conn)
        for seg in ("s3", "s4", "t3", "t4"):
            rec.update("segments", ids[seg], bead_id=ids["b1"])
        rec.delete("beads", ids["b2"])
        record(conn, "p1", "merge", rec)
    after = snapshot(conn)
    assert valid(conn)

    with transaction(conn):
        undo(conn, "p1")
    assert snapshot(conn) == before
    assert conn.execute("SELECT id FROM beads WHERE id = ?", (ids["b2"],)).fetchone() is not None
    assert valid(conn)

    with transaction(conn):
        redo(conn, "p1")
    assert snapshot(conn) == after
    assert valid(conn)


def test_swap_ords_respects_unique(db):
    conn, ids, _ = db
    b1, b2 = ids["b1"], ids["b2"]
    ord1, ord2 = (conn.execute("SELECT ord FROM beads WHERE id = ?", (b,)).fetchone()[0] for b in (b1, b2))
    before = snapshot(conn)
    with transaction(conn):
        rec = Recorder(conn)
        rec.update("beads", b1, ord=-1)
        rec.update("beads", b2, ord=ord1)
        rec.update("beads", b1, ord=ord2)
        # Swap the segments too, so the alignment stays valid.
        for seg in ("s1", "s2", "t1", "t2"):
            rec.update("segments", ids[seg], bead_id=b2)
        for seg in ("s3", "s4", "t3", "t4"):
            rec.update("segments", ids[seg], bead_id=b1)
        record(conn, "p1", "swap", rec)
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


def test_new_operation_drops_redo(db):
    conn, ids, _ = db
    _edit_and_new_bead(conn, ids)
    with transaction(conn):
        undo(conn, "p1")
    with transaction(conn):
        rec = Recorder(conn)
        rec.update("segments", ids["s3"], text="Trois!")
        record(conn, "p1", "edit", rec)
    with transaction(conn):
        assert redo(conn, "p1") is None
    assert conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 1
    assert valid(conn)


def _mark(conn, bead_id, kind="streak", coalesce=True):
    with transaction(conn):
        rec = Recorder(conn)
        rec.update("beads", bead_id, reviewed=1)
        return record(conn, "p1", kind, rec, coalesce=coalesce)


def _reviewed(conn, bead_id):
    return conn.execute("SELECT reviewed FROM beads WHERE id = ?", (bead_id,)).fetchone()[0]


def test_coalesce_same_kind(db):
    conn, ids, _ = db
    op1 = _mark(conn, ids["b1"])
    op2 = _mark(conn, ids["b2"])
    assert op1 == op2
    with transaction(conn):
        undo(conn, "p1")
    assert (_reviewed(conn, ids["b1"]), _reviewed(conn, ids["b2"])) == (0, 0)
    assert valid(conn)


def test_coalesce_not_after_undo(db):
    conn, ids, _ = db
    _mark(conn, ids["b1"])
    with transaction(conn):
        undo(conn, "p1")
    _mark(conn, ids["b2"])
    # The undone operation was dropped; the new one holds only b2's mark.
    (changes,) = conn.execute("SELECT changes FROM operations").fetchone()
    assert [c[1] for c in json.loads(changes)] == [ids["b2"]]
    with transaction(conn):
        undo(conn, "p1")
    assert (_reviewed(conn, ids["b1"]), _reviewed(conn, ids["b2"])) == (0, 0)


def test_coalesce_not_across_kinds(db):
    conn, ids, _ = db
    op1 = _mark(conn, ids["b1"], kind="streak")
    op2 = _mark(conn, ids["b2"], kind="review")
    assert op1 != op2
    with transaction(conn):
        undo(conn, "p1")
    assert (_reviewed(conn, ids["b1"]), _reviewed(conn, ids["b2"])) == (1, 0)


def test_survives_reopen(db):
    conn, ids, path = db
    before = snapshot(conn)
    _edit_and_new_bead(conn, ids)
    after = snapshot(conn)
    conn.close()

    conn = get_connection(path)
    with transaction(conn):
        assert undo(conn, "p1") is not None
    assert snapshot(conn) == before
    conn.close()

    conn = get_connection(path)
    with transaction(conn):
        assert redo(conn, "p1") is not None
    assert snapshot(conn) == after
    assert valid(conn)
    conn.close()


def test_recorder_refuses_block_insert_and_delete(db):
    conn, ids, _ = db
    rec = Recorder(conn)
    with pytest.raises(ValueError):
        rec.delete("blocks", 1)
    with pytest.raises(ValueError):
        rec.insert("documents", {"project_id": "p1"})
    with pytest.raises(ValueError):
        rec.update("operations", 1, kind="x")
