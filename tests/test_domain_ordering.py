"""Tests for sparse ordering (tradurre.domain.ordering)."""

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain.history import Recorder, record, redo, transaction, undo
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.ordering import ord_after


def _add_project(conn, project_id):
    conn.execute(
        "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
        "VALUES (?, 'Book', 'fr', 'it', 'now', 'now')",
        (project_id,),
    )


@pytest.fixture()
def conn(tmp_path):
    """Project p1 with beads at ords 0, 1024, 2048 (one source segment each); empty project p2."""
    c = get_connection(tmp_path / "test.db")
    init_db(c)
    with transaction(c):
        _add_project(c, "p1")
        _add_project(c, "p2")
        (segs,) = create_document(c, "p1", "source", "fr.txt", "txt", [NewBlock("paragraph", ["A.", "B.", "C."])])
        append_beads(c, "p1", [NewBead([s], [], 0.5, "length") for s in segs])
    yield c
    c.close()


def _beads(conn, project_id="p1"):
    return [tuple(r) for r in conn.execute(
        "SELECT id, ord FROM beads WHERE project_id = ? ORDER BY ord", (project_id,)
    )]


def _ord_after(conn, project_id, after_id):
    """ord_after inside a recorded operation; returns (result, operation id)."""
    with transaction(conn):
        rec = Recorder(conn)
        result = ord_after(rec, "beads", project_id, after_id)
        op = record(conn, project_id, "test", rec)
    return result, op


def test_after_first(conn):
    (b1, _), _, _ = _beads(conn)
    assert _ord_after(conn, "p1", b1)[0] == 512


def test_after_last(conn):
    _, _, (b3, _) = _beads(conn)
    assert _ord_after(conn, "p1", b3)[0] == 3072


def test_empty_project(conn):
    result, op = _ord_after(conn, "p2", None)
    assert (result, op) == (0, None)


def test_before_first_renumbers(conn):
    ids = [b for b, _ in _beads(conn)]
    assert _ord_after(conn, "p1", None)[0] == 512
    assert _beads(conn) == list(zip(ids, [1024, 2048, 3072]))


def test_no_room_renumbers_and_undo_redo(conn):
    ids = [b for b, _ in _beads(conn)]
    with transaction(conn):
        rec = Recorder(conn)
        rec.update("beads", ids[1], ord=1)
        rec.delete("segments", conn.execute("SELECT id FROM segments WHERE bead_id = ?", (ids[2],)).fetchone()[0])
        rec.delete("beads", ids[2])
        record(conn, "p1", "setup", rec)
    before = _beads(conn)
    assert before == [(ids[0], 0), (ids[1], 1)]

    result, op = _ord_after(conn, "p1", ids[0])
    assert result == 1536
    after = _beads(conn)
    assert after == [(ids[0], 1024), (ids[1], 2048)]

    with transaction(conn):
        assert undo(conn, "p1") == op
    assert _beads(conn) == before
    with transaction(conn):
        assert redo(conn, "p1") == op
    assert _beads(conn) == after


def test_value_errors(conn):
    (b1, _), _, _ = _beads(conn)
    rec = Recorder(conn)
    with pytest.raises(ValueError):
        ord_after(rec, "blocks", "p1", None)
    with pytest.raises(ValueError):
        ord_after(rec, "beads", "p2", b1)
    assert rec.changes == []
