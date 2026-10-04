"""Block exclude/include (SPEC §2, §3.3; PLAN.md, "Domain operations").

Excluding never deletes text: the block's segments only leave the alignment. Exclude and include are text-layer
decisions, so they never change an existing bead's method, confidence or reviewed flag. Callers own the
transaction (`history.transaction`).
"""

import sqlite3
from typing import Literal

from tradurre.domain import DomainError
from tradurre.domain.beads import _check_bead, _check_side, _is_empty
from tradurre.domain.history import Recorder, record
from tradurre.domain.ordering import ord_after

# The bead of the nearest segment of a non-excluded block before (or after) a block, on the same side.
_NEIGHBOUR_BEAD = """
SELECT s.bead_id
FROM segments s
JOIN blocks b ON b.id = s.block_id
WHERE b.document_id = ? AND b.excluded = 0 AND b.ord {cmp} ?
ORDER BY b.ord {order}, s.ord {order}
LIMIT 1
"""


def _block(conn: sqlite3.Connection, project_id: str, block_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT b.id, b.document_id, b.ord, b.excluded, d.project_id "
        "FROM blocks b JOIN documents d ON d.id = b.document_id WHERE b.id = ?",
        (block_id,),
    ).fetchone()
    if row is None or row["project_id"] != project_id:
        raise DomainError(f"Block {block_id} is not in this project")
    return row


def _block_segments(conn: sqlite3.Connection, block_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, bead_id FROM segments WHERE block_id = ? ORDER BY ord", (block_id,)).fetchall()


def _exclude(rec: Recorder, conn: sqlite3.Connection, block: sqlite3.Row) -> None:
    """Exclude one non-excluded block into `rec`; beads left empty are deleted."""
    block_id = block["id"]
    rec.update("blocks", block_id, excluded=1)
    touched: list[int] = []
    for seg in _block_segments(conn, block_id):
        rec.update("segments", seg["id"], bead_id=None)
        if seg["bead_id"] not in touched:
            touched.append(seg["bead_id"])
    for bead_id in touched:
        if _is_empty(conn, bead_id):
            rec.delete("beads", bead_id)


def _include(rec: Recorder, conn: sqlite3.Connection, project_id: str, block: sqlite3.Row) -> None:
    """Include one excluded block into `rec`, inside the surrounding bead or as a new unmatched bead."""
    block_id = block["id"]
    rec.update("blocks", block_id, excluded=0)
    segments = _block_segments(conn, block_id)
    if segments:
        args = (block["document_id"], block["ord"])
        p = conn.execute(_NEIGHBOUR_BEAD.format(cmp="<", order="DESC"), args).fetchone()
        n = conn.execute(_NEIGHBOUR_BEAD.format(cmp=">", order="ASC"), args).fetchone()
        p_bead = None if p is None else p[0]
        if p is not None and n is not None and p_bead == n[0]:
            bead_id = p_bead
        else:
            bead_id = rec.insert("beads", {
                "project_id": project_id,
                "ord": ord_after(rec, "beads", project_id, p_bead),
                "confidence": 0.0,
                "method": "manual",
                "reviewed": 0,
            })
        for seg in segments:
            rec.update("segments", seg["id"], bead_id=bead_id)


def exclude_block(conn: sqlite3.Connection, project_id: str, block_id: int) -> int:
    """Take the block out of the alignment; beads left empty are deleted."""
    block = _block(conn, project_id, block_id)
    if block["excluded"]:
        raise DomainError("The block is already excluded")
    rec = Recorder(conn)
    _exclude(rec, conn, block)
    return record(conn, project_id, "exclude_block", rec)


def include_block(conn: sqlite3.Connection, project_id: str, block_id: int) -> int:
    """Put the block back into the alignment, inside the surrounding bead or as a new unmatched bead."""
    block = _block(conn, project_id, block_id)
    if not block["excluded"]:
        raise DomainError("The block is not excluded")
    rec = Recorder(conn)
    _include(rec, conn, project_id, block)
    return record(conn, project_id, "include_block", rec)


# Layout kinds: a range include leaves them out; only a single-block include brings one back (PLAN.md, "Range
# exclude/include").
_LAYOUT_KINDS = ("running_head", "page_number", "footnote")


def _range_blocks(
    conn: sqlite3.Connection, project_id: str, bead_id: int, side: str, to: Literal["start", "end"], excluded: int
) -> list[sqlite3.Row]:
    """The blocks of the bead's `side` document from its start up to the block of the bead's last segment on that
    side (`to="start"`), or from the block of its first segment to the end (`to="end"`), with that `excluded` flag,
    in document order. A block straddling the bead is in the range: blocks are the unit."""
    _check_bead(conn, project_id, bead_id)
    _check_side(side)
    if to not in ("start", "end"):
        raise ValueError(f"to must be 'start' or 'end', not {to!r}")
    ords = conn.execute(
        "SELECT b.document_id, b.ord FROM segments s JOIN blocks b ON b.id = s.block_id "
        "JOIN documents d ON d.id = b.document_id WHERE s.bead_id = ? AND d.side = ? ORDER BY b.ord, s.ord",
        (bead_id, side),
    ).fetchall()
    if not ords:
        raise DomainError(f"The bead has no {side} segment")
    document_id, bound = (ords[-1] if to == "start" else ords[0])
    cmp = "<=" if to == "start" else ">="
    return conn.execute(
        f"SELECT id, document_id, ord, excluded, kind FROM blocks "
        f"WHERE document_id = ? AND ord {cmp} ? AND excluded = ? ORDER BY ord",
        (document_id, bound, excluded),
    ).fetchall()


def exclude_range(
    conn: sqlite3.Connection, project_id: str, bead_id: int, side: str, to: Literal["start", "end"]
) -> int:
    """Exclude every block of one side from the start of the edition up to the bead, or from it to the end:
    one operation, so one undo. Returns the operation id."""
    blocks = _range_blocks(conn, project_id, bead_id, side, to, excluded=0)
    if not blocks:
        raise DomainError("Nothing to exclude")
    rec = Recorder(conn)
    for block in blocks:
        _exclude(rec, conn, block)
    return record(conn, project_id, "exclude_range", rec)


def include_range(
    conn: sqlite3.Connection, project_id: str, bead_id: int, side: str, to: Literal["start", "end"]
) -> int:
    """Include every excluded block of one side in that range, except the layout kinds (running heads, page
    numbers, footnotes): one operation, so one undo. Returns the operation id."""
    blocks = [
        b for b in _range_blocks(conn, project_id, bead_id, side, to, excluded=1) if b["kind"] not in _LAYOUT_KINDS
    ]
    if not blocks:
        raise DomainError("Nothing to include")
    rec = Recorder(conn)
    for block in blocks:
        _include(rec, conn, project_id, block)
    return record(conn, project_id, "include_range", rec)
