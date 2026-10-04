"""From two extractions to a project in the new model (PLAN.md, "Interim build").

Segmentation is `segment.split_sentences` (French/Italian conventions); alignment is the baseline local aligner
(`align.align`: sentence length plus anchors).
"""

import sqlite3

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


def build_book(
    conn: sqlite3.Connection,
    project_id: str,
    source: tuple[str, str, Extraction],
    target: tuple[str, str, Extraction],
) -> None:
    """Create both documents and the baseline beads of an existing project, inside the caller's transaction.

    `source` and `target` are (filename, format, extraction). Not recorded in the operation history.
    """
    sides = []
    for side, (filename, format, extraction) in (("source", source), ("target", target)):
        blocks = _blocks(extraction)
        segment_ids = create_document(conn, project_id, side, filename, format, blocks)
        sides.append(_included(blocks, segment_ids))
    source_segments, target_segments = sides

    source_texts = [text for _, text in source_segments]
    target_texts = [text for _, text in target_segments]
    append_beads(conn, project_id, [
        NewBead([source_segments[k][0] for k in bead.source], [target_segments[k][0] for k in bead.target],
                bead.confidence, "length")
        for bead in align.align(source_texts, target_texts)
    ])
