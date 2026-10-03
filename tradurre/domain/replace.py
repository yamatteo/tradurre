"""Replacing a run of beads in bulk (PLAN.md, "Domain operations").

The primitive behind re-align range and loading a Colab alignment. The new beads must cover exactly the segments
the old ones covered, in order; which runs may be replaced (e.g. only unreviewed ones) is the caller's rule.
Callers own the transaction (`history.transaction`): the run's beads are deleted before their segments are
re-pointed, which relies on deferred foreign keys.
"""

import sqlite3

from tradurre.domain import DomainError
from tradurre.domain.beads import SIDES, _previous, _segments
from tradurre.domain.history import Recorder, record
from tradurre.domain.layer import NewBead
from tradurre.domain.ordering import ords_after

METHODS = ("anchor", "length", "embedding", "llm", "manual")

_PROJECT_SEGMENTS = """
SELECT s.id
FROM segments s
JOIN blocks b ON b.id = s.block_id
JOIN documents d ON d.id = b.document_id
WHERE d.project_id = ? AND d.side = ? AND b.excluded = 0
ORDER BY b.ord, s.ord
"""


def _bead_ord(conn: sqlite3.Connection, project_id: str, bead_id: int) -> int:
    row = conn.execute("SELECT project_id, ord FROM beads WHERE id = ?", (bead_id,)).fetchone()
    if row is None or row[0] != project_id:
        raise DomainError(f"Bead {bead_id} is not in this project")
    return row[1]


def _run(conn: sqlite3.Connection, project_id: str, first: int | None, last: int | None) -> list[int]:
    """The ids of the beads from `first` to `last` inclusive, in ord order (empty for None/None)."""
    if first is None and last is None:
        if conn.execute("SELECT 1 FROM beads WHERE project_id = ? LIMIT 1", (project_id,)).fetchone():
            raise DomainError("The project already has beads; say which ones to replace")
        return []
    if first is None or last is None:
        raise DomainError("Give both the first and the last bead to replace")
    lo, hi = _bead_ord(conn, project_id, first), _bead_ord(conn, project_id, last)
    if lo > hi:
        raise DomainError("The first bead comes after the last one")
    return [r[0] for r in conn.execute(
        "SELECT id FROM beads WHERE project_id = ? AND ord BETWEEN ? AND ? ORDER BY ord", (project_id, lo, hi)
    )]


def _replace(rec: Recorder, project_id: str, first: int | None, last: int | None, beads: list[NewBead]) -> list[int]:
    """Validate, then replace the run from `first` to `last` with `beads`; return the new bead ids."""
    conn = rec.conn
    for bead in beads:
        if not 0 <= bead.confidence <= 1:
            raise ValueError(f"confidence {bead.confidence} is outside [0, 1]")
        if bead.method not in METHODS:
            raise ValueError(f"Unknown method {bead.method!r}")
    run = _run(conn, project_id, first, last)
    for bead in beads:
        if not bead.source and not bead.target:
            raise DomainError("A bead needs at least one segment")
    for side in SIDES:
        if run:
            old = [seg for bead_id in run for seg in _segments(conn, bead_id, side)]
        else:
            old = [r[0] for r in conn.execute(_PROJECT_SEGMENTS, (project_id, side))]
        new = [seg for bead in beads for seg in getattr(bead, side)]
        if new != old:
            raise DomainError(f"The new beads must cover exactly the same {side} segments, in order")

    before = _previous(conn, run[0]) if run else None
    for bead_id in run:
        rec.delete("beads", bead_id)
    if not beads:
        return []
    ids = []
    for bead, ord_ in zip(beads, ords_after(rec, "beads", project_id, before, len(beads))):
        bead_id = rec.insert("beads", {
            "project_id": project_id,
            "ord": ord_,
            "confidence": bead.confidence,
            "method": bead.method,
            "reviewed": 0,
        })
        for seg_id in bead.source + bead.target:
            rec.update("segments", seg_id, bead_id=bead_id)
        ids.append(bead_id)
    return ids


def replace_beads(
    conn: sqlite3.Connection,
    project_id: str,
    first: int | None,
    last: int | None,
    beads: list[NewBead],
    kind: str = "replace_beads",
) -> list[int]:
    """Replace the beads from `first` to `last` (None/None: a project with no beads) as one operation."""
    rec = Recorder(conn)
    ids = _replace(rec, project_id, first, last, beads)
    record(conn, project_id, kind, rec)
    return ids
