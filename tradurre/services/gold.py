"""Gold book: the translator's corrected book, saved to score the import pipeline against (PLAN.md, "Gold chapter",
design v2).

A layer is every segment of both editions in document order, as (original text, bead index or None if its block is
excluded), plus each bead's reviewed mark. Original text, not edited text, so a text edit for extraction damage
doesn't change the gold. Scores are per non-whitespace character, so segmentation and whitespace don't matter:
- exclusion: precision/recall of the excluded characters;
- alignment: precision/recall/F1 of bead boundaries, counted on the characters both layers include.
"""

import re
import sqlite3
from dataclasses import dataclass

SIDES = ("source", "target")
_SPACE = re.compile(r"\s+")


@dataclass
class Layer:
    source: list[tuple[str, int | None]]
    target: list[tuple[str, int | None]]
    reviewed: list[bool]

    def side(self, side: str) -> list[tuple[str, int | None]]:
        return self.source if side == "source" else self.target


def read_layer(conn: sqlite3.Connection, book_id: str) -> Layer:
    if conn.execute("SELECT 1 FROM documents WHERE project_id = ?", (book_id,)).fetchone() is None:
        raise ValueError(f"book {book_id} not found")
    beads = conn.execute("SELECT id, reviewed FROM beads WHERE project_id = ? ORDER BY ord", (book_id,)).fetchall()
    index = {row["id"]: k for k, row in enumerate(beads)}
    sides: dict[str, list[tuple[str, int | None]]] = {side: [] for side in SIDES}
    rows = conn.execute(
        """
        SELECT d.side, s.original_text, s.bead_id
        FROM segments s
        JOIN blocks b ON b.id = s.block_id
        JOIN documents d ON d.id = b.document_id
        WHERE d.project_id = ?
        ORDER BY d.side, b.ord, s.ord
        """,
        (book_id,),
    )
    for r in rows:
        sides[r["side"]].append((r["original_text"], None if r["bead_id"] is None else index[r["bead_id"]]))
    return Layer(sides["source"], sides["target"], [bool(row["reviewed"]) for row in beads])


def layer_to_json(layer: Layer) -> dict:
    return {
        "format": 1,
        "source": [[text, bead] for text, bead in layer.source],
        "target": [[text, bead] for text, bead in layer.target],
        "reviewed": layer.reviewed,
    }


def layer_from_json(data: dict) -> Layer:
    if data.get("format") != 1:
        raise ValueError(f"unknown gold format {data.get('format')!r}")
    return Layer(
        [(text, bead) for text, bead in data["source"]],
        [(text, bead) for text, bead in data["target"]],
        list(data["reviewed"]),
    )


@dataclass
class Score:
    alignment_precision: float
    alignment_recall: float
    alignment_f1: float
    gold_boundaries: int
    predicted_boundaries: int
    exclusion_precision: float
    exclusion_recall: float
    exclusion_f1: float
    excluded_chars: dict[str, tuple[int, int]]  # side -> (gold, predicted)
    missed: list[tuple[int, int]]  # runs of gold bead indices (first, last) whose boundary isn't predicted


def _chars(segments: list[tuple[str, int | None]]) -> tuple[str, list[int | None]]:
    """The side's text without whitespace, and the bead (or None) of each of its characters."""
    texts: list[str] = []
    beads: list[int | None] = []
    for text, bead in segments:
        text = _SPACE.sub("", text)
        texts.append(text)
        beads.extend([bead] * len(text))
    return "".join(texts), beads


def _ratio(hits: int, total: int, other: int) -> float:
    """hits / total, or by the empty-set convention: 1 if both sets are empty, 0 if only this one is."""
    if total:
        return hits / total
    return 1.0 if not other else 0.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _boundaries(common: dict[str, list[int]], n_beads: int) -> list[tuple[int, int]]:
    """For every bead, the number of common characters of each side in it and all beads before it."""
    counts = {side: [0] * n_beads for side in SIDES}
    for side in SIDES:
        for bead in common[side]:
            counts[side][bead] += 1
    ends = []
    s = t = 0
    for k in range(n_beads):
        s, t = s + counts["source"][k], t + counts["target"][k]
        ends.append((s, t))
    return ends


def score(gold: Layer, predicted: Layer) -> Score:
    """Exclusion and alignment scores of `predicted` (a fresh import) against `gold` (the corrected book)."""
    common_gold: dict[str, list[int]] = {}
    common_predicted: dict[str, list[int]] = {}
    excluded_chars: dict[str, tuple[int, int]] = {}
    excluded_both = 0
    for side in SIDES:
        gold_text, gold_beads = _chars(gold.side(side))
        predicted_text, predicted_beads = _chars(predicted.side(side))
        if gold_text != predicted_text:
            raise ValueError(f"the gold doesn't match the current extraction ({side})")
        excluded_chars[side] = (gold_beads.count(None), predicted_beads.count(None))
        excluded_both += sum(g is None and p is None for g, p in zip(gold_beads, predicted_beads))
        both = [(g, p) for g, p in zip(gold_beads, predicted_beads) if g is not None and p is not None]
        common_gold[side] = [g for g, _ in both]
        common_predicted[side] = [p for _, p in both]

    excluded_gold = sum(g for g, _ in excluded_chars.values())
    excluded_predicted = sum(p for _, p in excluded_chars.values())
    exclusion_precision = _ratio(excluded_both, excluded_predicted, excluded_gold)
    exclusion_recall = _ratio(excluded_both, excluded_gold, excluded_predicted)

    gold_ends = _boundaries(common_gold, len(gold.reviewed))
    predicted_ends = _boundaries(common_predicted, len(predicted.reviewed))
    edges = {(0, 0), (len(common_gold["source"]), len(common_gold["target"]))}
    gold_set = set(gold_ends) - edges
    predicted_set = set(predicted_ends) - edges
    hits = len(gold_set & predicted_set)
    alignment_precision = _ratio(hits, len(predicted_set), len(gold_set))
    alignment_recall = _ratio(hits, len(gold_set), len(predicted_set))

    runs: list[tuple[int, int]] = []
    for k, end in enumerate(gold_ends):
        if end in edges or end in predicted_set:
            continue
        if runs and runs[-1][1] == k - 1:
            runs[-1] = (runs[-1][0], k)
        else:
            runs.append((k, k))
    runs.sort(key=lambda run: run[0] - run[1])  # longest first; stable, so equal lengths stay in book order

    return Score(
        alignment_precision, alignment_recall, _f1(alignment_precision, alignment_recall),
        len(gold_set), len(predicted_set),
        exclusion_precision, exclusion_recall, _f1(exclusion_precision, exclusion_recall),
        excluded_chars, runs,
    )
