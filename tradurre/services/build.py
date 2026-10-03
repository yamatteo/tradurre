"""From two extractions to a project in the new model (PLAN.md, "Interim build").

Segmentation is `segment.split_sentences` (French/Italian conventions); alignment is still v0.1's (`find_anchors`,
`align`), used unchanged until a better one replaces it behind `build_book`.
"""

import sqlite3

from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.services import align, segment
from tradurre.services import aligner as anchor_aligner
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
    aligner: str = "anchor",
) -> None:
    """Create both documents and the baseline beads of an existing project, inside the caller's transaction.

    `source` and `target` are (filename, format, extraction). `aligner` is "anchor" (v0.1's, the import's
    default) or "length" (`align.align`; PLAN.md, "Length aligner"). Not recorded in the operation history.
    """
    sides = []
    for side, (filename, format, extraction) in (("source", source), ("target", target)):
        blocks = _blocks(extraction)
        segment_ids = create_document(conn, project_id, side, filename, format, blocks)
        sides.append(_included(blocks, segment_ids))
    source_segments, target_segments = sides

    source_texts = [text for _, text in source_segments]
    target_texts = [text for _, text in target_segments]
    if aligner == "length":
        append_beads(conn, project_id, [
            NewBead([source_segments[k][0] for k in bead.source], [target_segments[k][0] for k in bead.target],
                    bead.confidence, "length")
            for bead in align.align(source_texts, target_texts)
        ])
        return
    if aligner != "anchor":
        raise ValueError(f"unknown aligner {aligner!r}")
    pairs = anchor_aligner.align(source_texts, target_texts, anchor_aligner.find_anchors(source_texts, target_texts))

    # `align` returns every unit once, in order, padded with "": consume the segment ids sequentially.
    remaining = {"source": iter(source_segments), "target": iter(target_segments)}
    beads = []
    for source_text, target_text in pairs:
        ids = {}
        for side, text in (("source", source_text), ("target", target_text)):
            ids[side] = []
            if text:
                seg_id, seg_text = next(remaining[side])
                assert seg_text == text, f"aligner output out of order on the {side} side"
                ids[side].append(seg_id)
        confidence = 0.5 if source_text and target_text else 0.2
        beads.append(NewBead(ids["source"], ids["target"], confidence, "anchor"))
    append_beads(conn, project_id, beads)
