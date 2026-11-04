"""Gold book: the translator's corrected book, saved to score the import pipeline against (PLAN.md, "Gold chapter",
design v2).

A layer is every segment of both editions in document order, as (original text, bead index or None if its block is
excluded), plus each bead's reviewed mark (at any level). Original text, not edited text, so a text edit for extraction damage
doesn't change the gold. Scores are per non-whitespace character, so segmentation and whitespace don't matter:
- exclusion: precision/recall of the excluded characters;
- alignment: precision/recall/F1 of bead boundaries, counted on the characters both layers include; since a gold
  may be coarser than the pipeline (sentences grouped into beads), a predicted boundary inside a gold bead is
  counted apart (`inside_gold`), and `coarse_precision` accepts it.
Alignment is also scored at nested levels, each a subset of the sentence-level boundaries, defined by the source
side: a speech paragraph (a block whose first segment opens with a dialogue mark) is one turn; a paragraph is a
block. `turn`: the predicted boundaries outside speech paragraphs against the gold as is; `paragraph`: both sets
kept only at paragraph breaks. Needs the predicted layer's block ids (`Layer.blocks`).
Characters are compared without whitespace, hyphens and soft hyphens.
A layer read from a corrected bundle also carries the corrected texts; `score_ligatures` then measures how many of
the ligature gaps (a space the PDF leaves after f/fi/fl/Th) the import closes, and how many real spaces it keeps.
"""

import re
import sqlite3
from bisect import bisect_right
from dataclasses import dataclass, field

from tradurre.domain.levels import SPEECH_OPENERS, is_speech  # noqa: F401  (re-exported)
from tradurre.services.bundle import _bead_review_rank
from tradurre.services.bundle import _read as _read_bundle

SIDES = ("source", "target")
_SPACE = re.compile(r"\s+")
_HYPHENS = str.maketrans("", "", "-\u00ad")  # the comparison ignores hyphens and soft hyphens
# A whitespace run (group 1) right after f/fi/fl/Th and before a letter or hyphen: a candidate ligature slip.
LIGATURE_GAP = re.compile(r"(?:(?i:f[il]?)|Th)(\s+)(?=[^\W\d_]|-)")


@dataclass
class Layer:
    source: list[tuple[str, int | None]]
    target: list[tuple[str, int | None]]
    reviewed: list[bool]
    corrected: dict[str, list[str]] | None = None  # per side, the current texts, parallel to source/target
    # per side, the block id of each segment, parallel to source/target (not compared: the gold files omit it)
    blocks: dict[str, list[int]] | None = field(default=None, compare=False)

    def side(self, side: str) -> list[tuple[str, int | None]]:
        return self.source if side == "source" else self.target


