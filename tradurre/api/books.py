"""Books: projects in the new model (PLAN.md, "Book API: import and read").

Writes go through `transaction` (`tradurre.domain.history`), which defers foreign keys as the domain needs.
"""

import json
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import PurePath

from collections.abc import Callable
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from tradurre.db import get_db
from tradurre.domain import DomainError, history
from tradurre.domain.beads import merge_with_next, move_first_to_previous, move_last_to_next, set_reviewed, split_bead
from tradurre.domain.blocks import exclude_block, exclude_range, include_block, include_range
from tradurre.domain.history import transaction
from tradurre.domain.invariants import check_project
from tradurre.domain.search import END, START, _bead_text, count_beads, search_beads
from tradurre.domain.segments import edit_text, join_with_next, restore_original, split_segment
from tradurre.models import (
    BookEditRequest,
    BookImportResponse,
    BookMoveRequest,
    BookRangeRequest,
    BookRealignRequest,
    BookResponse,
    BookReviewedRequest,
    BookRun,
    BookSearchCount,
    BookSearchResult,
    BookSearchSpan,
    BookSplitBeadRequest,
    BookSplitSegmentRequest,
    BookSummary,
    ContextBead,
)
from tradurre.services.build import PreparedBook, prepare_book, write_book
from tradurre.services.bundle import BundleError, export_bundle, import_bundle
from tradurre.services.edition import edition_blocks, edition_docx, edition_txt
from tradurre.services.extract import EXCLUDED_KINDS, Extraction, extract
from tradurre.services.realign import realign as realign_beads

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


def _import_stats(
    db: sqlite3.Connection,
    book_id: str,
    files: list[tuple[str, str, Extraction]],
    sizes: list[int],
    extract_ms: list[int],
    build_ms: int,
) -> dict:
    """Counts and timings of an import, read back from the database after `build_book` (PLAN.md, "Import warnings
    and run metadata")."""
    stats: dict = {}
    for side, (filename, format, _), size, ms in zip(("source", "target"), files, sizes, extract_ms):
        where = "FROM blocks b JOIN documents d ON d.id = b.document_id WHERE d.project_id = ? AND d.side = ?"
        stats[side] = {
            "filename": filename,
            "format": format,
            "bytes": size,
            "extract_ms": ms,
            "pages": db.execute(f"SELECT MAX(b.page) {where}", (book_id, side)).fetchone()[0],
            "blocks": dict(db.execute(f"SELECT b.kind, COUNT(*) {where} GROUP BY b.kind ORDER BY b.kind",
                                      (book_id, side)).fetchall()),
            "excluded_blocks": db.execute(f"SELECT COUNT(*) {where} AND b.excluded = 1", (book_id, side)).fetchone()[0],
            "segments": db.execute(
                "SELECT COUNT(*) FROM segments s JOIN blocks b ON b.id = s.block_id "
                "JOIN documents d ON d.id = b.document_id WHERE d.project_id = ? AND d.side = ? AND b.excluded = 0",
                (book_id, side),
            ).fetchone()[0],
        }
    beads = db.execute(
        """
        SELECT be.confidence, SUM(d.side = 'source') AS source, SUM(d.side = 'target') AS target
        FROM beads be
        JOIN segments s ON s.bead_id = be.id
        JOIN blocks b ON b.id = s.block_id
        JOIN documents d ON d.id = b.document_id
        WHERE be.project_id = ?
        GROUP BY be.id
        """,
        (book_id,),
    ).fetchall()
    shapes: dict[str, int] = {}
    for bead in beads:
        shape = f"{bead['source']}:{bead['target']}"
        shapes[shape] = shapes.get(shape, 0) + 1
    stats.update({
        "build_ms": build_ms,
        "beads": len(beads),
        "one_sided_beads": sum(not bead["source"] or not bead["target"] for bead in beads),
        "low_confidence_beads": sum(bead["confidence"] < 0.5 for bead in beads),
        "bead_shapes": shapes,
    })
    return stats


