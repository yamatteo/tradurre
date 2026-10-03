"""Baseline local aligner: anchors plus sentence length (PLAN.md, "Length aligner"; SPEC §3.1.4).

Dynamic programming over (source index, target index) with moves 1:1, 1:0, 0:1, 2:1, 1:2, 2:2. A move costs
prior + length + anchor:
- prior: −ln of the move's probability;
- length (Gale–Church): how far the target's character count is from the source's times the book's ratio;
- anchor: a bonus for tokens (numbers, capitalized words not first in their segment) found on both sides.
Only cells near the diagonal are computed and stored (a band), so a book aligns in seconds: first a narrow band,
then, if the best path runs along its edge, once more with a band widened by the difference in segment counts.
"""

import math
import re
from array import array
from dataclasses import dataclass

# (source count, target count, probability), in tie-breaking order.
_MOVES = [(1, 1, 0.89), (1, 0, 0.005), (0, 1, 0.005), (2, 1, 0.045), (1, 2, 0.045), (2, 2, 0.011)]
_PRIOR = {(ds, dt): -math.log(p) for ds, dt, p in _MOVES}
_BEST = -math.log(0.89)
_VARIANCE = 6.8
_BAND = 100
_EDGE = 10  # a path this close to a band edge reruns with the wide band
_ANCHOR_BONUS = 1.5
_ANCHOR_CAP = 3

_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"\w+")
_DIGITS = re.compile(r"\d+")


@dataclass
class Bead:
    source: list[int]  # indices into the source input
    target: list[int]  # indices into the target input
    confidence: float


def _tokens(segment: str) -> frozenset[str]:
    """Numbers, and words that start with an uppercase letter and aren't the segment's first word."""
    words = _WORD.findall(segment)
    return frozenset(w for w in words[1:] if w[0].isupper()) | frozenset(_DIGITS.findall(segment))


def _length_cost(ls: int, lt: int, ratio: float) -> float:
    delta = (lt - ls * ratio) / math.sqrt(ls * _VARIANCE)
    return -math.log(max(1e-12, math.erfc(abs(delta) / math.sqrt(2))))


def align(source: list[str], target: list[str]) -> list[Bead]:
    """Beads tiling both inputs in order: every index appears exactly once."""
    n, m = len(source), len(target)
    source_sums, target_sums = [0], [0]
    for text in source:
        source_sums.append(source_sums[-1] + len(_SPACE.sub("", text)))
    for text in target:
        target_sums.append(target_sums[-1] + len(_SPACE.sub("", text)))
    total_s, total_t = source_sums[-1], target_sums[-1]
    ratio = total_t / total_s if n and m and total_s else 1.0
    source_tokens = [_tokens(s) for s in source]
    target_tokens = [_tokens(t) for t in target]

    def move_cost(i: int, j: int, ds: int, dt: int) -> float:
        """Cost of the move ending at (i, j) that takes ds source and dt target segments."""
        cost = _PRIOR[(ds, dt)]
        if ds and dt:
            ls = source_sums[i] - source_sums[i - ds]
            lt = target_sums[j] - target_sums[j - dt]
            cost += _length_cost(max(ls, 1), lt, ratio)
            st = source_tokens[i - 1] if ds == 1 else source_tokens[i - 2] | source_tokens[i - 1]
            tt = target_tokens[j - 1] if dt == 1 else target_tokens[j - 2] | target_tokens[j - 1]
            if st and tt:
                cost -= _ANCHOR_BONUS * min(_ANCHOR_CAP, len(st & tt))
        return cost

    def run(width: float) -> tuple[list[Bead], bool]:
        """The beads of the best path inside the band of this width, and whether that path runs within
        `_EDGE` cells of a band edge the grid doesn't clip (so a wider band might find a better one)."""
        inf = math.inf
        moves = [(k, ds, dt, _PRIOR[(ds, dt)]) for k, (ds, dt, _) in enumerate(_MOVES)]
        sqrt, log, erfc, root2 = math.sqrt, math.log, math.erfc, math.sqrt(2)
        rows: list[array] = []  # per row i, the best cost of each band cell lo..hi
        backs: list[array] = []  # per row i, the index in _MOVES of each cell's chosen move (-1: none)
        bounds: list[tuple[int, int]] = []  # per row i, (lo, hi)
        for i in range(n + 1):
            if n and m:
                centre = i * m / n
                lo, hi = max(0, math.ceil(centre - width)), min(m, math.floor(centre + width))
            else:
                lo, hi = 0, m
            row = array("d", [inf]) * (hi - lo + 1)
            back = array("b", [-1]) * (hi - lo + 1)
            for j in range(lo, hi + 1):
                if i == 0 and j == 0:
                    row[0] = 0.0
                    continue
                cell, step = inf, -1
                for k, ds, dt, prior in moves:
                    pi, pj = i - ds, j - dt
                    if pi < 0 or pj < 0:
                        continue
                    if ds:
                        previous_row, previous_lo = rows[pi], bounds[pi][0]
                    else:
                        previous_row, previous_lo = row, lo
                    q = pj - previous_lo
                    if q < 0 or q >= len(previous_row):
                        continue
                    previous = previous_row[q]
                    if previous == inf:
                        continue
                    # move_cost(i, j, ds, dt), inlined: this loop runs for every band cell
                    cost = prior
                    if ds and dt:
                        ls = source_sums[i] - source_sums[pi]
                        lt = target_sums[j] - target_sums[pj]
                        if ls < 1:
                            ls = 1
                        delta = (lt - ls * ratio) / sqrt(ls * _VARIANCE)  # _length_cost, inlined
                        cost += -log(max(1e-12, erfc(abs(delta) / root2)))
                        st = source_tokens[i - 1] if ds == 1 else source_tokens[i - 2] | source_tokens[i - 1]
                        tt = target_tokens[j - 1] if dt == 1 else target_tokens[j - 2] | target_tokens[j - 1]
                        if st and tt:
                            cost -= _ANCHOR_BONUS * min(_ANCHOR_CAP, len(st & tt))
                    if previous + cost < cell:
                        cell, step = previous + cost, k
                row[j - lo] = cell
                back[j - lo] = step
            rows.append(row)
            backs.append(back)
            bounds.append((lo, hi))
        if rows[n][m - bounds[n][0]] == inf:  # unreachable only if the band were broken; the end is on the diagonal
            raise AssertionError("alignment band does not reach the end")

        beads: list[Bead] = []
        near_edge = False
        i, j = n, m
        while True:
            lo, hi = bounds[i]
            if (lo > 0 and j - lo < _EDGE) or (hi < m and hi - j < _EDGE):
                near_edge = True
            if not (i or j):
                break
            ds, dt, _ = _MOVES[backs[i][j - lo]]
            cost = move_cost(i, j, ds, dt)
            confidence = round(math.exp(-max(0.0, cost - _BEST) / 4), 3)
            beads.append(Bead(list(range(i - ds, i)), list(range(j - dt, j)), confidence))
            i, j = i - ds, j - dt
        beads.reverse()
        return beads, near_edge

    narrow, wide = _BAND, _BAND + abs(m - n)
    beads, near_edge = run(narrow)
    if near_edge and wide > narrow:
        beads, _ = run(wide)
    return beads
