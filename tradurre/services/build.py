"""From two extractions to a project in the new model (PLAN.md, "Interim build").

Segmentation is `segment.split_sentences` (French/Italian conventions); alignment is the baseline local aligner
(`align.align`: sentence length plus anchors).
"""

import sqlite3
from dataclasses import dataclass

from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.services import align, segment
from tradurre.services.extract import EXCLUDED_KINDS, Extraction


def _blocks(extraction: Extraction) -> list[NewBlock]:
    return [
        NewBlock(
            block.kind,
            segment.split_sentences(block.text) or [block.text],
            excluded=block.kind in EXCLUDED_KINDS,
            page=block.page,
        )
        for block in extraction.blocks
    ]


def _included(blocks: list[NewBlock], segment_ids: list[list[int]]) -> list[tuple[int, str]]:
    """(segment id, text) of the included segments, in document order."""
    return [
        (seg_id, text)
        for block, ids in zip(blocks, segment_ids)
        if not block.excluded
        for seg_id, text in zip(ids, block.segments)
    ]


def _headings_open(beads: list[align.Bead], source_kinds: list[str], target_kinds: list[str]) -> list[align.Bead]:
    """A heading that ends a multi-segment side of a bead opens the next bead instead: a chapter number belongs to
    its chapter. `*_kinds` are the block kinds of the included segments, parallel to the aligner's inputs. The
    last bead is left alone; a side with a single segment is never emptied; a heading moved into a bead
    stays there. Returns new beads."""
    moved = [align.Bead(list(b.source), list(b.target), b.confidence) for b in beads]
    for k in range(len(moved) - 1):
        for side, kinds in (("source", source_kinds), ("target", target_kinds)):
            original = getattr(beads[k], side)  # a heading moved into this bead does not count: it never moves twice
            if len(original) >= 2 and kinds[original[-1]] == "heading":
                getattr(moved[k + 1], side).insert(0, getattr(moved[k], side).pop())
    return moved


@dataclass
class PreparedBook:
    """Both editions segmented and aligned, ready to write: everything that needs no database."""
    source: tuple[str, str, list[NewBlock]]  # (filename, format, blocks)
    target: tuple[str, str, list[NewBlock]]
    beads: list[align.Bead]  # indices into each side's included segments, in document order


def prepare_book(source: tuple[str, str, Extraction], target: tuple[str, str, Extraction]) -> PreparedBook:
    """Segment and align two extractions, `(filename, format, extraction)` each. Seconds for a big book, so the
    import runs it before taking the database's write lock."""
    sides = [(filename, format, _blocks(extraction)) for filename, format, extraction in (source, target)]
    texts = [[text for block in blocks if not block.excluded for text in block.segments] for _, _, blocks in sides]
    kinds = [[block.kind for block in blocks if not block.excluded for _ in block.segments] for _, _, blocks in sides]
    beads = _headings_open(align.align(texts[0], texts[1]), kinds[0], kinds[1])
    return PreparedBook(sides[0], sides[1], beads)


def write_book(conn: sqlite3.Connection, project_id: str, prepared: PreparedBook) -> None:
    """Create both documents and the baseline beads of an existing project, inside the caller's transaction.

    Not recorded in the operation history.
    """
    sides = []
    for side, (filename, format, blocks) in (("source", prepared.source), ("target", prepared.target)):
        segment_ids = create_document(conn, project_id, side, filename, format, blocks)
        sides.append(_included(blocks, segment_ids))
    source_segments, target_segments = sides
    append_beads(conn, project_id, [
        NewBead([source_segments[k][0] for k in bead.source], [target_segments[k][0] for k in bead.target],
                bead.confidence, "length")
        for bead in prepared.beads
    ])


def build_book(
    conn: sqlite3.Connection,
    project_id: str,
    source: tuple[str, str, Extraction],
    target: tuple[str, str, Extraction],
) -> None:
    """`prepare_book` then `write_book`, inside the caller's transaction.

    `source` and `target` are (filename, format, extraction). Not recorded in the operation history.
    """
    write_book(conn, project_id, prepare_book(source, target))
