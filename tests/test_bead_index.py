"""Tests for the bead search index (migration 4): kept in sync by triggers through every write path."""

import time

import pytest
from helpers import actual_index, expected_index

from tradurre.db import MIGRATIONS, get_connection, init_db
from tradurre.domain.beads import merge_with_next, split_bead
from tradurre.domain.blocks import exclude_block, include_block
from tradurre.domain.history import redo, transaction, undo
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.replace import replace_beads
from tradurre.domain.search import fold
from tradurre.domain.segments import edit_text, join_with_next, split_segment


def _add_project(conn, project_id):
    conn.execute(
        "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
        "VALUES (?, 'Book', 'fr', 'it', 'now', 'now')",
        (project_id,),
    )


def _build(conn):
    """Source [s1, s2, s3], footnote [f1] excluded, [s4]; target [t1..t4];
    beads A (s1 | t1), B (s2, s3 | t2), C (s4 | t3, t4)."""
    _add_project(conn, "p1")
    (s1, s2, s3), (f1,), (s4,) = create_document(conn, "p1", "source", "fr.txt", "txt", [
        NewBlock("paragraph", ["Le désœuvrement le gagna.", "Il partit.", "Puis il revint."]),
        NewBlock("footnote", ["Zanzibar introuvable."], excluded=True),
        NewBlock("paragraph", ["Fin de l’histoire."]),
    ])
    (t1, t2, t3, t4), = create_document(conn, "p1", "target", "it.txt", "txt", [
        NewBlock("paragraph", ["Lo prese l'ozio.", "Partì e tornò.", "Fine", "della storia."]),
    ])
    a, b, c = append_beads(conn, "p1", [
        NewBead([s1], [t1], 0.9, "anchor"),
        NewBead([s2, s3], [t2], 0.6, "length"),
        NewBead([s4], [t3, t4], 0.5, "length"),
    ])
    return dict(s1=s1, s2=s2, s3=s3, s4=s4, f1=f1, t1=t1, t2=t2, t3=t3, t4=t4, A=a, B=b, C=c)


@pytest.fixture()
def db(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with transaction(conn):
        ids = _build(conn)
        ids["block_f"] = conn.execute("SELECT block_id FROM segments WHERE id = ?", (ids["f1"],)).fetchone()[0]
        ids["block_s1"] = conn.execute("SELECT block_id FROM segments WHERE id = ?", (ids["s1"],)).fetchone()[0]
    yield conn, ids
    conn.close()


def in_sync(conn):
    return actual_index(conn) == expected_index(conn)


def match(conn, query):
    return [r[0] for r in conn.execute("SELECT rowid FROM bead_index WHERE bead_index MATCH ?", (query,))]


def test_built_project_is_indexed(db):
    conn, i = db
    assert in_sync(conn)
    assert len(actual_index(conn)) == 3
    assert match(conn, "zanzibar") == []


def _split_s3(c, i):
    return split_segment(c, "p1", i["s3"], 4)


OPERATIONS = [
    ("edit_text", lambda c, i: edit_text(c, "p1", i["s2"], "Il s'en alla.")),
    ("split_segment", _split_s3),
    ("join_cross_bead", lambda c, i: join_with_next(c, "p1", i["s1"])),
    ("merge_with_next", lambda c, i: merge_with_next(c, "p1", i["A"])),
    ("split_bead", lambda c, i: split_bead(c, "p1", i["B"], i["s3"], None)),
    ("exclude_block", lambda c, i: exclude_block(c, "p1", i["block_s1"])),
    ("include_block", lambda c, i: include_block(c, "p1", i["block_f"])),
    ("replace_beads", lambda c, i: replace_beads(c, "p1", i["A"], i["B"], [
        NewBead([i["s1"], i["s2"]], [i["t1"]], 0.5, "llm"),
        NewBead([i["s3"]], [i["t2"]], 0.5, "llm"),
    ])),
]


@pytest.mark.parametrize("op", [op for _, op in OPERATIONS], ids=[name for name, _ in OPERATIONS])
def test_index_follows_operation_undo_redo(db, op):
    conn, i = db
    before = actual_index(conn)
    with transaction(conn):
        op(conn, i)
    assert in_sync(conn)
    after = actual_index(conn)
    if op is not _split_s3:  # a split re-joins to the same bead text: the index rightly stays the same
        assert after != before
    with transaction(conn):
        undo(conn, "p1")
    assert in_sync(conn)
    assert actual_index(conn) == before
    with transaction(conn):
        redo(conn, "p1")
    assert in_sync(conn)
    assert actual_index(conn) == after


def test_include_block_makes_text_searchable(db):
    conn, i = db
    with transaction(conn):
        include_block(conn, "p1", i["block_f"])
    assert len(match(conn, "zanzibar")) == 1


def test_matching_folds_case_accents_ligatures(db):
    conn, i = db
    assert match(conn, "desoeuvrement") == [i["A"]]
    assert match(conn, fold("DESŒUVREMENT")) == [i["A"]]
    assert match(conn, '"l histoire"') == [i["C"]]
    assert match(conn, "source : (histoire)") == [i["C"]]
    assert match(conn, "target : (histoire)") == []
    assert match(conn, "target : (storia)") == [i["C"]]
    assert match(conn, "ozio") == [i["A"]]
    assert match(conn, "parti") == [i["B"]]  # "Partì" in the target, accent folded


def test_project_delete_cascades_to_index(db):
    conn, _ = db
    with transaction(conn):
        conn.execute("DELETE FROM projects WHERE id = 'p1'")
    assert actual_index(conn) == set()


def test_migration_indexes_existing_beads(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    try:
        for version, migrate in enumerate(MIGRATIONS[:3], start=1):
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                migrate(conn)
                conn.execute(f"PRAGMA user_version = {version}")
        with transaction(conn):
            ids = _build(conn)
        init_db(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
        assert len(actual_index(conn)) == 3
        assert in_sync(conn)
        assert match(conn, "desoeuvrement") == [ids["A"]]
    finally:
        conn.close()


def test_building_large_project_is_fast(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    n = 10_000
    start = time.perf_counter()
    with transaction(conn):
        _add_project(conn, "big")
        (source,) = create_document(conn, "big", "source", "fr.txt", "txt",
                                    [NewBlock("paragraph", [f"Phrase numéro {k}." for k in range(n)])])
        (target,) = create_document(conn, "big", "target", "it.txt", "txt",
                                    [NewBlock("paragraph", [f"Frase numero {k}." for k in range(n)])])
        append_beads(conn, "big", [NewBead([s], [t], 0.5, "length") for s, t in zip(source, target)])
    elapsed = time.perf_counter() - start
    print(f"10,000-bead build with index triggers: {elapsed:.2f} s")
    assert conn.execute("SELECT COUNT(*) FROM bead_index").fetchone()[0] == n
    assert elapsed < 5
    conn.close()
