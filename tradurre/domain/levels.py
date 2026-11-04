"""Alignment levels (SPEC §2, "Levels: sentences, turns, paragraphs").

The levels are derived views over the beads, defined by the source's structure: a paragraph is a source block, a
turn is a speech paragraph (one that opens with a dialogue mark) or, outside speech, a single sentence. A bead
records the finest level it was reviewed at (`beads.review_level`); this module holds the level ranks and tells,
for the boundary after each bead, whether a turn and a paragraph end there.
"""

import sqlite3
from collections.abc import Sequence

SPEECH_OPENERS = "—–-«"  # em dash, en dash, hyphen, opening guillemet

# Review levels, coarse to fine; a higher rank is a finer, stronger mark. 0 is unreviewed.
LEVEL_RANKS = {"paragraph": 1, "turn": 2, "sentence": 3}
_LEVEL_NAMES = {rank: name for name, rank in LEVEL_RANKS.items()}


def is_speech(text: str) -> bool:
    """Whether the text opens with a dialogue mark (its first non-whitespace character)."""
    stripped = text.lstrip()
    return bool(stripped) and stripped[0] in SPEECH_OPENERS


def level_name(rank: int) -> str | None:
    """The level a review rank stands for, or None for 0 (unreviewed)."""
    return _LEVEL_NAMES.get(rank)


def level_rank(level: str) -> int:
    if level not in LEVEL_RANKS:
        raise ValueError(f"unknown level {level!r}")
    return LEVEL_RANKS[level]


def compute_unit_ends(
    bead_ids: Sequence[int], segments: Sequence[tuple[int, int, str]]
) -> dict[int, tuple[bool, bool]]:
    """`bead id -> (turn_end, paragraph_end)` for the boundary after each bead.

    `bead_ids` are the book's beads in order; `segments` are the included source segments in document order, as
    (bead id, block id, text). With p the number of source segments up to and including the bead, the boundary
    lies between segments p-1 and p: a paragraph ends there iff they are in different blocks; a turn ends there
    iff a paragraph does or their block is not a speech paragraph. The last bead ends both; a bead before any
    source segment (p = 0), or after the last one, ends neither: a source-empty bead joins the unit it sits in.
    """
    position = {bead_id: k for k, bead_id in enumerate(bead_ids)}
    per_bead = [0] * len(bead_ids)
    speech: dict[int, bool] = {}
    for bead_id, block_id, text in segments:
        per_bead[position[bead_id]] += 1
        if block_id not in speech and text.strip():
            speech[block_id] = is_speech(text)
    blocks = [block_id for _, block_id, _ in segments]
    ends: dict[int, tuple[bool, bool]] = {}
    p = 0
    for k, bead_id in enumerate(bead_ids):
        p += per_bead[k]
        if k == len(bead_ids) - 1:
            ends[bead_id] = (True, True)
        elif p == 0 or p >= len(blocks):
            ends[bead_id] = (False, False)
        else:
            paragraph_end = blocks[p - 1] != blocks[p]
            ends[bead_id] = (paragraph_end or not speech.get(blocks[p - 1], False), paragraph_end)
    return ends


def unit_ends(conn: sqlite3.Connection, project_id: str) -> dict[int, tuple[bool, bool]]:
    """`compute_unit_ends` for a book, from the database (two queries, however many beads)."""
    bead_ids = [r[0] for r in conn.execute("SELECT id FROM beads WHERE project_id = ? ORDER BY ord", (project_id,))]
    segments = conn.execute(
        """
        SELECT s.bead_id, b.id, s.text
        FROM segments s
        JOIN blocks b ON b.id = s.block_id
        JOIN documents d ON d.id = b.document_id
        WHERE d.project_id = ? AND d.side = 'source' AND b.excluded = 0 AND s.bead_id IS NOT NULL
        ORDER BY b.ord, s.ord
        """,
        (project_id,),
    ).fetchall()
    return compute_unit_ends(bead_ids, [tuple(r) for r in segments])