def read_layer(conn: sqlite3.Connection, book_id: str) -> Layer:
    if conn.execute("SELECT 1 FROM documents WHERE project_id = ?", (book_id,)).fetchone() is None:
        raise ValueError(f"book {book_id} not found")
    beads = conn.execute("SELECT id, review_level FROM beads WHERE project_id = ? ORDER BY ord", (book_id,)).fetchall()
    index = {row["id"]: k for k, row in enumerate(beads)}
    sides: dict[str, list[tuple[str, int | None]]] = {side: [] for side in SIDES}
    blocks: dict[str, list[int]] = {side: [] for side in SIDES}
    rows = conn.execute(
        """
        SELECT d.side, s.original_text, s.bead_id, b.id AS block_id
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
        blocks[r["side"]].append(r["block_id"])
    return Layer(sides["source"], sides["target"], [row["review_level"] > 0 for row in beads], None, blocks)


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


def layer_from_bundle(data: bytes) -> Layer:
    """The layer of a bundle (zip bytes): original texts, beads, reviewed marks and the current (corrected) texts."""
    bundle = _read_bundle(data)
    sides: dict[str, list[tuple[str, int | None]]] = {side: [] for side in SIDES}
    corrected: dict[str, list[str]] = {side: [] for side in SIDES}
    for document in bundle["documents"]:
        side = document["side"]
        for block in document["blocks"]:
            for segment in block["segments"]:
                sides[side].append((segment["original_text"], segment["bead"]))
                corrected[side].append(segment["text"])
    return Layer(sides["source"], sides["target"], [_bead_review_rank(b, bundle["version"], f"beads[{k}]") > 0 for k, b in enumerate(bundle["beads"])], corrected)


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
    on_gold: int = 0  # predicted boundaries equal to a gold boundary
    inside_gold: int = 0  # ... not a gold boundary, but strictly inside a gold bead (a finer split)
    elsewhere: int = 0  # ... all the others
    coarse_precision: float = 1.0  # (on_gold + inside_gold) / predicted_boundaries
    exclusion_by_side: dict[str, tuple[float, float]] = field(default_factory=dict)  # side -> (precision, recall)
    # Levels (need the predicted layer's blocks): the source side defines speech paragraphs and paragraph breaks.
    turn_precision: float = 1.0  # predicted boundaries outside speech paragraphs, against the gold as is
    turn_recall: float = 1.0
    turn_f1: float = 1.0
    turn_boundaries: int = 0  # predicted boundaries at turn level
    gold_inside_speech: int = 0  # gold boundaries inside a speech paragraph
    paragraph_precision: float = 1.0  # boundaries at paragraph breaks, both sets coarsened
    paragraph_recall: float = 1.0
    paragraph_f1: float = 1.0
    paragraph_boundaries: tuple[int, int] = (0, 0)  # (gold, predicted)


def _chars(segments: list[tuple[str, int | None]]) -> tuple[str, list[int | None]]:
    """The side's text without whitespace and hyphens, and the bead (or None) of each of its characters."""
    texts: list[str] = []
    beads: list[int | None] = []
    for text, bead in segments:
        text = _SPACE.sub("", text).translate(_HYPHENS)
        texts.append(text)
        beads.extend([bead] * len(text))
    return "".join(texts), beads


def _check_same_text(gold: Layer, predicted: Layer) -> None:
    """Raise if a side's text without whitespace differs between the two layers."""
    for side in SIDES:
        if _chars(gold.side(side))[0] != _chars(predicted.side(side))[0]:
            raise ValueError(f"the gold doesn't match the current extraction ({side})")


def _source_blocks(predicted: Layer) -> tuple[list[int], set[int]]:
    """The block id of each source character (as `_chars` counts them), and the ids of the speech blocks."""
    ids: list[int] = []
    speech: set[int] = set()
    seen: set[int] = set()
    for (text, _), block in zip(predicted.source, predicted.blocks["source"]):
        if block not in seen:
            seen.add(block)
            if is_speech(text):
                speech.add(block)
        ids.extend([block] * len(_SPACE.sub("", text).translate(_HYPHENS)))
    return ids, speech


def level_boundaries(level: str, boundaries: set[tuple[int, int]], source_blocks: list[int],
                     speech: set[int]) -> set[tuple[int, int]]:
    """The boundaries (edges already removed) kept at a level; `source_blocks` is the block id of each common source
    character. `sentence`: all. `turn`: not inside a speech paragraph. `paragraph`: only at a paragraph break."""
    if level == "sentence":
        return set(boundaries)
    if level not in ("turn", "paragraph"):
        raise ValueError(f"unknown level {level!r}")
    kept = set()
    for s, t in boundaries:
        if 0 < s < len(source_blocks):
            before, after = source_blocks[s - 1], source_blocks[s]
            if level == "paragraph" and before != after:
                kept.add((s, t))
            elif level == "turn" and not (before == after and before in speech):
                kept.add((s, t))
        elif level == "turn":
            kept.add((s, t))
    return kept


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
    exclusion_by_side: dict[str, tuple[float, float]] = {}
    _check_same_text(gold, predicted)
    for side in SIDES:
        _, gold_beads = _chars(gold.side(side))
        _, predicted_beads = _chars(predicted.side(side))
        excluded_chars[side] = (gold_beads.count(None), predicted_beads.count(None))
        both_excluded = sum(g is None and p is None for g, p in zip(gold_beads, predicted_beads))
        excluded_both += both_excluded
        exclusion_by_side[side] = (_ratio(both_excluded, excluded_chars[side][1], excluded_chars[side][0]),
                                   _ratio(both_excluded, excluded_chars[side][0], excluded_chars[side][1]))
        both = [(g, p) for g, p in zip(gold_beads, predicted_beads) if g is not None and p is not None]
        common_gold[side] = [g for g, _ in both]
        common_predicted[side] = [p for _, p in both]
        if predicted.blocks is not None and side == "source":
            ids, speech = _source_blocks(predicted)
            common_blocks = [b for b, g, p in zip(ids, gold_beads, predicted_beads) if g is not None and p is not None]

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

    coarse = sorted(set(gold_ends) | edges)
    on_gold = inside_gold = 0
    for s, t in predicted_set:
        if (s, t) in gold_set:
            on_gold += 1
            continue
        k = bisect_right(coarse, (s, t))
        if 0 < k < len(coarse):
            (a_s, a_t), (b_s, b_t) = coarse[k - 1], coarse[k]
            inside_gold += a_s <= s <= b_s and a_t <= t <= b_t
    elsewhere = len(predicted_set) - on_gold - inside_gold
    coarse_precision = _ratio(on_gold + inside_gold, len(predicted_set), len(gold_set))

    runs: list[tuple[int, int]] = []
    for k, end in enumerate(gold_ends):
        if end in edges or end in predicted_set:
            continue
        if runs and runs[-1][1] == k - 1:
            runs[-1] = (runs[-1][0], k)
        else:
            runs.append((k, k))
    runs.sort(key=lambda run: run[0] - run[1])  # longest first; stable, so equal lengths stay in book order

    levels: dict = {}
    if predicted.blocks is not None:
        turn_predicted = level_boundaries("turn", predicted_set, common_blocks, speech)
        turn_hits = len(gold_set & turn_predicted)
        turn_precision = _ratio(turn_hits, len(turn_predicted), len(gold_set))
        turn_recall = _ratio(turn_hits, len(gold_set), len(turn_predicted))
        paragraph_gold = level_boundaries("paragraph", gold_set, common_blocks, speech)
        paragraph_predicted = level_boundaries("paragraph", predicted_set, common_blocks, speech)
        paragraph_hits = len(paragraph_gold & paragraph_predicted)
        paragraph_precision = _ratio(paragraph_hits, len(paragraph_predicted), len(paragraph_gold))
        paragraph_recall = _ratio(paragraph_hits, len(paragraph_gold), len(paragraph_predicted))
        levels = dict(
            turn_precision=turn_precision, turn_recall=turn_recall, turn_f1=_f1(turn_precision, turn_recall),
            turn_boundaries=len(turn_predicted),
            gold_inside_speech=len(gold_set - level_boundaries("turn", gold_set, common_blocks, speech)),
            paragraph_precision=paragraph_precision, paragraph_recall=paragraph_recall,
            paragraph_f1=_f1(paragraph_precision, paragraph_recall),
            paragraph_boundaries=(len(paragraph_gold), len(paragraph_predicted)),
        )

    return Score(
        alignment_precision, alignment_recall, _f1(alignment_precision, alignment_recall),
        len(gold_set), len(predicted_set),
        exclusion_precision, exclusion_recall, _f1(exclusion_precision, exclusion_recall),
        excluded_chars, runs,
        on_gold, inside_gold, elsewhere, coarse_precision, exclusion_by_side, **levels,
    )


@dataclass
class LigatureCounts:
    slips: int = 0  # gold gaps that were ligature slips (closed in the corrected text)
    slips_closed: int = 0  # ... that the predicted layer closes
    slips_open: int = 0
    real: int = 0  # gold gaps that are real spaces
    real_kept: int = 0
    real_joined: int = 0  # real spaces the predicted layer closes
    skipped_segments: int = 0  # segments edited beyond whitespace, not examined

    @property
    def slip_recall(self) -> float:
        return _ratio(self.slips_closed, self.slips, 0)

    @property
    def keep_rate(self) -> float:
        return _ratio(self.real_kept, self.real, 0)


@dataclass
class LigatureScore:
    sides: dict[str, LigatureCounts]
    total: LigatureCounts


def ligature_positions(gold: Layer) -> dict[str, tuple[list[int], list[int], int]]:
    """Per side: the positions (in the side's non-whitespace character stream) of the gold's ligature slips and of
    its real spaces, and the number of skipped segments. Needs corrected texts."""
    if gold.corrected is None:
        raise ValueError("the gold has no corrected texts, so it has no ligature metric")
    result: dict[str, tuple[list[int], list[int], int]] = {}
    for side in SIDES:
        slips: list[int] = []
        real: list[int] = []
        skipped = 0
        offset = 0
        for (original, _), text in zip(gold.side(side), gold.corrected[side]):
            size = len(_SPACE.sub("", original))
            if _SPACE.sub("", text) != _SPACE.sub("", original):
                skipped += 1
            else:
                kept = {offset + n for n in _whitespace_runs(text)}
                for m in LIGATURE_GAP.finditer(original):
                    pos = offset + len(_SPACE.sub("", original[: m.start(1)]))
                    (real if pos in kept else slips).append(pos)
            offset += size
        result[side] = (slips, real, skipped)
    return result


def _whitespace_runs(text: str) -> list[int]:
    """For each whitespace run of `text`, the number of non-whitespace characters before it."""
    return [len(_SPACE.sub("", text[: m.start()])) for m in _SPACE.finditer(text)]


def _open_positions(segments: list[tuple[str, int | None]]) -> set[int]:
    """Where a side has whitespace or a segment boundary, in its non-whitespace character stream."""
    positions: set[int] = set()
    offset = 0
    for text, _ in segments:
        positions.add(offset)
        positions.update(offset + n for n in _whitespace_runs(text))
        offset += len(_SPACE.sub("", text))
    return positions


def score_ligatures(gold: Layer, predicted: Layer) -> LigatureScore:
    """How well `predicted` (a fresh import) closes the gold's ligature slips and keeps its real spaces."""
    gold_positions = ligature_positions(gold)
    _check_same_text(gold, predicted)
    sides: dict[str, LigatureCounts] = {}
    total = LigatureCounts()
    for side in SIDES:
        slips, real, skipped = gold_positions[side]
        open_ = _open_positions(predicted.side(side))
        closed = sum(p not in open_ for p in slips)
        joined = sum(p not in open_ for p in real)
        counts = LigatureCounts(len(slips), closed, len(slips) - closed, len(real), len(real) - joined, joined, skipped)
        sides[side] = counts
        for field in counts.__dataclass_fields__:
            setattr(total, field, getattr(total, field) + getattr(counts, field))
    return LigatureScore(sides, total)
