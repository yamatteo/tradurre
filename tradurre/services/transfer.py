"""Transfer a gold book's review marks and text edits onto a freshly imported copy of the same book.

`plan_transfer` reads the book and the gold and works out what would change, without writing; `apply_transfer`
writes it as one undoable operation (kind "transfer"). The two texts must match (without whitespace and hyphens).

Marks: a fresh turn (a run of beads ending at a turn end, see `domain/levels.py`) is marked at turn level when both
of its edges are gold bead boundaries (as (source, target) counts of the characters included on both sides, the
count `gold.score` uses), it holds at least one such character, and every gold bead inside it is reviewed.
Edits: a gold segment whose corrected text differs from its original is placed on the fresh segment covering exactly
the same characters of the side's stream. An edit that only changes whitespace or hyphens is a spacing fix: it is
counted (`spacing`, and `spacing_matched` when the fresh original already equals the corrected text) and never
applied, since the fresh extraction is the better source for spacing. Exclusions are only reported.
Plans hold counts and ids, never book text.
"""

import sqlite3
from bisect import bisect_right
from dataclasses import dataclass, field

from tradurre.domain.history import Recorder, record
from tradurre.domain.levels import level_rank, unit_ends
from tradurre.services.gold import _HYPHENS, _SPACE, SIDES, Layer, _boundaries, _chars, _check_same_text, _count, read_layer


@dataclass
class EditCounts:
    applied: list[tuple[int, int]] = field(default_factory=list)  # (fresh segment id, index of the gold segment)
    already: int = 0
    unplaced: list[int] = field(default_factory=list)  # indexes of the gold segments in the side
    spacing: int = 0  # gold edits that only change whitespace or hyphens: never applied
    spacing_matched: int = 0  # ... of which the fresh segment with the same span already has the corrected text


@dataclass
class Exclusions:
    gold_only: int = 0  # characters excluded in the gold, included in the fresh book
    fresh_only: int = 0  # ... the other way round
    blocks: list[int] = field(default_factory=list)  # fresh block ids holding such characters


@dataclass
class Plan:
    turns_total: int = 0
    turns_marked: int = 0
    beads_to_mark: list[int] = field(default_factory=list)  # bead ids to raise to turn level
    edits: dict[str, EditCounts] = field(default_factory=lambda: {side: EditCounts() for side in SIDES})
    exclusions: dict[str, Exclusions] = field(default_factory=lambda: {side: Exclusions() for side in SIDES})


def _fresh_rows(conn: sqlite3.Connection, book_id: str):
    """Per side, the fresh segments (id, text, original, block id) and the book's bead ids, in `read_layer` order."""
    rows: dict[str, list[tuple[int, str, str, int]]] = {side: [] for side in SIDES}
    for r in conn.execute(
        """
        SELECT d.side, s.id, s.text, s.original_text, b.id AS block_id
        FROM segments s JOIN blocks b ON b.id = s.block_id JOIN documents d ON d.id = b.document_id
        WHERE d.project_id = ? ORDER BY d.side, b.ord, s.ord
        """,
        (book_id,),
    ):
        rows[r["side"]].append((r["id"], r["text"], r["original_text"], r["block_id"]))
    beads = [r["id"] for r in conn.execute("SELECT id FROM beads WHERE project_id = ? ORDER BY ord", (book_id,))]
    return rows, beads


