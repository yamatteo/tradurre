"""Tests for replacing a run of beads (tradurre.domain.replace) and `ordering.ords_after`."""

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain import DomainError
from tradurre.domain.history import Recorder, record, redo, transaction, undo
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.ordering import ords_after
from tradurre.domain.replace import replace_beads


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


def _documents(conn, project_id):
    """Source [s1, s2, s3], footnote [f1] excluded, [s4, s5]; target [t1..t5]."""
    (s1, s2, s3), (f1,), (s4, s5) = create_document(conn, project_id, "source", "fr.txt", "txt", [
        NewBlock("paragraph", ["Un.", "Deux.", "Trois."]),
        NewBlock("footnote", ["Note."], excluded=True),
        NewBlock("paragraph", ["Quatre.", "Cinq."]),
    ])
    (t1, t2, t3, t4, t5), = create_document(conn, project_id, "target", "it.txt", "txt", [
        NewBlock("paragraph", ["Uno.", "Due e tre.", "Quattro,", "ancora.", "Cinque."]),
    ])
    return dict(s1=s1, s2=s2, s3=s3, s4=s4, s5=s5, f1=f1, t1=t1, t2=t2, t3=t3, t4=t4, t5=t5)


@pytest.fixture()
def db(tmp_path):
    """p1: beads A (s1 | t1), B (s2, s3 | t2), C (s4 | t3, t4), D (s5 | t5). p2: one bead; p3: no beads."""
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with transaction(conn):
        for p in ("p1", "p2", "p3"):
            _add_project(conn, p)
        i = _documents(conn, "p1")
        i["A"], i["B"], i["C"], i["D"] = append_beads(conn, "p1", [
            NewBead([i["s1"]], [i["t1"]], 0.9, "anchor"),
            NewBead([i["s2"], i["s3"]], [i["t2"]], 0.6, "length"),
            NewBead([i["s4"]], [i["t3"], i["t4"]], 0.5, "length"),
            NewBead([i["s5"]], [i["t5"]], 0.9, "anchor"),
        ])
        (x,), = create_document(conn, "p2", "source", "x.txt", "txt", [NewBlock("paragraph", ["X."])])
        (i["other"],) = append_beads(conn, "p2", [NewBead([x], [], 0.5, "length")])
        i["p3"] = _documents(conn, "p3")
    yield conn, i
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


def bead_order(conn, project_id="p1"):
    return [r[0] for r in conn.execute("SELECT id FROM beads WHERE project_id = ? ORDER BY ord", (project_id,))]


def valid(conn, project_id="p1"):
    return check_project(conn, project_id) == []


def run(conn, project_id, *args):
    """replace_beads with invariants and an undo/redo round trip; return the new ids."""
    before = snapshot(conn)
    with transaction(conn):
        ids = replace_beads(conn, project_id, *args)
    after = snapshot(conn)
    assert valid(conn, project_id)
    with transaction(conn):
        undo(conn, project_id)
    assert snapshot(conn) == before
    with transaction(conn):
        redo(conn, project_id)
    assert snapshot(conn) == after
    assert valid(conn, project_id)
    return ids


def _op_count(conn):
    return conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]


def refused(conn, *args):
    before = snapshot(conn)
    ops = _op_count(conn)
    with pytest.raises(DomainError):
        with transaction(conn):
            replace_beads(conn, "p1", *args)
    assert snapshot(conn) == before
    assert _op_count(conn) == ops


def test_replace_run(db):
    conn, i = db
    new = run(conn, "p1", i["B"], i["C"], [
        NewBead([i["s2"]], [i["t2"]], 0.7, "embedding"),
        NewBead([i["s3"], i["s4"]], [i["t3"]], 0.6, "llm"),
        NewBead([], [i["t4"]], 0.3, "llm"),
    ])
    assert bead(conn, i["B"]) is None and bead(conn, i["C"]) is None
    assert bead_order(conn) == [i["A"], *new, i["D"]]
    assert [bead(conn, b) for b in new] == [
        ([i["s2"]], [i["t2"]], "embedding", 0.7, 0),
        ([i["s3"], i["s4"]], [i["t3"]], "llm", 0.6, 0),
        ([], [i["t4"]], "llm", 0.3, 0),
    ]


def test_replace_with_same_content(db):
    conn, i = db
    (new,) = run(conn, "p1", i["B"], i["B"], [NewBead([i["s2"], i["s3"]], [i["t2"]], 0.6, "length")])
    assert new != i["B"]
    assert bead_order(conn) == [i["A"], new, i["C"], i["D"]]


