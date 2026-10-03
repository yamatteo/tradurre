"""Gold chapter: a hand-checked chapter of a book, saved as text, to score aligners against (PLAN.md, "Gold
chapter").

A gold cell is a side of a bead: its segments' `original_text` in reading order, joined with one space. Original
text, not edited text, so a text edit for extraction damage doesn't change the gold; splits and joins keep the
original text consistent (`domain/segments.py`).
"""

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_CHAPTER_NUMBER = re.compile(r"^\s*([0-9]+|[IVXLC]+)\s*$")  # as `tests/test_library.py`
_BREAKS = re.compile(r"[\t\r\n]")


def _cell(texts: list[str]) -> str:
    return _BREAKS.sub(" ", " ".join(texts))


def _read(conn: sqlite3.Connection, book_id: str) -> tuple[list[tuple[str, str, bool]], list[int]]:
    """Every bead as (source cell, target cell, reviewed), and the indices of the beads holding a chapter number
    (a source heading that is only a number)."""
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
    return [
        (_cell(c["source"]), _cell(c["target"]), bool(bead["reviewed"])) for c, bead in zip(cells, beads)
    ], starts


def book_beads(conn: sqlite3.Connection, book_id: str) -> list[tuple[str, str, bool]]:
    """Every bead of the book as (source cell, target cell, reviewed)."""
    return _read(conn, book_id)[0]


def chapter_beads(conn: sqlite3.Connection, book_id: str, chapter: int) -> list[tuple[str, str, bool]]:
    """The beads of chapter `chapter` (1-based) as (source cell, target cell, reviewed).

    Chapter n runs from the bead holding the n-th source heading that is only a number up to, excluding, the bead
    holding the next one (or the end of the book).
    """
    beads, starts = _read(conn, book_id)
    if not 1 <= chapter <= len(starts):
        raise ValueError(f"chapter {chapter} not found; the book has {len(starts)}")
    end = starts[chapter] if chapter < len(starts) else len(beads)
    return beads[starts[chapter - 1]:end]


def write_tsv(path: Path, cells: list[tuple[str, str]]) -> None:
    """One line per bead, `source<TAB>target`; no header."""
    path.write_text("".join(f"{_cell([s])}\t{_cell([t])}\n" for s, t in cells), encoding="utf-8")


def read_tsv(path: Path) -> list[tuple[str, str]]:
    cells = []
    for line in path.read_text(encoding="utf-8").split("\n")[:-1]:
        source, target = line.split("\t")
        cells.append((source, target))
    return cells


# --- Scoring (PLAN.md, "Gold chapter", metric) ---

_SPACE = re.compile(r"\s+")


def boundaries(cells: list[tuple[str, str]]) -> tuple[str, str, list[tuple[int, int]]]:
    """The two side texts (whitespace removed) and every bead's boundary: how many of their characters lie in the
    bead and all before it, (source, target)."""
    sources: list[str] = []
    targets: list[str] = []
    ends: list[tuple[int, int]] = []
    s = t = 0
    for source, target in cells:
        source, target = _SPACE.sub("", source), _SPACE.sub("", target)
        sources.append(source)
        targets.append(target)
        s, t = s + len(source), t + len(target)
        ends.append((s, t))
    return "".join(sources), "".join(targets), ends


@dataclass
class Score:
    precision: float
    recall: float
    f1: float
    gold_count: int
    predicted_count: int
    missed: list[tuple[int, int]]  # runs of gold bead indices (first, last) whose boundary isn't predicted


def score(gold: list[tuple[str, str]], predicted: list[tuple[str, str]]) -> Score:
    """Bead-boundary precision, recall and F1 of `predicted` (a whole book) against `gold` (a chapter in it)."""
    gold_source, gold_target, gold_ends = boundaries(gold)
    source, target, predicted_ends = boundaries(predicted)
    shift_s, shift_t = source.find(gold_source), target.find(gold_target)
    if shift_s < 0 or shift_t < 0:
        raise ValueError("the gold chapter doesn't match the current extraction")
    length_s, length_t = len(gold_source), len(gold_target)
    gold_set = set(gold_ends[:-1])
    predicted_set = {
        (s - shift_s, t - shift_t) for s, t in predicted_ends
        if 0 <= s - shift_s <= length_s and 0 <= t - shift_t <= length_t
    } - {(0, 0), (length_s, length_t)}
    hits = len(gold_set & predicted_set)
    precision = hits / len(predicted_set) if predicted_set else 0.0
    recall = hits / len(gold_set) if gold_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    runs: list[tuple[int, int]] = []
    for k, end in enumerate(gold_ends[:-1]):
        if end in predicted_set:
            continue
        if runs and runs[-1][1] == k - 1:
            runs[-1] = (runs[-1][0], k)
        else:
            runs.append((k, k))
    runs.sort(key=lambda run: run[0] - run[1])  # longest first; stable, so equal lengths stay in book order
    return Score(precision, recall, f1, len(gold_set), len(predicted_set), runs)
