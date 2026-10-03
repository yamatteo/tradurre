"""Checker for the alignment invariants of a project (PLAN.md, "Domain operations").

I1  a segment has a bead iff its block is not excluded
I2  a bead and the segments pointing at it belong to the same project
I3  every bead has at least one segment
I4  on each side, bead ords read along non-excluded segments in document order never decrease
    (contiguity and monotonicity together)
I5  no negative ord
"""

import sqlite3

_SIDE_SEGMENTS = """
SELECT s.id, s.bead_id, b.excluded, bd.ord AS bead_ord
FROM segments s
JOIN blocks b ON b.id = s.block_id
JOIN documents d ON d.id = b.document_id
LEFT JOIN beads bd ON bd.id = s.bead_id
WHERE d.project_id = ? AND d.side = ?
ORDER BY b.ord, s.ord
"""


def check_project(conn: sqlite3.Connection, project_id: str) -> list[str]:
    """Return one message per violation, each starting with its code; empty = valid."""
    errors: list[str] = []

    for side in ("source", "target"):
        prev = None  # (segment id, bead ord) of the previous non-excluded segment with a bead
        for seg_id, bead_id, excluded, bead_ord in conn.execute(_SIDE_SEGMENTS, (project_id, side)):
            # I1
            if excluded and bead_id is not None:
                errors.append(f"I1: segment {seg_id} ({side}) is in an excluded block but has bead {bead_id}")
            elif not excluded and bead_id is None:
                errors.append(f"I1: segment {seg_id} ({side}) is in an included block but has no bead")
            # I4
            if excluded or bead_ord is None:
                continue
            if prev is not None and bead_ord < prev[1]:
                errors.append(
                    f"I4: segment {seg_id} ({side}) is in a bead (ord {bead_ord}) before the bead of "
                    f"the previous segment {prev[0]} (ord {prev[1]})"
                )
            prev = (seg_id, bead_ord)

    # I2: segments of this project pointing at another project's bead, and vice versa
    for seg_id, bead_id, bead_project in conn.execute(
        """
        SELECT s.id, s.bead_id, bd.project_id
        FROM segments s
        JOIN blocks b ON b.id = s.block_id
        JOIN documents d ON d.id = b.document_id
        JOIN beads bd ON bd.id = s.bead_id
        WHERE (d.project_id = ? AND bd.project_id != ?) OR (d.project_id != ? AND bd.project_id = ?)
        ORDER BY s.id
        """,
        (project_id, project_id, project_id, project_id),
    ):
        errors.append(f"I2: segment {seg_id} points at bead {bead_id} of project {bead_project}")

    # I3
    for (bead_id,) in conn.execute(
        """
        SELECT bd.id FROM beads bd
        WHERE bd.project_id = ? AND NOT EXISTS (SELECT 1 FROM segments s WHERE s.bead_id = bd.id)
        ORDER BY bd.ord
        """,
        (project_id,),
    ):
        errors.append(f"I3: bead {bead_id} has no segments")

    # I5
    for table, row_id, ord_ in conn.execute(
        """
        SELECT 'bead', id, ord FROM beads WHERE project_id = ? AND ord < 0
        UNION ALL
        SELECT 'block', b.id, b.ord FROM blocks b JOIN documents d ON d.id = b.document_id
            WHERE d.project_id = ? AND b.ord < 0
        UNION ALL
        SELECT 'segment', s.id, s.ord FROM segments s JOIN blocks b ON b.id = s.block_id
            JOIN documents d ON d.id = b.document_id WHERE d.project_id = ? AND s.ord < 0
        """,
        (project_id, project_id, project_id),
    ):
        errors.append(f"I5: {table} {row_id} has negative ord {ord_}")

    return errors
