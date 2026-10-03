"""Tests for the text-layer builder and the invariant checker (tradurre.domain)."""

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document


def _add_project(conn, project_id):
    conn.execute(
        "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
        "VALUES (?, 'Book', 'fr', 'it', 'now', 'now')",
        (project_id,),
    )


@pytest.fixture()
def project(tmp_path):
    """Source: 3 blocks (the middle one excluded); target: 2 blocks; 1:1, 2:1, 0:1 and 1:0 beads."""
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with conn:
        _add_project(conn, "p1")
        (s1, s2), (footnote,), (s3, s4) = create_document(conn, "p1", "source", "fr.pdf", "pdf", [
            NewBlock("paragraph", ["Il partit.", "Il marcha longtemps."]),
            NewBlock("footnote", ["Une note."], excluded=True),
            NewBlock("paragraph", ["Puis il revint.", "Fin."]),
        ])
        (t1,), (t2, t3) = create_document(conn, "p1", "target", "it.pdf", "pdf", [
            NewBlock("paragraph", ["Partì."]),
            NewBlock("paragraph", ["Camminò a lungo e poi tornò.", "Nota del traduttore."]),
        ])
        beads = append_beads(conn, "p1", [
            NewBead([s1], [t1], 0.9, "anchor"),
            NewBead([s2, s3], [t2], 0.7, "length"),
            NewBead([], [t3], 0.2, "length"),
            NewBead([s4], [], 0.2, "length"),
        ])
    ids = {"s1": s1, "s2": s2, "s3": s3, "s4": s4, "footnote": footnote,
           "t1": t1, "t2": t2, "t3": t3, "beads": beads}
    yield conn, ids
    conn.close()


def _codes(errors):
    return {e.split(":", 1)[0] for e in errors}


def test_built_project_is_valid(project):
    conn, _ = project
    assert check_project(conn, "p1") == []


def test_append_beads_continues_after_last(project):
    conn, ids = project
    ords = [r[0] for r in conn.execute("SELECT ord FROM beads WHERE project_id = 'p1' ORDER BY ord")]
    assert ords == [0, 1024, 2048, 3072]


def test_i1_excluded_segment_with_bead(project):
    conn, ids = project
    conn.execute("UPDATE segments SET bead_id = ? WHERE id = ?", (ids["beads"][1], ids["footnote"]))
    assert "I1" in _codes(check_project(conn, "p1"))


def test_i2_segment_points_at_other_project(project):
    conn, ids = project
    _add_project(conn, "p2")
    (other_bead,) = append_beads(conn, "p2", [NewBead([], [], 1.0, "manual")])
    conn.execute("UPDATE segments SET bead_id = ? WHERE id = ?", (other_bead, ids["s4"]))
    errors = check_project(conn, "p1")
    assert "I2" in _codes(errors)


def test_i3_bead_without_segments(project):
    conn, _ = project
    append_beads(conn, "p1", [NewBead([], [], 1.0, "manual")])
    assert "I3" in _codes(check_project(conn, "p1"))


def test_i4_swapped_bead_order(project):
    conn, ids = project
    a, b = ids["beads"][0], ids["beads"][1]
    conn.execute("UPDATE beads SET ord = -1 WHERE id = ?", (a,))
    conn.execute("UPDATE beads SET ord = 0 WHERE id = ?", (b,))
    conn.execute("UPDATE beads SET ord = 1024 WHERE id = ?", (a,))
    assert "I4" in _codes(check_project(conn, "p1"))


def test_i5_negative_ord(project):
    conn, ids = project
    conn.execute("UPDATE segments SET ord = -5 WHERE id = ?", (ids["s1"],))
    assert "I5" in _codes(check_project(conn, "p1"))
