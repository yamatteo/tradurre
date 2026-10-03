"""Gold chapter: a hand-checked chapter of a book, saved as text, to score aligners against (PLAN.md, "Gold
chapter").

A gold cell is a side of a bead: its segments' `original_text` in reading order, joined with one space. Original
text, not edited text, so a text edit for extraction damage doesn't change the gold; splits and joins keep the
original text consistent (`domain/segments.py`).
"""

import re
import sqlite3
from pathlib import Path

_CHAPTER_NUMBER = re.compile(r"^\s*([0-9]+|[IVXLC]+)\s*$")  # as `tests/test_library.py`
_BREAKS = re.compile(r"[\t\r\n]")


def _cell(texts: list[str]) -> str:
    return _BREAKS.sub(" ", " ".join(texts))


def chapter_beads(conn: sqlite3.Connection, book_id: str, chapter: int) -> list[tuple[str, str, bool]]:
    """The beads of chapter `chapter` (1-based) as (source cell, target cell, reviewed).

    Chapter n runs from the bead holding the n-th source heading that is only a number up to, excluding, the bead
    holding the next one (or the end of the book).
    """
    if conn.execute("SELECT 1 FROM documents WHERE project_id = ?", (book_id,)).fetchone() is None:
        raise ValueError(f"book {book_id} not found")
    beads = conn.execute(
        "SELECT id, reviewed FROM beads WHERE project_id = ? ORDER BY ord", (book_id,)
    ).fetchall()
    index = {row["id"]: k for k, row in enumerate(beads)}
    cells: list[dict[str, list[str]]] = [{"source": [], "target": []} for _ in beads]
    starts: list[int] = []
    rows = conn.execute(
        """
        SELECT d.side, b.id AS block_id, b.kind, s.original_text, s.bead_id
        FROM segments s
        JOIN blocks b ON b.id = s.block_id
        JOIN documents d ON d.id = b.document_id
        WHERE d.project_id = ? AND NOT b.excluded
        ORDER BY d.side, b.ord, s.ord
        """,
        (book_id,),
    )
    seen_blocks: set[int] = set()
    for r in rows:
        k = index[r["bead_id"]]
        cells[k][r["side"]].append(r["original_text"])
        if r["side"] == "source" and r["block_id"] not in seen_blocks:
            seen_blocks.add(r["block_id"])
            if r["kind"] == "heading" and _CHAPTER_NUMBER.match(r["original_text"]):
                starts.append(k)
    if not 1 <= chapter <= len(starts):
        raise ValueError(f"chapter {chapter} not found; the book has {len(starts)}")
    first = starts[chapter - 1]
    end = starts[chapter] if chapter < len(starts) else len(beads)
    return [
        (_cell(cells[k]["source"]), _cell(cells[k]["target"]), bool(beads[k]["reviewed"]))
        for k in range(first, end)
    ]


def write_tsv(path: Path, cells: list[tuple[str, str]]) -> None:
    """One line per bead, `source<TAB>target`; no header."""
    path.write_text("".join(f"{_cell([s])}\t{_cell([t])}\n" for s, t in cells), encoding="utf-8")


def read_tsv(path: Path) -> list[tuple[str, str]]:
    cells = []
    for line in path.read_text(encoding="utf-8").split("\n")[:-1]:
        source, target = line.split("\t")
        cells.append((source, target))
    return cells
