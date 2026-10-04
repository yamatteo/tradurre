"""Tests for re-align range (tradurre.services.realign)."""

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain import DomainError
from tradurre.domain.history import transaction, undo
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.services import align
from tradurre.services.realign import realign

SOURCE = ["Marie arriva à Paris le 3 mai.", "Il pleuvait sur la ville depuis des jours.", "Paul partit.",
          "Personne ne dit rien de toute la soirée.", "Fin."]
TARGET = ["Marie arrivò a Parigi il 3 maggio.", "Pioveva sulla città da giorni.", "Paul partì.",
          "Nessuno disse niente per tutta la sera.", "Fine."]


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
    """Beads P (s0 | t0) reviewed, A (s1 | ), B (s2 | t1, t2) reviewed, C (s3 | t3), Z (s4 | t4) reviewed:
    A..C is laid out wrongly by hand. Project p2 has one bead."""
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with transaction(conn):
        _add_project(conn, "p1")
        _add_project(conn, "p2")
        s, = create_document(conn, "p1", "source", "fr.txt", "txt", [NewBlock("paragraph", SOURCE)])
        t, = create_document(conn, "p1", "target", "it.txt", "txt", [NewBlock("paragraph", TARGET)])
        p, a, b, c, z = append_beads(conn, "p1", [
            NewBead([s[0]], [t[0]], 0.9, "length"),
            NewBead([s[1]], [], 0.2, "length"),
            NewBead([s[2]], [t[1], t[2]], 0.3, "length"),
            NewBead([s[3]], [t[3]], 0.8, "length"),
            NewBead([s[4]], [t[4]], 0.9, "length"),
        ])
        conn.execute("UPDATE beads SET reviewed = 1 WHERE id IN (?, ?, ?)", (p, b, z))
        o, = create_document(conn, "p2", "source", "x.txt", "txt", [NewBlock("paragraph", ["X."])])
        (other,) = append_beads(conn, "p2", [NewBead([o[0]], [], 0.5, "length")])
    yield conn, dict(s=s, t=t, P=p, A=a, B=b, C=c, Z=z, other=other)
    conn.close()


def beads(conn):
    """[(source ids, target ids, method, reviewed)] of p1 in order."""
    out = []
    for bead_id, method, reviewed in conn.execute(
        "SELECT id, method, reviewed FROM beads WHERE project_id = 'p1' ORDER BY ord"
    ).fetchall():
        sides = [[r[0] for r in conn.execute(
            "SELECT s.id FROM segments s JOIN blocks b ON b.id = s.block_id JOIN documents d ON d.id = b.document_id "
            "WHERE s.bead_id = ? AND d.side = ? ORDER BY b.ord, s.ord", (bead_id, side))] for side in ("source", "target")]
        out.append((*sides, method, reviewed))
    return out


def _op_count(conn):
    return conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]


def test_realign_replaces_the_stretch_with_the_aligners_beads(db):
    conn, i = db
    s, t = i["s"], i["t"]
    before = snapshot(conn)
    with transaction(conn):
        new = realign(conn, "p1", i["A"], i["C"])
    expected = [([s[1:4][k] for k in b.source], [t[1:4][k] for k in b.target], "length", 0)
                for b in align.align(SOURCE[1:4], TARGET[1:4])]
    after = beads(conn)
    assert after[0] == ([s[0]], [t[0]], "length", 1)  # P, outside: kept, still reviewed
    assert after[-1] == ([s[4]], [t[4]], "length", 1)  # Z, outside: kept, still reviewed
    assert after[1:-1] == expected
    assert len(new) == len(expected)
    assert expected != [([s[1]], [], "length", 0), ([s[2]], [t[1], t[2]], "length", 0), ([s[3]], [t[3]], "length", 0)]
    assert check_project(conn, "p1") == []
    assert _op_count(conn) == 1
    with transaction(conn):
        undo(conn, "p1")
    assert snapshot(conn) == before


def test_realign_refused(db):
    conn, i = db
    before = snapshot(conn)
    for first, last in ((i["C"], i["A"]), (i["other"], i["other"]), (i["A"], i["other"])):
        with pytest.raises(DomainError):
            with transaction(conn):
                realign(conn, "p1", first, last)
    assert snapshot(conn) == before
    assert _op_count(conn) == 0