def test_refusals(db):
    conn, i = db
    B, C = i["B"], i["C"]
    s2, s3, s4, t2, t3, t4 = (i[k] for k in ("s2", "s3", "s4", "t2", "t3", "t4"))
    refused(conn, B, C, [NewBead([s2, s3], [t2, t3, t4], 0.5, "llm")])  # missing s4
    refused(conn, B, C, [NewBead([s2], [t2], 0.5, "llm"), NewBead([s4], [t3], 0.5, "llm"),
                         NewBead([s3], [t4], 0.5, "llm")])  # source order changed
    refused(conn, B, C, [NewBead([i["s1"], s2, s3, s4], [t2, t3, t4], 0.5, "llm")])  # s1 outside the run
    refused(conn, B, C, [NewBead([s2, s3, i["f1"], s4], [t2, t3, t4], 0.5, "llm")])  # f1 excluded
    refused(conn, B, C, [NewBead([s2, s3, s4], [t2, t3, t4], 0.5, "llm"), NewBead([], [], 0.5, "llm")])
    refused(conn, C, B, [NewBead([s2, s3, s4], [t2, t3, t4], 0.5, "llm")])  # first after last
    refused(conn, i["other"], i["other"], [NewBead([], [], 0.5, "llm")])
    refused(conn, B, None, [NewBead([s2, s3], [t2], 0.5, "llm")])
    refused(conn, None, None, [NewBead([s2, s3], [t2], 0.5, "llm")])


def test_bad_values(db):
    conn, i = db
    with pytest.raises(ValueError):
        replace_beads(conn, "p1", i["B"], i["B"], [NewBead([i["s2"], i["s3"]], [i["t2"]], 1.5, "llm")])
    with pytest.raises(ValueError):
        replace_beads(conn, "p1", i["B"], i["B"], [NewBead([i["s2"], i["s3"]], [i["t2"]], 0.5, "magic")])


def test_empty_project(db):
    conn, i = db
    j = i["p3"]
    new = run(conn, "p3", None, None, [
        NewBead([j["s1"]], [j["t1"]], 0.9, "anchor"),
        NewBead([j["s2"], j["s3"]], [j["t2"]], 0.5, "length"),
        NewBead([j["s4"]], [j["t3"], j["t4"]], 0.5, "length"),
        NewBead([j["s5"]], [j["t5"]], 0.9, "anchor"),
    ])
    assert [conn.execute("SELECT ord FROM beads WHERE id = ?", (b,)).fetchone()[0] for b in new] == [
        0, 1024, 2048, 3072,
    ]
    with transaction(conn):
        undo(conn, "p3")
    assert bead_order(conn, "p3") == []


def _ords_after(conn, project_id, after_id, count):
    with transaction(conn):
        rec = Recorder(conn)
        result = ords_after(rec, "beads", project_id, after_id, count)
        record(conn, project_id, "test", rec)
    return result


def _set_ords(conn, ords):
    """Leave p1 with beads A and B at the given ords (C and D merged into B; checked valid)."""
    with transaction(conn):
        rec = Recorder(conn)
        a, b = bead_order(conn)[:2]
        for bead_id in bead_order(conn)[2:]:
            for (seg,) in conn.execute("SELECT id FROM segments WHERE bead_id = ?", (bead_id,)).fetchall():
                rec.update("segments", seg, bead_id=b)
            rec.delete("beads", bead_id)
        rec.update("beads", b, ord=-1)
        rec.update("beads", a, ord=ords[0])
        rec.update("beads", b, ord=ords[1])
        record(conn, "p1", "setup", rec)
    assert valid(conn)
    return a, b


def _ords(conn, ids):
    return [conn.execute("SELECT ord FROM beads WHERE id = ?", (b,)).fetchone()[0] for b in ids]


def test_ords_after_with_room(db):
    conn, _ = db
    a, b = _set_ords(conn, (0, 1024))
    assert _ords_after(conn, "p1", a, 3) == [256, 512, 768]
    assert _ords(conn, (a, b)) == [0, 1024]


def test_ords_after_makes_room(db):
    conn, _ = db
    a, b = _set_ords(conn, (0, 1))
    assert _ords_after(conn, "p1", a, 3) == [2048, 3072, 4096]
    assert _ords(conn, (a, b)) == [1024, 5120]


def test_ords_after_before_first_makes_room(db):
    conn, _ = db
    a, b = _set_ords(conn, (0, 1))
    assert _ords_after(conn, "p1", None, 2) == [1024, 2048]
    assert _ords(conn, (a, b)) == [3072, 4096]


def test_ords_after_last(db):
    conn, i = db
    last = _ords(conn, [i["D"]])[0]
    assert _ords_after(conn, "p1", i["D"], 2) == [last + 1024, last + 2048]


def test_ords_after_count_zero(db):
    conn, i = db
    with pytest.raises(ValueError):
        ords_after(Recorder(conn), "beads", "p1", i["A"], 0)
