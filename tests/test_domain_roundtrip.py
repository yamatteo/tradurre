"""Randomized round trip over all domain operations: invariants hold after every step, and the history undoes
and redoes exactly, whatever the mix (PLAN.md, "Randomized round trip")."""

import random

import pytest
from helpers import actual_index, expected_index

from tradurre.db import get_connection, init_db
from tradurre.domain import DomainError
from tradurre.domain.beads import (
    SIDES,
    _segments,
    merge_with_next,
    move_first_to_previous,
    move_last_to_next,
    set_reviewed,
    split_bead,
)
from tradurre.domain.blocks import exclude_block, include_block
from tradurre.domain.history import redo, transaction, undo
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.replace import replace_beads
from tradurre.domain.segments import edit_text, join_with_next, split_segment

STEPS = 60
SEED_COUNT = 20


def snapshot(conn):
    return {
        table: sorted(tuple(r) for r in conn.execute(f"SELECT * FROM {table}"))
        for table in ("documents", "blocks", "segments", "beads")
    }


def _op_count(conn):
    return conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]


def _words(rng):
    return " ".join(f"w{rng.randint(1, 99)}" for _ in range(rng.randint(3, 4)))


def _build(conn, rng):
    conn.execute(
        "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
        "VALUES ('p1', 'Book', 'fr', 'it', 'now', 'now')"
    )
    p1, _, p2 = create_document(conn, "p1", "source", "fr.txt", "txt", [
        NewBlock("paragraph", [_words(rng) for _ in range(5)]),
        NewBlock("footnote", [_words(rng)], excluded=True),
        NewBlock("paragraph", [_words(rng) for _ in range(4)]),
    ])
    q1, q2 = create_document(conn, "p1", "target", "it.txt", "txt", [
        NewBlock("paragraph", [_words(rng) for _ in range(4)]),
        NewBlock("paragraph", [_words(rng) for _ in range(5)]),
    ])
    append_beads(conn, "p1", [NewBead([s], [t], 0.5, "length") for s, t in zip(p1 + p2, q1 + q2)])


def _ids(conn, sql):
    return [r[0] for r in conn.execute(sql)]


def _segment_ids(conn):
    return _ids(conn, "SELECT s.id FROM segments s JOIN blocks b ON b.id = s.block_id "
                      "JOIN documents d ON d.id = b.document_id WHERE d.project_id = 'p1' ORDER BY s.id")


def _bead_ids(conn):
    return _ids(conn, "SELECT id FROM beads WHERE project_id = 'p1' ORDER BY ord")


def _block_ids(conn):
    return _ids(conn, "SELECT b.id FROM blocks b JOIN documents d ON d.id = b.document_id "
                      "WHERE d.project_id = 'p1' ORDER BY b.id")


def _cut(rng, items, k):
    """Cut `items` into `k` contiguous (possibly empty) parts at random points."""
    points = sorted(rng.randint(0, len(items)) for _ in range(k - 1))
    bounds = [0, *points, len(items)]
    return [items[bounds[i]:bounds[i + 1]] for i in range(k)]


def _pick(rng, conn):
    """Choose an operation and its arguments from the current database: (name, callable, args)."""
    name = rng.choice([
        "edit_text", "split_segment", "join_with_next", "move_first_to_previous", "move_last_to_next",
        "merge_with_next", "split_bead", "set_reviewed", "exclude_block", "include_block", "replace_beads",
        "undo", "redo",
    ])
    segments, beads, blocks = _segment_ids(conn), _bead_ids(conn), _block_ids(conn)
    if name == "undo":
        return name, lambda c: undo(c, "p1"), ()
    if name == "redo":
        return name, lambda c: redo(c, "p1"), ()
    if name == "edit_text":
        return name, edit_text, (rng.choice(segments), _words(rng))
    if name == "split_segment":
        seg = rng.choice(segments)
        text = conn.execute("SELECT text FROM segments WHERE id = ?", (seg,)).fetchone()[0]
        return name, split_segment, (seg, rng.randint(1, max(1, len(text) - 1)))
    if name == "join_with_next":
        return name, join_with_next, (rng.choice(segments),)
    if name in ("exclude_block", "include_block"):
        op = exclude_block if name == "exclude_block" else include_block
        return name, op, (rng.choice(blocks),)
    if not beads:
        return name, None, ()
    bead = rng.choice(beads)
    if name in ("move_first_to_previous", "move_last_to_next"):
        op = move_first_to_previous if name == "move_first_to_previous" else move_last_to_next
        return name, op, (bead, rng.choice(SIDES))
    if name == "merge_with_next":
        return name, merge_with_next, (bead,)
    if name == "split_bead":
        points = [rng.choice([None, *_segments(conn, bead, side)]) for side in SIDES]
        return name, split_bead, tuple([bead, *points])
    if name == "set_reviewed":
        flag = rng.random() < 0.5
        chosen = rng.sample(beads, rng.randint(1, min(3, len(beads))))
        return name, set_reviewed, (chosen, flag)
    # replace_beads
    start = beads.index(bead)
    run = beads[start:start + rng.randint(1, 3)]
    k = rng.randint(1, 3)
    parts = [_cut(rng, [s for b in run for s in _segments(conn, b, side)], k) for side in SIDES]
    new = [NewBead(src, tgt, rng.random(), "length") for src, tgt in zip(*parts) if src or tgt]
    return name, replace_beads, (run[0], run[-1], new)


@pytest.mark.parametrize("seed", range(SEED_COUNT))
def test_random_round_trip(tmp_path, seed):
    rng = random.Random(seed)
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with transaction(conn):
        _build(conn, rng)
    initial = snapshot(conn)
    assert check_project(conn, "p1") == []

    changed = 0
    for step in range(STEPS):
        name, op, args = _pick(rng, conn)
        where = f"seed {seed}, step {step}: {name}{args}"
        before, ops = snapshot(conn), _op_count(conn)
        if op is None:
            continue
        try:
            with transaction(conn):
                if name in ("undo", "redo"):
                    op(conn)
                else:
                    op(conn, "p1", *args)
        except DomainError:
            assert snapshot(conn) == before, where
            assert _op_count(conn) == ops, where
        if snapshot(conn) != before:
            changed += 1
        errors = check_project(conn, "p1")
        assert errors == [], f"{where}: {errors}"
        assert actual_index(conn) == expected_index(conn), f"{where}: bead index out of sync"

    assert changed >= 20, f"seed {seed}: only {changed} of {STEPS} steps changed something"

    with transaction(conn):
        while redo(conn, "p1") is not None:
            pass
    final = snapshot(conn)
    assert check_project(conn, "p1") == [], f"seed {seed}: after redoing all"

    with transaction(conn):
        while undo(conn, "p1") is not None:
            pass
    assert snapshot(conn) == initial, f"seed {seed}: undoing everything"

    with transaction(conn):
        while redo(conn, "p1") is not None:
            pass
    assert snapshot(conn) == final, f"seed {seed}: redoing everything"
    conn.close()
