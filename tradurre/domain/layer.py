"""Building a project's text and alignment layers in bulk (import, tests).

These are plain inserts: not recorded in the operation log and not undoable.
They don't commit; the caller owns the transaction.
"""

import sqlite3
from dataclasses import dataclass

GAP = 1024


@dataclass
class NewBlock:
    kind: str
    segments: list[str]
    excluded: bool = False
    page: int | None = None


@dataclass
class NewBead:
    source: list[int]  # segment ids
    target: list[int]  # segment ids
    confidence: float
    method: str


def create_document(
    conn: sqlite3.Connection,
    project_id: str,
    side: str,
    filename: str,
    format: str,
    blocks: list[NewBlock],
) -> list[list[int]]:
    """Insert a document with its blocks and segments; return the segment ids per block."""
    document_id = conn.execute(
        "INSERT INTO documents (project_id, side, filename, format) VALUES (?, ?, ?, ?)",
        (project_id, side, filename, format),
    ).lastrowid
    segment_ids: list[list[int]] = []
    for i, block in enumerate(blocks):
        block_id = conn.execute(
            "INSERT INTO blocks (document_id, ord, kind, excluded, page) VALUES (?, ?, ?, ?, ?)",
            (document_id, i * GAP, block.kind, int(block.excluded), block.page),
        ).lastrowid
        ids = []
        for j, text in enumerate(block.segments):
            ids.append(conn.execute(
                "INSERT INTO segments (block_id, ord, text, original_text) VALUES (?, ?, ?, ?)",
                (block_id, j * GAP, text, text),
            ).lastrowid)
        segment_ids.append(ids)
    return segment_ids


def append_beads(conn: sqlite3.Connection, project_id: str, beads: list[NewBead]) -> list[int]:
    """Insert beads after the project's last bead and point their segments at them; return the bead ids."""
    last = conn.execute("SELECT MAX(ord) FROM beads WHERE project_id = ?", (project_id,)).fetchone()[0]
    next_ord = 0 if last is None else last + GAP
    bead_ids = []
    for bead in beads:
        bead_id = conn.execute(
            "INSERT INTO beads (project_id, ord, confidence, method, reviewed) VALUES (?, ?, ?, ?, 0)",
            (project_id, next_ord, bead.confidence, bead.method),
        ).lastrowid
        conn.executemany(
            "UPDATE segments SET bead_id = ? WHERE id = ?",
            [(bead_id, seg_id) for seg_id in bead.source + bead.target],
        )
        bead_ids.append(bead_id)
        next_ord += GAP
    return bead_ids
