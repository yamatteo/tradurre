import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from tradurre.db import get_db
from tradurre.models import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(tags=["projects"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        """
        SELECT p.*, COALESCE(c.cnt, 0) as pair_count
        FROM projects p
        LEFT JOIN (SELECT project_id, COUNT(*) as cnt FROM pairs GROUP BY project_id) c
            ON c.project_id = p.id
        ORDER BY p.updated_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(project: ProjectCreate, db: sqlite3.Connection = Depends(get_db)):
    project_id = str(uuid.uuid4())
    now = _now()
    with db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, project.title, project.source_lang, project.target_lang, now, now),
        )
    return {
        "id": project_id,
        "title": project.title,
        "source_lang": project.source_lang,
        "target_lang": project.target_lang,
        "created_at": now,
        "updated_at": now,
        "pair_count": 0,
    }


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute(
        """
        SELECT p.*, COALESCE(c.cnt, 0) as pair_count
        FROM projects p
        LEFT JOIN (SELECT project_id, COUNT(*) as cnt FROM pairs GROUP BY project_id) c
            ON c.project_id = p.id
        WHERE p.id = ?
        """,
        (project_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return dict(row)


@router.put("/projects/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, update: ProjectUpdate, db: sqlite3.Connection = Depends(get_db)):
    with db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Project not found")

        fields = {}
        if update.title is not None:
            fields["title"] = update.title
        if update.source_lang is not None:
            fields["source_lang"] = update.source_lang
        if update.target_lang is not None:
            fields["target_lang"] = update.target_lang

        if fields:
            fields["updated_at"] = _now()
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            values = list(fields.values()) + [project_id]
            db.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", values)

    return get_project(project_id, db)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, db: sqlite3.Connection = Depends(get_db)):
    with db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Project not found")
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
