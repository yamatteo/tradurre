import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from tradurre.models import ImportParagraph, ProjectResponse
from tradurre.services.importer import extract_paragraphs_docx, extract_paragraphs_txt

router = APIRouter(tags=["import"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract(file: UploadFile, content: bytes) -> list[ImportParagraph]:
    name = (file.filename or "").lower()
    if name.endswith(".docx"):
        return extract_paragraphs_docx(content)
    elif name.endswith(".txt"):
        return extract_paragraphs_txt(content)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {name}")


class ImportPreviewResponse(BaseModel):
    source_paragraphs: list[ImportParagraph]
    target_paragraphs: list[ImportParagraph]


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def import_preview(source_file: UploadFile, target_file: UploadFile):
    source_bytes = await source_file.read()
    target_bytes = await target_file.read()

    source_paragraphs = _extract(source_file, source_bytes)
    target_paragraphs = _extract(target_file, target_bytes)

    return ImportPreviewResponse(
        source_paragraphs=source_paragraphs,
        target_paragraphs=target_paragraphs,
    )


class ImportConfirmRequest(BaseModel):
    title: str
    source_lang: str
    target_lang: str
    pairs: list[dict]  # [{source_html, target_html, source_text, target_text}]


@router.post("/import/confirm", response_model=ProjectResponse, status_code=201)
def import_confirm(body: ImportConfirmRequest, request: Request):
    db = request.app.state.db
    project_id = str(uuid.uuid4())
    now = _now()

    db.execute(
        "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, body.title, body.source_lang, body.target_lang, now, now),
    )

    for i, pair in enumerate(body.pairs):
        pair_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO pairs (id, project_id, position, source_html, target_html, source_text, target_text, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
            (
                pair_id,
                project_id,
                i,
                pair.get("source_html", ""),
                pair.get("target_html", ""),
                pair.get("source_text", ""),
                pair.get("target_text", ""),
                now,
                now,
            ),
        )

    db.commit()

    return {
        "id": project_id,
        "title": body.title,
        "source_lang": body.source_lang,
        "target_lang": body.target_lang,
        "created_at": now,
        "updated_at": now,
        "pair_count": len(body.pairs),
    }
