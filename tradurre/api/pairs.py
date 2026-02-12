import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from tradurre.models import PairCreate, PairResponse, PairSplitRequest, PairUpdate
from tradurre.services.html_utils import strip_html

router = APIRouter(tags=["pairs"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/projects/{project_id}/pairs", response_model=list[PairResponse])
def list_pairs(project_id: str, request: Request):
    db = request.app.state.db
    proj = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    rows = db.execute(
        "SELECT * FROM pairs WHERE project_id = ? ORDER BY position",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/projects/{project_id}/pairs", response_model=PairResponse, status_code=201)
def create_pair(project_id: str, pair: PairCreate, request: Request):
    db = request.app.state.db
    proj = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    if pair.position is not None:
        position = pair.position
        # Shift existing pairs at or after this position.
        # Two-step via negative values to avoid UNIQUE constraint violations
        # (SQLite checks per-row, so direct +1 can collide with the next row).
        db.execute(
            "UPDATE pairs SET position = -(position + 1) WHERE project_id = ? AND position >= ?",
            (project_id, position),
        )
        db.execute(
            "UPDATE pairs SET position = -position WHERE project_id = ? AND position < 0",
            (project_id,),
        )
    else:
        row = db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 as next_pos FROM pairs WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        position = row["next_pos"]

    pair_id = str(uuid.uuid4())
    now = _now()
    source_text = pair.source_text or strip_html(pair.source_html)
    target_text = pair.target_text or strip_html(pair.target_html)

    db.execute(
        """INSERT INTO pairs (id, project_id, position, source_html, target_html, source_text, target_text, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
        (pair_id, project_id, position, pair.source_html, pair.target_html, source_text, target_text, now, now),
    )
    db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
    db.commit()

    return dict(db.execute("SELECT * FROM pairs WHERE id = ?", (pair_id,)).fetchone())


@router.put("/pairs/{pair_id}", response_model=PairResponse)
def update_pair(pair_id: str, update: PairUpdate, request: Request):
    db = request.app.state.db
    existing = db.execute("SELECT * FROM pairs WHERE id = ?", (pair_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Pair not found")

    now = _now()
    fields: dict[str, str] = {"updated_at": now}

    if update.source_html is not None:
        fields["source_html"] = update.source_html
        fields["source_text"] = strip_html(update.source_html)
    if update.target_html is not None:
        fields["target_html"] = update.target_html
        fields["target_text"] = strip_html(update.target_html)
    if update.status is not None:
        fields["status"] = update.status

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [pair_id]
    db.execute(f"UPDATE pairs SET {set_clause} WHERE id = ?", values)
    db.execute(
        "UPDATE projects SET updated_at = ? WHERE id = ?",
        (now, existing["project_id"]),
    )
    db.commit()

    return dict(db.execute("SELECT * FROM pairs WHERE id = ?", (pair_id,)).fetchone())


@router.delete("/pairs/{pair_id}", status_code=204)
def delete_pair(pair_id: str, request: Request):
    db = request.app.state.db
    existing = db.execute("SELECT * FROM pairs WHERE id = ?", (pair_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Pair not found")

    project_id = existing["project_id"]
    position = existing["position"]

    db.execute("DELETE FROM pairs WHERE id = ?", (pair_id,))
    # Close the gap in positions (two-step via negatives to avoid UNIQUE violations)
    db.execute(
        "UPDATE pairs SET position = -(position - 1) WHERE project_id = ? AND position > ?",
        (project_id, position),
    )
    db.execute(
        "UPDATE pairs SET position = -position WHERE project_id = ? AND position < 0",
        (project_id,),
    )
    db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_now(), project_id))
    db.commit()


@router.post("/pairs/{pair_id}/split", response_model=PairResponse, status_code=201)
def split_pair(pair_id: str, body: PairSplitRequest, request: Request):
    db = request.app.state.db
    existing = db.execute("SELECT * FROM pairs WHERE id = ?", (pair_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Pair not found")

    project_id = existing["project_id"]
    position = existing["position"]
    now = _now()

    # Update existing pair with "before" content
    db.execute(
        "UPDATE pairs SET source_html = ?, target_html = ?, source_text = ?, target_text = ?, updated_at = ? WHERE id = ?",
        (body.source_html_before, body.target_html_before,
         strip_html(body.source_html_before), strip_html(body.target_html_before), now, pair_id),
    )

    # Shift pairs after this position (two-step via negatives to avoid UNIQUE violations)
    db.execute(
        "UPDATE pairs SET position = -(position + 1) WHERE project_id = ? AND position > ?",
        (project_id, position),
    )
    db.execute(
        "UPDATE pairs SET position = -position WHERE project_id = ? AND position < 0",
        (project_id,),
    )

    # Create new pair at position + 1 with "after" content
    new_id = str(uuid.uuid4())
    db.execute(
        """INSERT INTO pairs (id, project_id, position, source_html, target_html, source_text, target_text, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
        (new_id, project_id, position + 1, body.source_html_after, body.target_html_after,
         strip_html(body.source_html_after), strip_html(body.target_html_after), now, now),
    )

    db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
    db.commit()

    return dict(db.execute("SELECT * FROM pairs WHERE id = ?", (new_id,)).fetchone())


@router.post("/pairs/{pair_id}/merge", response_model=PairResponse)
def merge_pair(pair_id: str, request: Request):
    db = request.app.state.db
    existing = db.execute("SELECT * FROM pairs WHERE id = ?", (pair_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Pair not found")

    project_id = existing["project_id"]
    position = existing["position"]

    next_pair = db.execute(
        "SELECT * FROM pairs WHERE project_id = ? AND position = ?",
        (project_id, position + 1),
    ).fetchone()
    if not next_pair:
        raise HTTPException(status_code=400, detail="No next pair to merge with")

    now = _now()
    merged_source = existing["source_html"] + next_pair["source_html"]
    merged_target = existing["target_html"] + next_pair["target_html"]

    db.execute(
        "UPDATE pairs SET source_html = ?, target_html = ?, source_text = ?, target_text = ?, updated_at = ? WHERE id = ?",
        (merged_source, merged_target, strip_html(merged_source), strip_html(merged_target), now, pair_id),
    )

    db.execute("DELETE FROM pairs WHERE id = ?", (next_pair["id"],))
    # Close the gap (two-step via negatives to avoid UNIQUE violations)
    db.execute(
        "UPDATE pairs SET position = -(position - 1) WHERE project_id = ? AND position > ?",
        (project_id, position + 1),
    )
    db.execute(
        "UPDATE pairs SET position = -position WHERE project_id = ? AND position < 0",
        (project_id,),
    )
    db.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
    db.commit()

    return dict(db.execute("SELECT * FROM pairs WHERE id = ?", (pair_id,)).fetchone())
