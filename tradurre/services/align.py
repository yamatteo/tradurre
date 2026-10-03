"""Baseline local aligner: anchors plus sentence length (PLAN.md, "Length aligner"; SPEC §3.1.4).

Dynamic programming over (source index, target index) with moves 1:1, 1:0, 0:1, 2:1, 1:2, 2:2. A move costs
prior + length + anchor:
- prior: −ln of the move's probability;
- length (Gale–Church): how far the target's character count is from the source's times the book's ratio;
- anchor: a bonus for tokens (numbers, capitalized words not first in their segment) found on both sides.
Only cells near the diagonal are computed (a band), so a book aligns in seconds.
"""

import math
import re
from dataclasses import dataclass

# (source count, target count, probability), in tie-breaking order.
_MOVES = [(1, 1, 0.89), (1, 0, 0.005), (0, 1, 0.005), (2, 1, 0.045), (1, 2, 0.045), (2, 2, 0.011)]
_PRIOR = {(ds, dt): -math.log(p) for ds, dt, p in _MOVES}
_BEST = -math.log(0.89)
_VARIANCE = 6.8
_BAND = 100
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
    source_len = [len(_SPACE.sub("", s)) for s in source]
    target_len = [len(_SPACE.sub("", t)) for t in target]
    total_s, total_t = sum(source_len), sum(target_len)
    ratio = total_t / total_s if n and m and total_s else 1.0
    source_tokens = [_tokens(s) for s in source]
    target_tokens = [_tokens(t) for t in target]

    width = _BAND + abs(m - n)

    def move_cost(i: int, j: int, ds: int, dt: int) -> float:
        """Cost of the move ending at (i, j) that takes ds source and dt target segments."""
        cost = _PRIOR[(ds, dt)]
        if ds and dt:
            ls = sum(source_len[i - ds:i])
            lt = sum(target_len[j - dt:j])
            cost += _length_cost(max(ls, 1), lt, ratio)
            st = source_tokens[i - 1] if ds == 1 else source_tokens[i - 2] | source_tokens[i - 1]
            tt = target_tokens[j - 1] if dt == 1 else target_tokens[j - 2] | target_tokens[j - 1]
            if st and tt:
                cost -= _ANCHOR_BONUS * min(_ANCHOR_CAP, len(st & tt))
        return cost

    inf = math.inf
    best = [[inf] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple[int, int, float] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for i in range(n + 1):
        if n and m:
            centre = i * m / n
            lo, hi = max(0, math.ceil(centre - width)), min(m, math.floor(centre + width))
        else:
            lo, hi = 0, m
        row = best[i]
        for j in range(lo, hi + 1):
            if i == 0 and j == 0:
                continue
            cell, step = inf, None
            for ds, dt, _ in _MOVES:
                pi, pj = i - ds, j - dt
                if pi < 0 or pj < 0:
                    continue
                previous = best[pi][pj]
                if previous == inf:
                    continue
                cost = move_cost(i, j, ds, dt)
                if previous + cost < cell:
                    cell, step = previous + cost, (ds, dt, cost)
            row[j] = cell
            back[i][j] = step
    if best[n][m] == inf:  # unreachable only if the band were broken; the end is always on the diagonal
        raise AssertionError("alignment band does not reach the end")

    beads: list[Bead] = []
    i, j = n, m
    while i or j:
        ds, dt, cost = back[i][j]
        confidence = round(math.exp(-max(0.0, cost - _BEST) / 4), 3)
        beads.append(Bead(list(range(i - ds, i)), list(range(j - dt, j)), confidence))
        i, j = i - ds, j - dt
    beads.reverse()
    return beads
