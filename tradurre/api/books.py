"""Books: projects in the new model (PLAN.md, "Book API: import and read").

Writes go through `transaction` (`tradurre.domain.history`), which defers foreign keys as the domain needs.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import PurePath

from collections.abc import Callable

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from tradurre.db import get_db
from tradurre.domain import DomainError, history
from tradurre.domain.beads import merge_with_next, move_first_to_previous, move_last_to_next, set_reviewed, split_bead
from tradurre.domain.blocks import exclude_block, include_block
from tradurre.domain.history import transaction
from tradurre.domain.invariants import check_project
from tradurre.domain.segments import edit_text, join_with_next, split_segment
from tradurre.models import (
    BookEditRequest,
    BookImportResponse,
    BookMoveRequest,
    BookResponse,
    BookReviewedRequest,
    BookSplitBeadRequest,
    BookSplitSegmentRequest,
    BookSummary,
)
from tradurre.services.build import build_book
from tradurre.services.extract import EXCLUDED_KINDS, Extraction, extract

router = APIRouter(tags=["books"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _extract(upload: UploadFile, content: bytes) -> tuple[str, str, Extraction]:
    """(filename, format, extraction) of an uploaded file, or the HTTP error the import answers with."""
    filename = upload.filename or ""
    try:
        # Seconds of CPU work for a PDF: off the event loop, so other requests aren't frozen meanwhile.
        extraction = await run_in_threadpool(extract, filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not any(block.kind not in EXCLUDED_KINDS for block in extraction.blocks):
        raise HTTPException(status_code=400, detail=f"no text found in {filename}")
    return filename, PurePath(filename).suffix.lower().lstrip("."), extraction


@router.post("/books", response_model=BookImportResponse, status_code=201)
async def import_book(
    source: UploadFile,
    target: UploadFile,
    title: str | None = Form(None),
    source_lang: str = Form("fr"),
    target_lang: str = Form("it"),
    db: sqlite3.Connection = Depends(get_db),
):
    source_file = await _extract(source, await source.read())
    target_file = await _extract(target, await target.read())
    title = title or PurePath(source_file[0]).stem

    book_id = str(uuid.uuid4())
    now = _now()
    with transaction(db):
        db.execute(
            "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (book_id, title, source_lang, target_lang, now, now),
        )
        build_book(db, book_id, source_file, target_file)
    bead_count = db.execute("SELECT COUNT(*) FROM beads WHERE project_id = ?", (book_id,)).fetchone()[0]
    warnings = [f"{side}: {w}" for side, (_, _, ex) in (("source", source_file), ("target", target_file))
                for w in ex.warnings]
    return {"id": book_id, "title": title, "bead_count": bead_count, "warnings": warnings}


@router.get("/books", response_model=list[BookSummary])
def list_books(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        """
        SELECT p.id, p.title, p.source_lang, p.target_lang,
               (SELECT COUNT(*) FROM beads b WHERE b.project_id = p.id) AS bead_count,
               (SELECT COUNT(*) FROM beads b WHERE b.project_id = p.id AND b.reviewed = 1) AS reviewed_count
        FROM projects p
        WHERE EXISTS (SELECT 1 FROM documents d WHERE d.project_id = p.id)
        ORDER BY p.updated_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _book_row(db: sqlite3.Connection, book_id: str) -> sqlite3.Row:
    row = db.execute(
        "SELECT p.id, p.title, p.source_lang, p.target_lang FROM projects p WHERE p.id = ? "
        "AND EXISTS (SELECT 1 FROM documents d WHERE d.project_id = p.id)",
        (book_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return row


def _read_book(db: sqlite3.Connection, book_id: str) -> dict:
    """The whole book as `BookResponse` describes it."""
    book = dict(_book_row(db, book_id))
    beads = {
        r["id"]: {"id": r["id"], "confidence": r["confidence"], "method": r["method"],
                  "reviewed": bool(r["reviewed"]), "source": [], "target": []}
        for r in db.execute(
            "SELECT id, confidence, method, reviewed FROM beads WHERE project_id = ? ORDER BY ord", (book_id,)
        )
    }
    excluded: list[dict] = []
    last_bead: dict[str, int | None] = {"source": None, "target": None}
    rows = db.execute(
        """
        SELECT d.side, b.id AS block_id, b.kind, b.excluded, b.page, s.id AS segment_id, s.text, s.bead_id
        FROM segments s
        JOIN blocks b ON b.id = s.block_id
        JOIN documents d ON d.id = b.document_id
        WHERE d.project_id = ?
        ORDER BY d.side, b.ord, s.ord
        """,
        (book_id,),
    )
    for r in rows:
        side = r["side"]
        if r["excluded"]:
            if not excluded or excluded[-1]["block_id"] != r["block_id"]:
                excluded.append({"block_id": r["block_id"], "side": side, "kind": r["kind"], "page": r["page"],
                                 "segments": [], "after_bead_id": last_bead[side]})
            excluded[-1]["segments"].append({"segment_id": r["segment_id"], "text": r["text"]})
        else:
            beads[r["bead_id"]][side].append({"segment_id": r["segment_id"], "block_id": r["block_id"],
                                              "block_kind": r["kind"], "text": r["text"]})
            last_bead[side] = r["bead_id"]
    undone = {r[0] for r in db.execute("SELECT DISTINCT undone FROM operations WHERE project_id = ?", (book_id,))}
    return {**book, "beads": list(beads.values()), "excluded": excluded,
            "can_undo": 0 in undone, "can_redo": 1 in undone}


@router.get("/books/{book_id}", response_model=BookResponse)
def get_book(book_id: str, db: sqlite3.Connection = Depends(get_db)):
    return _read_book(db, book_id)


@router.get("/books/{book_id}/check", response_model=list[str])
def check_book(book_id: str, db: sqlite3.Connection = Depends(get_db)):
    _book_row(db, book_id)
    return check_project(db, book_id)


# Corrections (PLAN.md, "Book API: corrections"): the domain does the work and the checking.


def _correct(db: sqlite3.Connection, book_id: str, operation: Callable[[], object], nothing: str | None = None) -> dict:
    """Run one domain operation in a transaction and return the book.

    `nothing` is the 409 message when the operation returns None (undo/redo with nothing to do); otherwise None is
    a no-op success.
    """
    _book_row(db, book_id)
    try:
        with transaction(db):
            if operation() is None and nothing is not None:
                raise HTTPException(status_code=409, detail=nothing)
            db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_now(), book_id))
    except DomainError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _read_book(db, book_id)


