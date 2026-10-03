"""Sparse integer ordering of sibling rows (PLAN.md, "Domain operations").

New rows take the midpoint between their neighbours; when no integer fits, the siblings are renumbered
through the Recorder, so the renumbering is undone with the operation.
"""

from tradurre.domain.history import Recorder
from tradurre.domain.layer import GAP

# The only tables that get new rows, and the column that groups siblings.
_PARENT = {"beads": "project_id", "segments": "block_id"}


def _parent_col(table: str) -> str:
    if table not in _PARENT:
        raise ValueError(f"No ordering for table {table!r}")
    return _PARENT[table]


def ord_after(rec: Recorder, table: str, parent_id, after_id: int | None) -> int:
    """An ord for a new row right after sibling `after_id` (None = before every sibling)."""
    parent_col = _parent_col(table)
    result = _midpoint(rec, table, parent_col, parent_id, after_id)
    if result is None:
        renumber(rec, table, parent_id)
        result = _midpoint(rec, table, parent_col, parent_id, after_id)
        assert result is not None
    return result


def _midpoint(rec: Recorder, table: str, parent_col: str, parent_id, after_id: int | None) -> int | None:
    """The ord per the midpoint rule, or None if there is no room."""
    conn = rec.conn
    if after_id is None:
        prev = None
    else:
        row = conn.execute(f"SELECT {parent_col}, ord FROM {table} WHERE id = ?", (after_id,)).fetchone()
        if row is None or row[0] != parent_id:
            raise ValueError(f"{table} {after_id} is not a sibling under {parent_col} = {parent_id!r}")
        prev = row[1]
    next_ = conn.execute(
        f"SELECT MIN(ord) FROM {table} WHERE {parent_col} = ? AND ord > ?",
        (parent_id, -1 if prev is None else prev),
    ).fetchone()[0]

    if prev is None and next_ is None:
        return 0
    if next_ is None:
        result = prev + GAP
    elif prev is None:
        result = next_ // 2
    else:
        result = (prev + next_) // 2
    if result == prev or result == next_:
        return None
    return result


def renumber(rec: Recorder, table: str, parent_id) -> None:
    """Respace the siblings to GAP, 2·GAP, … (room before the first), in two collision-free passes."""
    parent_col = _parent_col(table)
    ids = [r[0] for r in rec.conn.execute(
        f"SELECT id FROM {table} WHERE {parent_col} = ? ORDER BY ord", (parent_id,)
    )]
    for i, row_id in enumerate(ids):
        rec.update(table, row_id, ord=-(i + 1))
    for i, row_id in enumerate(ids):
        rec.update(table, row_id, ord=(i + 1) * GAP)