def _store_book(
    db: sqlite3.Connection,
    book_id: str,
    title: str,
    source_lang: str,
    target_lang: str,
    files: list[tuple[str, str, Extraction]],
    sizes: list[int],
    extract_ms: list[int],
    prepared: PreparedBook,
    prepare_ms: int,
) -> None:
    """Create the project, write the prepared book and record the import run with its warnings, in one transaction:
    the write lock covers only the writes."""
    now = _now()
    with transaction(db):
        db.execute(
            "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (book_id, title, source_lang, target_lang, now, now),
        )
        start = time.perf_counter()
        write_book(db, book_id, prepared)
        build_ms = prepare_ms + round((time.perf_counter() - start) * 1000)
        stats = _import_stats(db, book_id, files, sizes, extract_ms, build_ms)
        run_id = db.execute(
            "INSERT INTO runs (project_id, kind, created_at, app_version, stats) VALUES (?, 'import', ?, ?, ?)",
            (book_id, now, version("tradurre"), json.dumps(stats)),
        ).lastrowid
        for side, (_, _, extraction) in zip(("source", "target"), files):
            for message in extraction.warnings:
                db.execute("INSERT INTO warnings (run_id, side, message) VALUES (?, ?, ?)", (run_id, side, message))


@router.post("/books", response_model=BookImportResponse, status_code=201)
async def import_book(
    source: UploadFile,
    target: UploadFile,
    title: str | None = Form(None),
    source_lang: str = Form("fr"),
    target_lang: str = Form("it"),
    db: sqlite3.Connection = Depends(get_db),
):
    files, sizes, extract_ms = [], [], []
    for upload in (source, target):
        content = await upload.read()
        start = time.perf_counter()
        files.append(await _extract(upload, content))
        extract_ms.append(round((time.perf_counter() - start) * 1000))
        sizes.append(len(content))
    source_file, target_file = files
    title = title or PurePath(source_file[0]).stem

    book_id = str(uuid.uuid4())
    # Seconds of work for a big book (alignment above all): off the event loop, like extraction, and before the
    # write transaction, so other requests can write meanwhile.
    start = time.perf_counter()
    prepared = await run_in_threadpool(prepare_book, files[0], files[1])
    prepare_ms = round((time.perf_counter() - start) * 1000)
    await run_in_threadpool(_store_book, db, book_id, title, source_lang, target_lang, files, sizes, extract_ms,
                            prepared, prepare_ms)
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
        SELECT d.side, b.id AS block_id, b.kind, b.excluded, b.page, s.id AS segment_id, s.text, s.original_text,
               s.bead_id
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
                                              "block_kind": r["kind"], "text": r["text"],
                                              "original": None if r["original_text"] == r["text"] else r["original_text"]})
            last_bead[side] = r["bead_id"]
    undone = {r[0] for r in db.execute("SELECT DISTINCT undone FROM operations WHERE project_id = ?", (book_id,))}
    return {**book, "beads": list(beads.values()), "excluded": excluded,
            "can_undo": 0 in undone, "can_redo": 1 in undone}


@router.get("/books/{book_id}", response_model=BookResponse)
def get_book(book_id: str, db: sqlite3.Connection = Depends(get_db)):
    return _read_book(db, book_id)


def _spans(marked: str) -> list[BookSearchSpan]:
    """Cut a text marked with START/END into plain and matching spans (no markup reaches the page)."""
    spans: list[BookSearchSpan] = []
    match = False
    for k, part in enumerate(marked.replace(END, START).split(START)):
        if k:
            match = not match
        if part:
            spans.append(BookSearchSpan(text=part, match=match))
    return spans


@router.get("/search", response_model=list[BookSearchResult])
def search(
    q: str = "",
    side: Literal["source", "target", "either"] = "either",
    book: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
):
    """Beads matching `q` across all books, or in `book` (SPEC §3.4)."""
    if book is not None:
        _book_row(db, book)
    return [
        BookSearchResult(
            bead_id=hit["bead_id"], book_id=hit["project_id"], title=hit["title"], position=hit["position"],
            source=_spans(hit["source"]), target=_spans(hit["target"]), reviewed=hit["reviewed"],
        )
        for hit in search_beads(db, q, side, project_id=book, limit=limit, offset=offset)
    ]


