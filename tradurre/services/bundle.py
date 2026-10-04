"""Project bundle (SPEC §3.5; PLAN.md, "Project bundle"): one book's text layer and alignment as a full backup.

A bundle is a zip holding one `bundle.json`. It stores no ids and no ords: order is list order, and a segment names
its bead by its index in `beads`. The operation history is not included: a restored book starts with nothing to undo.
Import always creates a new book, in one transaction, refused whole if the bundle is malformed or breaks an invariant;
restored next to a book with the same title, it is titled "<title> (restored YYYY-MM-DD)"; it keeps its creation
date, but counts as worked on now, so it tops the library.
"""

import io
import json
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from importlib.metadata import version

from tradurre.domain.history import transaction
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import GAP

FORMAT = "tradurre-bundle"
VERSION = 1
_NAME = "bundle.json"


class BundleError(ValueError):
    """A bundle that can't be restored; the message is for the translator."""


def export_bundle(conn: sqlite3.Connection, book_id: str) -> bytes:
    book = conn.execute(
        "SELECT title, source_lang, target_lang, created_at, updated_at FROM projects WHERE id = ?", (book_id,)
    ).fetchone()
    bead_ids = [r["id"] for r in conn.execute("SELECT id FROM beads WHERE project_id = ? ORDER BY ord", (book_id,))]
    index = {bead_id: k for k, bead_id in enumerate(bead_ids)}
    beads = [
        {"confidence": r["confidence"], "method": r["method"], "reviewed": bool(r["reviewed"])}
        for r in conn.execute(
            "SELECT confidence, method, reviewed FROM beads WHERE project_id = ? ORDER BY ord", (book_id,)
        )
    ]
    documents = []
    for doc in conn.execute(
        "SELECT id, side, filename, format FROM documents WHERE project_id = ? "
        "ORDER BY CASE side WHEN 'source' THEN 0 ELSE 1 END",
        (book_id,),
    ).fetchall():
        blocks = []
        for block in conn.execute(
            "SELECT id, kind, excluded, page FROM blocks WHERE document_id = ? ORDER BY ord", (doc["id"],)
        ).fetchall():
            segments = [
                {"text": s["text"], "original_text": s["original_text"],
                 "bead": None if s["bead_id"] is None else index[s["bead_id"]]}
                for s in conn.execute(
                    "SELECT text, original_text, bead_id FROM segments WHERE block_id = ? ORDER BY ord", (block["id"],)
                )
            ]
            blocks.append({"kind": block["kind"], "excluded": bool(block["excluded"]), "page": block["page"],
                           "segments": segments})
        documents.append({"side": doc["side"], "filename": doc["filename"], "format": doc["format"], "blocks": blocks})
    runs = []
    for run in conn.execute(
        "SELECT id, kind, created_at, app_version, stats FROM runs WHERE project_id = ? ORDER BY id", (book_id,)
    ).fetchall():
        warnings = [
            {"side": w["side"], "message": w["message"]}
            for w in conn.execute("SELECT side, message FROM warnings WHERE run_id = ? ORDER BY id", (run["id"],))
        ]
        runs.append({"kind": run["kind"], "created_at": run["created_at"], "app_version": run["app_version"],
                     "stats": json.loads(run["stats"]), "warnings": warnings})
    bundle = {
        "format": FORMAT,
        "version": VERSION,
        "app_version": version("tradurre"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "book": dict(book),
        "documents": documents,
        "beads": beads,
        "runs": runs,
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(_NAME, json.dumps(bundle, ensure_ascii=False))
    return out.getvalue()


def _field(obj: object, key: str, kind: type | tuple[type, ...], path: str, nullable: bool = False):
    """`obj[key]` checked against `kind` (bools are not numbers), or BundleError naming its path."""
    if not isinstance(obj, dict) or key not in obj:
        raise BundleError(f"Malformed bundle: {path}.{key} is missing")
    value = obj[key]
    if value is None and nullable:
        return None
    kinds = kind if isinstance(kind, tuple) else (kind,)
    if not isinstance(value, kinds) or (isinstance(value, bool) and bool not in kinds):
        raise BundleError(f"Malformed bundle: {path}.{key} has the wrong type")
    return value


def _read(data: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            raw = z.read(_NAME)
    except (zipfile.BadZipFile, KeyError):
        raise BundleError("Not a Tradurre bundle")
    try:
        bundle = json.loads(raw)
    except ValueError:
        raise BundleError("Not a Tradurre bundle")
    if not isinstance(bundle, dict) or bundle.get("format") != FORMAT:
        raise BundleError("Not a Tradurre bundle")
    found = _field(bundle, "version", int, "bundle")
    if found > VERSION:
        raise BundleError(f"This bundle needs a newer Tradurre (version {found})")
    return bundle


def import_bundle(conn: sqlite3.Connection, data: bytes) -> str:
    """Restore the bundle as a new book; return its id."""
    bundle = _read(data)
    book = _field(bundle, "book", dict, "bundle")
    beads = _field(bundle, "beads", list, "bundle")
    documents = _field(bundle, "documents", list, "bundle")
    runs = _field(bundle, "runs", list, "bundle")
    book_id = str(uuid.uuid4())
    try:
        with transaction(conn):
            title = _field(book, "title", str, "book")
            if conn.execute(
                "SELECT 1 FROM projects p WHERE p.title = ? "
                "AND EXISTS (SELECT 1 FROM documents d WHERE d.project_id = p.id)",
                (title,),
            ).fetchone():
                title = f"{title} (restored {datetime.now(timezone.utc).date().isoformat()})"
            conn.execute(
                "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (book_id, title, *(_field(book, key, str, "book")
                                   for key in ("source_lang", "target_lang", "created_at")),
                 datetime.now(timezone.utc).isoformat()),
            )
            bead_ids = []
            for k, bead in enumerate(beads):
                path = f"beads[{k}]"
                bead_ids.append(conn.execute(
                    "INSERT INTO beads (project_id, ord, confidence, method, reviewed) VALUES (?, ?, ?, ?, ?)",
                    (book_id, k * GAP, _field(bead, "confidence", (int, float), path),
                     _field(bead, "method", str, path), int(_field(bead, "reviewed", bool, path))),
                ).lastrowid)
            for d, doc in enumerate(documents):
                path = f"documents[{d}]"
                document_id = conn.execute(
                    "INSERT INTO documents (project_id, side, filename, format) VALUES (?, ?, ?, ?)",
                    (book_id, *(_field(doc, key, str, path) for key in ("side", "filename", "format"))),
                ).lastrowid
                for b, block in enumerate(_field(doc, "blocks", list, path)):
                    block_path = f"{path}.blocks[{b}]"
                    block_id = conn.execute(
                        "INSERT INTO blocks (document_id, ord, kind, excluded, page) VALUES (?, ?, ?, ?, ?)",
                        (document_id, b * GAP, _field(block, "kind", str, block_path),
                         int(_field(block, "excluded", bool, block_path)),
                         _field(block, "page", int, block_path, nullable=True)),
                    ).lastrowid
                    for s, segment in enumerate(_field(block, "segments", list, block_path)):
                        segment_path = f"{block_path}.segments[{s}]"
                        bead = _field(segment, "bead", int, segment_path, nullable=True)
                        if bead is not None and not 0 <= bead < len(bead_ids):
                            raise BundleError(f"Malformed bundle: {segment_path}.bead is out of range")
                        conn.execute(
                            "INSERT INTO segments (block_id, ord, text, original_text, bead_id) VALUES (?, ?, ?, ?, ?)",
                            (block_id, s * GAP, _field(segment, "text", str, segment_path),
                             _field(segment, "original_text", str, segment_path),
                             None if bead is None else bead_ids[bead]),
                        )
            for r, run in enumerate(runs):
                path = f"runs[{r}]"
                run_id = conn.execute(
                    "INSERT INTO runs (project_id, kind, created_at, app_version, stats) VALUES (?, ?, ?, ?, ?)",
                    (book_id, _field(run, "kind", str, path), _field(run, "created_at", str, path),
                     _field(run, "app_version", str, path), json.dumps(_field(run, "stats", dict, path))),
                ).lastrowid
                for w, warning in enumerate(_field(run, "warnings", list, path)):
                    warning_path = f"{path}.warnings[{w}]"
                    conn.execute(
                        "INSERT INTO warnings (run_id, side, message) VALUES (?, ?, ?)",
                        (run_id, _field(warning, "side", str, warning_path, nullable=True),
                         _field(warning, "message", str, warning_path)),
                    )
            errors = check_project(conn, book_id)
            if errors:
                raise BundleError(f"Malformed bundle: {errors[0]}")
    except sqlite3.IntegrityError as e:
        # A value the schema refuses (an unknown kind, side or method, a second document for a side…).
        raise BundleError(f"Malformed bundle: {e}")
    return book_id