@router.post("/books/{book_id}/beads/{bead_id}/move", response_model=BookResponse)
def move_segment(book_id: str, bead_id: int, body: BookMoveRequest, db: sqlite3.Connection = Depends(get_db)):
    move = move_first_to_previous if body.to == "previous" else move_last_to_next
    return _correct(db, book_id, lambda: move(db, book_id, bead_id, body.side))


@router.post("/books/{book_id}/beads/{bead_id}/merge-next", response_model=BookResponse)
def merge_next(book_id: str, bead_id: int, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: merge_with_next(db, book_id, bead_id))


@router.post("/books/{book_id}/beads/{bead_id}/split", response_model=BookResponse)
def split(book_id: str, bead_id: int, body: BookSplitBeadRequest, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: split_bead(db, book_id, bead_id, body.source_at, body.target_at))


@router.post("/books/{book_id}/reviewed", response_model=BookResponse)
def reviewed(book_id: str, body: BookReviewedRequest, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: set_reviewed(db, book_id, body.bead_ids, body.reviewed, body.skim))


@router.post("/books/{book_id}/segments/{segment_id}/edit", response_model=BookResponse)
def edit(book_id: str, segment_id: int, body: BookEditRequest, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: edit_text(db, book_id, segment_id, body.text))


@router.post("/books/{book_id}/segments/{segment_id}/split", response_model=BookResponse)
def split_text(book_id: str, segment_id: int, body: BookSplitSegmentRequest, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: split_segment(db, book_id, segment_id, body.offset))


@router.post("/books/{book_id}/segments/{segment_id}/join-next", response_model=BookResponse)
def join_next(book_id: str, segment_id: int, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: join_with_next(db, book_id, segment_id))


@router.post("/books/{book_id}/blocks/{block_id}/exclude", response_model=BookResponse)
def exclude(book_id: str, block_id: int, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: exclude_block(db, book_id, block_id))


@router.post("/books/{book_id}/blocks/{block_id}/include", response_model=BookResponse)
def include(book_id: str, block_id: int, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: include_block(db, book_id, block_id))


@router.post("/books/{book_id}/undo", response_model=BookResponse)
def undo(book_id: str, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: history.undo(db, book_id), nothing="Nothing to undo")


@router.post("/books/{book_id}/redo", response_model=BookResponse)
def redo(book_id: str, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: history.redo(db, book_id), nothing="Nothing to redo")