def plan_transfer(conn: sqlite3.Connection, book_id: str, gold: Layer) -> Plan:
    """What transferring `gold` onto the book would change. Raises ValueError if the texts differ."""
    fresh = read_layer(conn, book_id)
    _check_same_text(gold, fresh)
    rows, bead_ids = _fresh_rows(conn, book_id)
    plan = Plan()

    common_gold: dict[str, list[int]] = {}
    common_fresh: dict[str, list[int]] = {}
    for side in SIDES:
        _, gold_beads = _chars(gold.side(side))
        _, fresh_beads = _chars(fresh.side(side))
        both = [(g, f) for g, f in zip(gold_beads, fresh_beads) if g is not None and f is not None]
        common_gold[side] = [g for g, _ in both]
        common_fresh[side] = [f for _, f in both]
        blocks = [b for (_, _, _, b), (text, _) in zip(rows[side], fresh.side(side)) for _ in range(_count(text))]
        ex = plan.exclusions[side]
        affected = set()
        for g, f, block in zip(gold_beads, fresh_beads, blocks):
            if g is None and f is not None:
                ex.gold_only += 1
                affected.add(block)
            elif g is not None and f is None:
                ex.fresh_only += 1
                affected.add(block)
        ex.blocks = sorted(affected)

    # Marks.
    gold_ends = _boundaries(common_gold, len(gold.reviewed))
    gold_set = {(0, 0)} | set(gold_ends)
    # Gold beads with common characters: their end and whether they are reviewed (ends strictly increase).
    ends: list[tuple[int, int]] = []
    unreviewed = [0]
    previous = (0, 0)
    for end, reviewed in zip(gold_ends, gold.reviewed):
        if end != previous:
            ends.append(end)
            unreviewed.append(unreviewed[-1] + (not reviewed))
            previous = end
    fresh_ends = _boundaries(common_fresh, len(bead_ids))
    turn_end = unit_ends(conn, book_id)
    start = 0
    for k, bead_id in enumerate(bead_ids):
        if not turn_end[bead_id][0] and k != len(bead_ids) - 1:
            continue
        plan.turns_total += 1
        edge_before = (0, 0) if start == 0 else fresh_ends[start - 1]
        edge_after = fresh_ends[k]
        if edge_before in gold_set and edge_after in gold_set and edge_before != edge_after:
            lo, hi = bisect_right(ends, edge_before), bisect_right(ends, edge_after)
            if unreviewed[hi] - unreviewed[lo] == 0:
                plan.turns_marked += 1
                plan.beads_to_mark.extend(bead_ids[start:k + 1])
        start = k + 1

    # Edits.
    if gold.corrected is not None:
        for side in SIDES:
            counts = plan.edits[side]
            spans: dict[tuple[int, int], tuple[int, str, str]] = {}
            offset = 0
            for seg_id, text, original, _ in rows[side]:
                size = _count(original)
                if size:
                    spans[(offset, offset + size)] = (seg_id, text, original)
                offset += size
            offset = 0
            for index, ((original, _), corrected) in enumerate(zip(gold.side(side), gold.corrected[side])):
                size = _count(original)
                span = (offset, offset + size)
                offset += size
                if corrected == original:
                    continue
                found = spans.get(span) if size else None
                if _SPACE.sub("", corrected).translate(_HYPHENS) == _SPACE.sub("", original).translate(_HYPHENS):
                    counts.spacing += 1
                    if found is not None and found[2] == corrected:
                        counts.spacing_matched += 1
                    continue
                if not corrected.strip() or found is None:
                    counts.unplaced.append(index)
                elif found[2] == corrected:
                    counts.already += 1
                elif found[1] == original:
                    counts.applied.append((found[0], index))
                else:
                    counts.unplaced.append(index)
    return plan


def has_work_done(conn: sqlite3.Connection, book_id: str) -> bool:
    """Whether the book has review marks or text edits."""
    marked = conn.execute("SELECT 1 FROM beads WHERE project_id = ? AND review_level > 0 LIMIT 1", (book_id,)).fetchone()
    edited = conn.execute(
        """
        SELECT 1 FROM segments s JOIN blocks b ON b.id = s.block_id JOIN documents d ON d.id = b.document_id
        WHERE d.project_id = ? AND s.text != s.original_text LIMIT 1
        """,
        (book_id,),
    ).fetchone()
    return marked is not None or edited is not None


def apply_transfer(conn: sqlite3.Connection, book_id: str, plan: Plan, gold: Layer) -> int | None:
    """Write the plan as one operation ("transfer"); return its id (None if nothing changes). The caller owns the
    transaction (`with transaction(conn):`). Refuses a book that already has marks or edits."""
    if has_work_done(conn, book_id):
        raise ValueError("the book already has review marks or edits: a transfer is for fresh imports only")
    rec = Recorder(conn)
    rank = level_rank("turn")
    for bead_id in plan.beads_to_mark:
        current = conn.execute("SELECT review_level FROM beads WHERE id = ?", (bead_id,)).fetchone()[0]
        if current < rank:
            rec.update("beads", bead_id, review_level=rank)
    for side in SIDES:
        for seg_id, index in plan.edits[side].applied:
            rec.update("segments", seg_id, text=gold.corrected[side][index])
    return record(conn, book_id, "transfer", rec)
