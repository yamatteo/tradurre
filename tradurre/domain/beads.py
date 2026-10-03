"""Bead corrections (SPEC §3.3; PLAN.md, "Domain operations").

Each operation writes through one Recorder and records one operation; a refused operation raises
`DomainError` before writing anything. Callers own the transaction (`history.transaction`).
"""

import sqlite3

from tradurre.domain import DomainError
from tradurre.domain.history import Recorder, record
from tradurre.domain.ordering import ord_after

SIDES = ("source", "target")

_BEAD_SEGMENTS = """
SELECT s.id
FROM segments s
JOIN blocks b ON b.id = s.block_id
JOIN documents d ON d.id = b.document_id
WHERE s.bead_id = ? AND d.side = ?
ORDER BY b.ord, s.ord
"""


def _segments(conn: sqlite3.Connection, bead_id: int, side: str) -> list[int]:
    """The bead's segment ids on one side, in document order."""
    return [r[0] for r in conn.execute(_BEAD_SEGMENTS, (bead_id, side))]


def _neighbour(conn: sqlite3.Connection, bead_id: int, after: bool) -> int | None:
    cmp, order = (">", "ASC") if after else ("<", "DESC")
    row = conn.execute(
        f"SELECT n.id FROM beads b JOIN beads n ON n.project_id = b.project_id AND n.ord {cmp} b.ord "
        f"WHERE b.id = ? ORDER BY n.ord {order} LIMIT 1",
        (bead_id,),
    ).fetchone()
    return None if row is None else row[0]


def _previous(conn: sqlite3.Connection, bead_id: int) -> int | None:
    """The bead right before this one in its project, or None."""
    return _neighbour(conn, bead_id, after=False)


def _next(conn: sqlite3.Connection, bead_id: int) -> int | None:
    """The bead right after this one in its project, or None."""
    return _neighbour(conn, bead_id, after=True)


def _corrected(rec: Recorder, bead_id: int) -> None:
    rec.update("beads", bead_id, method="manual", confidence=1.0)


def _reviewed(conn: sqlite3.Connection, bead_id: int) -> int:
    return conn.execute("SELECT reviewed FROM beads WHERE id = ?", (bead_id,)).fetchone()[0]


def _is_empty(conn: sqlite3.Connection, bead_id: int) -> bool:
    return conn.execute("SELECT 1 FROM segments WHERE bead_id = ? LIMIT 1", (bead_id,)).fetchone() is None


def _check_bead(conn: sqlite3.Connection, project_id: str, bead_id: int) -> None:
    row = conn.execute("SELECT project_id FROM beads WHERE id = ?", (bead_id,)).fetchone()
    if row is None or row[0] != project_id:
        raise DomainError(f"Bead {bead_id} is not in this project")


def _check_side(side: str) -> None:
    if side not in SIDES:
        raise ValueError(f"side must be 'source' or 'target', not {side!r}")


def _move(conn: sqlite3.Connection, project_id: str, bead_id: int, side: str, to_next: bool) -> int:
    _check_bead(conn, project_id, bead_id)
    _check_side(side)
    other = _next(conn, bead_id) if to_next else _previous(conn, bead_id)
    if other is None:
        raise DomainError(f"There is no {'next' if to_next else 'previous'} bead")
    segments = _segments(conn, bead_id, side)
    if not segments:
        raise DomainError(f"The bead has no {side} segment to move")

    rec = Recorder(conn)
    rec.update("segments", segments[-1] if to_next else segments[0], bead_id=other)
    _corrected(rec, other)
    if _is_empty(conn, bead_id):
        rec.delete("beads", bead_id)
    else:
        _corrected(rec, bead_id)
    return record(conn, project_id, "move_segment", rec)


def move_first_to_previous(conn: sqlite3.Connection, project_id: str, bead_id: int, side: str) -> int:
    """Move the bead's first segment on `side` to the previous bead."""
    return _move(conn, project_id, bead_id, side, to_next=False)


def move_last_to_next(conn: sqlite3.Connection, project_id: str, bead_id: int, side: str) -> int:
    """Move the bead's last segment on `side` to the next bead."""
    return _move(conn, project_id, bead_id, side, to_next=True)


def _merge(rec: Recorder, bead_id: int, next_id: int) -> None:
    """Move `next_id`'s segments into `bead_id` and delete `next_id`; reviewed only if both were."""
    conn = rec.conn
    reviewed = _reviewed(conn, bead_id) and _reviewed(conn, next_id)
    for side in SIDES:
        for seg_id in _segments(conn, next_id, side):
            rec.update("segments", seg_id, bead_id=bead_id)
    rec.delete("beads", next_id)
    rec.update("beads", bead_id, method="manual", confidence=1.0, reviewed=reviewed)


def merge_with_next(conn: sqlite3.Connection, project_id: str, bead_id: int) -> int:
    """Merge the next bead into this one."""
    _check_bead(conn, project_id, bead_id)
    next_id = _next(conn, bead_id)
    if next_id is None:
        raise DomainError("There is no next bead to merge with")
    rec = Recorder(conn)
    _merge(rec, bead_id, next_id)
    return record(conn, project_id, "merge", rec)


def split_bead(
    conn: sqlite3.Connection, project_id: str, bead_id: int, source_at: int | None, target_at: int | None
) -> int:
    """Move each side's segments from `*_at` onward to a new bead right after this one; return its id."""
    _check_bead(conn, project_id, bead_id)
    if source_at is None and target_at is None:
        raise DomainError("Choose where to split the bead")
    moving: list[int] = []
    staying = 0
    for side, at in (("source", source_at), ("target", target_at)):
        segments = _segments(conn, bead_id, side)
        if at is None:
            staying += len(segments)
            continue
        if at not in segments:
            raise DomainError(f"Segment {at} is not a {side} segment of this bead")
        i = segments.index(at)
        staying += i
        moving += segments[i:]
    if not staying:
        raise DomainError("The split would leave the bead empty")

    rec = Recorder(conn)
    new_id = rec.insert("beads", {
        "project_id": project_id,
        "ord": ord_after(rec, "beads", project_id, bead_id),
        "confidence": 1.0,
        "method": "manual",
        "reviewed": _reviewed(conn, bead_id),
    })
    for seg_id in moving:
        rec.update("segments", seg_id, bead_id=new_id)
    _corrected(rec, bead_id)
    record(conn, project_id, "split", rec)
    return new_id


def set_reviewed(
    conn: sqlite3.Connection, project_id: str, bead_ids: list[int], reviewed: bool, skim: bool = False
) -> int | None:
    """Set the reviewed flag on the beads; skim marks coalesce into one operation."""
    if skim and not reviewed:
        raise ValueError("Skim review only sets the reviewed flag")
    for bead_id in bead_ids:
        _check_bead(conn, project_id, bead_id)
    rec = Recorder(conn)
    for bead_id in bead_ids:
        if _reviewed(conn, bead_id) != int(reviewed):
            rec.update("beads", bead_id, reviewed=int(reviewed))
    if skim:
        return record(conn, project_id, "skim_review", rec, coalesce=True)
    return record(conn, project_id, "review", rec)
