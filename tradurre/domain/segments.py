"""Segment text corrections (SPEC §2, §3.3; PLAN.md, "Domain operations").

Text corrections leave the beads alone, except joining two segments in different beads, which merges the run of
beads between them so the joined sentence stays whole in one bead. Callers own the transaction
(`history.transaction`).
"""

import sqlite3
from difflib import SequenceMatcher

from tradurre.domain import DomainError
from tradurre.domain.beads import _merge, _next
from tradurre.domain.history import Recorder, record
from tradurre.domain.ordering import ord_after


def _segment(conn: sqlite3.Connection, project_id: str, segment_id: int) -> sqlite3.Row:
    """The segment's row (id, block_id, ord, text, original_text, bead_id); DomainError if not in the project."""
    row = conn.execute(
        "SELECT s.id, s.block_id, s.ord, s.text, s.original_text, s.bead_id, d.project_id "
        "FROM segments s JOIN blocks b ON b.id = s.block_id JOIN documents d ON d.id = b.document_id "
        "WHERE s.id = ?",
        (segment_id,),
    ).fetchone()
    if row is None or row["project_id"] != project_id:
        raise DomainError(f"Segment {segment_id} is not in this project")
    return row


def edit_text(conn: sqlite3.Connection, project_id: str, segment_id: int, text: str) -> int | None:
    """Replace the segment's text (`original_text` is kept); None if the text is unchanged."""
    seg = _segment(conn, project_id, segment_id)
    if not text.strip():
        raise DomainError("A segment can't be empty; join it with its neighbour instead")
    if text == seg["text"]:
        return None
    rec = Recorder(conn)
    rec.update("segments", segment_id, text=text)
    return record(conn, project_id, "edit_text", rec)


def _map_offset(text: str, original: str, offset: int) -> int:
    """Map an offset in `text` to the corresponding offset in `original`."""
    for tag, i1, i2, j1, _ in SequenceMatcher(None, text, original, autojunk=False).get_opcodes():
        if i1 <= offset < i2:
            return j1 + (offset - i1) if tag == "equal" else j1
    return len(original)


def split_segment(conn: sqlite3.Connection, project_id: str, segment_id: int, offset: int) -> int:
    """Split the segment at `offset` of its text; the second part follows in the same block and bead."""
    seg = _segment(conn, project_id, segment_id)
    text, original = seg["text"], seg["original_text"]
    if not 0 < offset < len(text):
        raise DomainError("Split inside the segment's text")
    first, second = text[:offset].rstrip(), text[offset:].lstrip()
    if not first or not second:
        raise DomainError("Both parts of a split must contain text")
    at = _map_offset(text, original, offset)

    rec = Recorder(conn)
    rec.update("segments", segment_id, text=first, original_text=original[:at].rstrip())
    new_id = rec.insert("segments", {
        "block_id": seg["block_id"],
        "ord": ord_after(rec, "segments", seg["block_id"], segment_id),
        "text": second,
        "original_text": original[at:].lstrip(),
        "bead_id": seg["bead_id"],
    })
    record(conn, project_id, "split_segment", rec)
    return new_id


def join_with_next(conn: sqlite3.Connection, project_id: str, segment_id: int) -> int:
    """Join the segment with the next one in its block, merging their beads if they differ."""
    a = _segment(conn, project_id, segment_id)
    row = conn.execute(
        "SELECT id FROM segments WHERE block_id = ? AND ord > ? ORDER BY ord LIMIT 1", (a["block_id"], a["ord"])
    ).fetchone()
    if row is None:
        raise DomainError("This is the last segment of its block; segments can't be joined across blocks")
    b = _segment(conn, project_id, row[0])

    rec = Recorder(conn)
    if a["bead_id"] != b["bead_id"]:
        while True:
            next_id = _next(conn, a["bead_id"])
            _merge(rec, a["bead_id"], next_id)
            if next_id == b["bead_id"]:
                break
    rec.update(
        "segments",
        a["id"],
        text=a["text"] + " " + b["text"],
        original_text=a["original_text"] + " " + b["original_text"],
    )
    rec.delete("segments", b["id"])
    return record(conn, project_id, "join_segments", rec)