@router.get("/search/books", response_model=list[BookSearchCount])
def search_counts(
    q: str = "",
    side: Literal["source", "target", "either"] = "either",
    book: str | None = None,
    db: sqlite3.Connection = Depends(get_db),
):
    """The number of beads matching `q` per book, in the order `/search` returns the books."""
    if book is not None:
        _book_row(db, book)
    return [
        BookSearchCount(book_id=hit["project_id"], title=hit["title"], count=hit["count"])
        for hit in count_beads(db, q, side, project_id=book)
    ]


@router.get("/books/{book_id}/beads/{bead_id}/context", response_model=list[ContextBead])
def bead_context(
    book_id: str, bead_id: int, around: int = Query(2, ge=1, le=10), db: sqlite3.Connection = Depends(get_db)
):
    """The bead and up to `around` beads on each side of it, in order (SPEC §3.4, context on demand)."""
    _book_row(db, book_id)
    row = db.execute("SELECT ord FROM beads WHERE id = ? AND project_id = ?", (bead_id, book_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Bead not found")
    ord_ = row["ord"]
    before = db.execute(
        "SELECT id, ord, reviewed FROM beads WHERE project_id = ? AND ord < ? ORDER BY ord DESC LIMIT ?",
        (book_id, ord_, around),
    ).fetchall()[::-1]
    rest = db.execute(
        "SELECT id, ord, reviewed FROM beads WHERE project_id = ? AND ord >= ? ORDER BY ord LIMIT ?",
        (book_id, ord_, around + 1),
    ).fetchall()
    beads = before + rest
    first = db.execute(
        "SELECT COUNT(*) FROM beads WHERE project_id = ? AND ord <= ?", (book_id, beads[0]["ord"])
    ).fetchone()[0]
    out = []
    for k, bead in enumerate(beads):
        texts = _bead_text(db, bead["id"])
        out.append(ContextBead(bead_id=bead["id"], position=first + k, source=texts["source"],
                               target=texts["target"], reviewed=bool(bead["reviewed"])))
    return out


_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# Characters Windows refuses in a file name.
_UNSAFE = re.compile(r'[/\\:*?"<>|]')


def _disposition(name: str) -> str:
    """An attachment named `name`: an ASCII `filename` (other characters as `_`), plus `filename*` when needed."""
    disposition = f'attachment; filename="{name.encode("ascii", "replace").decode().replace("?", "_")}"'
    if not name.isascii():
        disposition += f"; filename*=UTF-8''{quote(name)}"
    return disposition


@router.get("/books/{book_id}/export/edition")
def export_edition(
    book_id: str,
    side: Literal["source", "target"],
    format: Literal["txt", "docx"],
    db: sqlite3.Connection = Depends(get_db),
):
    """One side's text as reviewed, as a download (SPEC §3.5; PLAN.md, "Edition export")."""
    book = _book_row(db, book_id)
    blocks = edition_blocks(db, book_id, side)
    lang = book["source_lang" if side == "source" else "target_lang"].upper()
    disposition = _disposition(f"{_UNSAFE.sub('_', book['title'])} ({lang}).{format}")
    if format == "txt":
        return Response(edition_txt(blocks), media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": disposition})
    return Response(edition_docx(blocks), media_type=_DOCX, headers={"Content-Disposition": disposition})


@router.get("/books/{book_id}/export/bundle")
def export_book_bundle(book_id: str, db: sqlite3.Connection = Depends(get_db)):
    """The book's text layer and alignment as a backup (SPEC §3.5; PLAN.md, "Project bundle")."""
    book = _book_row(db, book_id)
    return Response(export_bundle(db, book_id), media_type="application/zip",
                    headers={"Content-Disposition": _disposition(f"{_UNSAFE.sub('_', book['title'])}.tradurre.zip")})


@router.post("/books/bundle", response_model=BookImportResponse, status_code=201)
async def restore_bundle(bundle: UploadFile, db: sqlite3.Connection = Depends(get_db)):
    """Restore a bundle as a new book."""
    data = await bundle.read()
    try:
        book_id = await run_in_threadpool(import_bundle, db, data)
    except BundleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    book = _book_row(db, book_id)
    bead_count = db.execute("SELECT COUNT(*) FROM beads WHERE project_id = ?", (book_id,)).fetchone()[0]
    return {"id": book_id, "title": book["title"], "bead_count": bead_count, "warnings": []}


@router.get("/books/{book_id}/check", response_model=list[str])
def check_book(book_id: str, db: sqlite3.Connection = Depends(get_db)):
    _book_row(db, book_id)
    return check_project(db, book_id)


@router.get("/books/{book_id}/runs", response_model=list[BookRun])
def get_runs(book_id: str, db: sqlite3.Connection = Depends(get_db)):
    """The book's import (and alignment) runs, newest first, each with its warnings."""
    _book_row(db, book_id)
    runs = [
        {"id": r["id"], "kind": r["kind"], "created_at": r["created_at"], "app_version": r["app_version"],
         "stats": json.loads(r["stats"]), "warnings": []}
        for r in db.execute(
            "SELECT id, kind, created_at, app_version, stats FROM runs WHERE project_id = ? ORDER BY id DESC",
            (book_id,),
        )
    ]
    by_id = {run["id"]: run for run in runs}
    for w in db.execute(
        "SELECT w.run_id, w.side, w.message FROM warnings w JOIN runs r ON r.id = w.run_id "
        "WHERE r.project_id = ? ORDER BY w.id",
        (book_id,),
    ):
        by_id[w["run_id"]]["warnings"].append({"side": w["side"], "message": w["message"]})
    return runs


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


@router.post("/books/{book_id}/beads/realign", response_model=BookResponse)
def realign(book_id: str, body: BookRealignRequest, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: realign_beads(db, book_id, body.first_bead_id, body.last_bead_id))


@router.post("/books/{book_id}/reviewed", response_model=BookResponse)
def reviewed(book_id: str, body: BookReviewedRequest, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: set_reviewed(db, book_id, body.bead_ids, body.reviewed))


@router.post("/books/{book_id}/segments/{segment_id}/edit", response_model=BookResponse)
def edit(book_id: str, segment_id: int, body: BookEditRequest, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: edit_text(db, book_id, segment_id, body.text))


@router.post("/books/{book_id}/segments/{segment_id}/split", response_model=BookResponse)
def split_text(book_id: str, segment_id: int, body: BookSplitSegmentRequest, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: split_segment(db, book_id, segment_id, body.offset))


@router.post("/books/{book_id}/segments/{segment_id}/join-next", response_model=BookResponse)
def join_next(book_id: str, segment_id: int, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: join_with_next(db, book_id, segment_id))


@router.post("/books/{book_id}/segments/{segment_id}/restore", response_model=BookResponse)
def restore(book_id: str, segment_id: int, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: restore_original(db, book_id, segment_id))


@router.post("/books/{book_id}/blocks/{block_id}/exclude", response_model=BookResponse)
def exclude(book_id: str, block_id: int, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: exclude_block(db, book_id, block_id))


@router.post("/books/{book_id}/blocks/{block_id}/include", response_model=BookResponse)
def include(book_id: str, block_id: int, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: include_block(db, book_id, block_id))


@router.post("/books/{book_id}/blocks/exclude-range", response_model=BookResponse)
def exclude_blocks(book_id: str, body: BookRangeRequest, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: exclude_range(db, book_id, body.bead_id, body.side, body.to))


@router.post("/books/{book_id}/blocks/include-range", response_model=BookResponse)
def include_blocks(book_id: str, body: BookRangeRequest, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: include_range(db, book_id, body.bead_id, body.side, body.to))


@router.post("/books/{book_id}/undo", response_model=BookResponse)
def undo(book_id: str, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: history.undo(db, book_id), nothing="Nothing to undo")


@router.post("/books/{book_id}/redo", response_model=BookResponse)
def redo(book_id: str, db: sqlite3.Connection = Depends(get_db)):
    return _correct(db, book_id, lambda: history.redo(db, book_id), nothing="Nothing to redo")
