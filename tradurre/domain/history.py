"""Operation log with generic undo/redo by row snapshots (PLAN.md, "Domain operations").

Every write an operation makes goes through a `Recorder`, which stores, per touched row,
`[table, id, before, after]` (`before` is None for an insert, `after` None for a delete). `record`
saves the change list in the `operations` table; `undo` applies the `before`s, `redo` the `after`s.
Rows keep their ids across undo/redo, and history is linear: recording a new operation drops the
project's undone ones.

None of these functions commit. The caller owns the transaction and must start it with
`BEGIN IMMEDIATE` followed by `PRAGMA defer_foreign_keys = ON`, because undo/redo may briefly break a
foreign key (e.g. re-inserting a bead after re-pointing segments at it) and only the end state is valid.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

TABLES = {"blocks", "segments", "beads"}
# Deleting a block (or document) cascades to its segments outside the Recorder, so only these may be
# inserted or deleted.
_INSERT_DELETE_TABLES = {"segments", "beads"}

Row = dict[str, Any]
Change = list  # [table, id, before: Row | None, after: Row | None]


def _check_table(table: str, insert_delete: bool = False) -> None:
    allowed = _INSERT_DELETE_TABLES if insert_delete else TABLES
    if table not in allowed:
        raise ValueError(f"Recorder can't {'insert into or delete from' if insert_delete else 'touch'} {table!r}")


def _read_row(conn: sqlite3.Connection, table: str, row_id: int) -> Row | None:
    cur = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    row = cur.fetchone()
    if row is None:
        return None
    return {col[0]: value for col, value in zip(cur.description, row)}


class Recorder:
    """Performs writes on the domain tables and records each row's before/after."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.changes: list[Change] = []

    def insert(self, table: str, values: dict[str, Any]) -> int:
        _check_table(table, insert_delete=True)
        cols = ", ".join(values)
        marks = ", ".join("?" * len(values))
        row_id = self.conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values())
        ).lastrowid
        self.changes.append([table, row_id, None, _read_row(self.conn, table, row_id)])
        return row_id

    def update(self, table: str, row_id: int, **fields: Any) -> None:
        _check_table(table)
        before = _read_row(self.conn, table, row_id)
        if before is None:
            raise ValueError(f"No row {row_id} in {table}")
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?", [*fields.values(), row_id])
        self.changes.append([table, row_id, before, _read_row(self.conn, table, row_id)])

    def delete(self, table: str, row_id: int) -> None:
        _check_table(table, insert_delete=True)
        before = _read_row(self.conn, table, row_id)
        if before is None:
            raise ValueError(f"No row {row_id} in {table}")
        self.conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
        self.changes.append([table, row_id, before, None])


def record(
    conn: sqlite3.Connection, project_id: str, kind: str, rec: Recorder, coalesce: bool = False
) -> int | None:
    """Save the recorder's changes as an operation; return its id (None if there were no changes).

    With `coalesce`, the changes are appended to the project's latest operation when it has the same
    kind and isn't undone.
    """
    if not rec.changes:
        return None
    conn.execute("DELETE FROM operations WHERE project_id = ? AND undone = 1", (project_id,))
    if coalesce:
        latest = conn.execute(
            "SELECT id, kind, changes, undone FROM operations WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        if latest is not None and latest[1] == kind and latest[3] == 0:
            changes = json.loads(latest[2]) + rec.changes
            conn.execute("UPDATE operations SET changes = ? WHERE id = ?", (json.dumps(changes), latest[0]))
            return latest[0]
    return conn.execute(
        "INSERT INTO operations (project_id, kind, changes, created_at) VALUES (?, ?, ?, ?)",
        (project_id, kind, json.dumps(rec.changes), datetime.now(timezone.utc).isoformat()),
    ).lastrowid


def undo(conn: sqlite3.Connection, project_id: str) -> int | None:
    """Revert the project's latest not-undone operation; return its id, or None if there is none."""
    op = conn.execute(
        "SELECT id, changes FROM operations WHERE project_id = ? AND undone = 0 ORDER BY id DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if op is None:
        return None
    _apply(conn, json.loads(op[1]), redo=False)
    conn.execute("UPDATE operations SET undone = 1 WHERE id = ?", (op[0],))
    return op[0]


def redo(conn: sqlite3.Connection, project_id: str) -> int | None:
    """Re-apply the project's earliest undone operation; return its id, or None if there is none."""
    op = conn.execute(
        "SELECT id, changes FROM operations WHERE project_id = ? AND undone = 1 ORDER BY id LIMIT 1",
        (project_id,),
    ).fetchone()
    if op is None:
        return None
    _apply(conn, json.loads(op[1]), redo=True)
    conn.execute("UPDATE operations SET undone = 0 WHERE id = ?", (op[0],))
    return op[0]


def _apply(conn: sqlite3.Connection, changes: list[Change], redo: bool) -> None:
    """Bring every row the change list touched to its target state (last `after` or first `before`).

    Four steps keep every UNIQUE (parent, ord) satisfied: (1) updated rows whose ord changes are parked
    at ord = -id; (2) deletes; (3) updates to the target values; (4) inserts with their old ids.
    """
    targets: dict[tuple[str, int], Row | None] = {}
    for table, row_id, before, after in changes:
        key = (table, row_id)
        if redo:
            targets[key] = after  # the last after wins
        elif key not in targets:
            targets[key] = before  # the first before wins

    deletes, updates, inserts = [], [], []
    for (table, row_id), target in targets.items():
        current = _read_row(conn, table, row_id)
        if target is None and current is not None:
            deletes.append((table, row_id))
        elif target is not None and current is None:
            inserts.append((table, target))
        elif target is not None and current is not None:
            updates.append((table, row_id, current, target))

    for table, row_id, current, target in updates:  # (1)
        if "ord" in target and target["ord"] != current["ord"]:
            conn.execute(f"UPDATE {table} SET ord = ? WHERE id = ?", (-row_id, row_id))
    for table, row_id in deletes:  # (2)
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
    for table, row_id, _, target in updates:  # (3)
        cols = [c for c in target if c != "id"]
        conn.execute(
            f"UPDATE {table} SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?",
            [*(target[c] for c in cols), row_id],
        )
    for table, target in inserts:  # (4)
        conn.execute(
            f"INSERT INTO {table} ({', '.join(target)}) VALUES ({', '.join('?' * len(target))})",
            list(target.values()),
        )
