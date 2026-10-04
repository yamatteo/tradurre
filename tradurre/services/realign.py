"""Re-align range (SPEC §3.3; PLAN.md, "Re-align range"): re-run the import's aligner on a stretch of beads.

Every bead of the stretch is replaced, reviewed or not, by the aligner's beads, which start unreviewed; one
operation, so one undo restores the old beads and their marks. Callers own the transaction (`history.transaction`).
"""

import sqlite3

from tradurre.domain.beads import _segments
from tradurre.domain.layer import NewBead
from tradurre.domain.replace import _run, replace_beads
from tradurre.services import align


def _texts(conn: sqlite3.Connection, segment_ids: list[int]) -> list[str]:
    texts = dict(conn.execute(
        f"SELECT id, text FROM segments WHERE id IN ({','.join('?' * len(segment_ids))})", segment_ids
    ).fetchall()) if segment_ids else {}
    return [texts[s] for s in segment_ids]


def realign(conn: sqlite3.Connection, project_id: str, first: int, last: int) -> list[int]:
    """Replace the beads from `first` to `last` with the aligner's beads for their segments; return the new ids."""
    run = _run(conn, project_id, first, last)
    source = [s for bead_id in run for s in _segments(conn, bead_id, "source")]
    target = [s for bead_id in run for s in _segments(conn, bead_id, "target")]
    beads = [
        NewBead([source[i] for i in bead.source], [target[j] for j in bead.target], bead.confidence, "length")
        for bead in align.align(_texts(conn, source), _texts(conn, target))
    ]
    return replace_beads(conn, project_id, first, last, beads, kind="realign")
