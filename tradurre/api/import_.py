import uuid
from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel, ValidationError

from tradurre.models import (
    AlignedArtifact,
    ImportArtifactResponse,
    ImportParagraph,
    ImportParagraphsRequest,
    ImportParagraphsResponse,
    ImportSectionsResponse,
    ImportSentencesRequest,
    ImportSentencesResponse,
    ImportUnit,
    ProjectResponse,
)
from tradurre.services import doc_adapter
from tradurre.services.aligner import (
    _align_units,
    _boundary_optimize,
    extract_hierarchy,
    find_anchors,
    align,
    split_sentences,
)
from tradurre.services.artifact_io import parse_artifact
from tradurre.services.importer import (
    extract_and_align_txt,
    extract_paragraphs_docx,
    extract_paragraphs_txt,
)

router = APIRouter(tags=["import"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract(file: UploadFile, content: bytes) -> list[ImportParagraph]:
    from tradurre.services.importer import extract_paragraphs_pdf

    name = (file.filename or "").lower()
    if name.endswith(".docx"):
        return extract_paragraphs_docx(content)
    elif name.endswith(".txt"):
        return extract_paragraphs_txt(content)
    elif name.endswith(".pdf"):
        return extract_paragraphs_pdf(content)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {name}")


# ---------------------------------------------------------------------------
# Legacy preview endpoint (kept for backward compatibility)
# ---------------------------------------------------------------------------

class ImportPreviewResponse(BaseModel):
    source_paragraphs: list[ImportParagraph]
    target_paragraphs: list[ImportParagraph]


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def import_preview(source_file: UploadFile, target_file: UploadFile):
    source_bytes = await source_file.read()
    target_bytes = await target_file.read()

    source_name = (source_file.filename or "").lower()
    target_name = (target_file.filename or "").lower()

    if source_name.endswith(".txt") and target_name.endswith(".txt"):
        source_paragraphs, target_paragraphs = extract_and_align_txt(
            source_bytes, target_bytes
        )
    else:
        try:
            source_paragraphs = _extract(source_file, source_bytes)
            target_paragraphs = _extract(target_file, target_bytes)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return ImportPreviewResponse(
        source_paragraphs=source_paragraphs,
        target_paragraphs=target_paragraphs,
    )


# ---------------------------------------------------------------------------
# Step 1: Upload → section-level alignment
# ---------------------------------------------------------------------------

@router.post("/import/sections", response_model=ImportSectionsResponse)
async def import_sections(source_file: UploadFile, target_file: UploadFile):
    """Upload files and return section-level aligned preview."""
    source_bytes = await source_file.read()
    target_bytes = await target_file.read()

    try:
        source_text = doc_adapter.load_as_text(source_file.filename or "", source_bytes)
        target_text = doc_adapter.load_as_text(target_file.filename or "", target_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    source_h = extract_hierarchy(source_text)
    target_h = extract_hierarchy(target_text)

    # Flatten each section to a single string for alignment
    source_texts = [
        " ".join(s for p in sec for s in p) for sec in source_h
    ]
    target_texts = [
        " ".join(s for p in sec for s in p) for sec in target_h
    ]

    aligned = _align_units(source_texts, target_texts)

    source_sections = []
    target_sections = []
    for i, (src, tgt) in enumerate(aligned):
        source_sections.append(ImportUnit(
            html=f"<p>{escape(src)}</p>" if src else "<p></p>",
            text=src,
            index=i,
        ))
        target_sections.append(ImportUnit(
            html=f"<p>{escape(tgt)}</p>" if tgt else "<p></p>",
            text=tgt,
            index=i,
        ))

    return ImportSectionsResponse(
        source_sections=source_sections,
        target_sections=target_sections,
    )


# ---------------------------------------------------------------------------
# Step 2: Confirmed sections → paragraph-level alignment
# ---------------------------------------------------------------------------

@router.post("/import/paragraphs", response_model=ImportParagraphsResponse)
def import_paragraphs(body: ImportParagraphsRequest):
    """Split confirmed section pairs into paragraph-level alignment."""
    source_paragraphs: list[ImportUnit] = []
    target_paragraphs: list[ImportUnit] = []

    for section_idx, section in enumerate(body.sections):
        src_text = section.get("source_text", "")
        tgt_text = section.get("target_text", "")

        # Extract paragraphs from each section's text
        src_h = extract_hierarchy(src_text)
        tgt_h = extract_hierarchy(tgt_text)

        # Flatten to paragraph level (hierarchy may have 1 section)
        src_paras = [" ".join(p) for sec in src_h for p in sec]
        tgt_paras = [" ".join(p) for sec in tgt_h for p in sec]

        # Align paragraphs using anchors
        aligned = _align_units(src_paras, tgt_paras)

        # Boundary optimization (as list of sentence-list pairs)
        # For paragraph level, we pass paragraph texts as single-element lists
        para_pairs = [(
            [src] if src else [],
            [tgt] if tgt else [],
        ) for src, tgt in aligned]
        para_pairs = _boundary_optimize(para_pairs)

        for para_idx, (src_list, tgt_list) in enumerate(para_pairs):
            src = src_list[0] if src_list else ""
            tgt = tgt_list[0] if tgt_list else ""
            source_paragraphs.append(ImportUnit(
                html=f"<p>{escape(src)}</p>" if src else "<p></p>",
                text=src,
                index=para_idx,
                section=section_idx,
            ))
            target_paragraphs.append(ImportUnit(
                html=f"<p>{escape(tgt)}</p>" if tgt else "<p></p>",
                text=tgt,
                index=para_idx,
                section=section_idx,
            ))

    return ImportParagraphsResponse(
        source_paragraphs=source_paragraphs,
        target_paragraphs=target_paragraphs,
    )


# ---------------------------------------------------------------------------
# Step 3: Confirmed paragraphs → sentence-level alignment
# ---------------------------------------------------------------------------

@router.post("/import/sentences", response_model=ImportSentencesResponse)
def import_sentences(body: ImportSentencesRequest):
    """Split confirmed paragraph pairs into sentence-level alignment."""
    source_sentences: list[ImportUnit] = []
    target_sentences: list[ImportUnit] = []

    for para in body.paragraphs:
        src_text = para.get("source_text", "")
        tgt_text = para.get("target_text", "")
        section_idx = para.get("section", 0)
        para_idx = para.get("paragraph", 0)

        src_sents = split_sentences(src_text) if src_text.strip() else []
        tgt_sents = split_sentences(tgt_text) if tgt_text.strip() else []

        aligned = _align_units(src_sents, tgt_sents)

        for src, tgt in aligned:
            source_sentences.append(ImportUnit(
                html=f"<p>{escape(src)}</p>" if src else "<p></p>",
                text=src,
                section=section_idx,
                paragraph=para_idx,
            ))
            target_sentences.append(ImportUnit(
                html=f"<p>{escape(tgt)}</p>" if tgt else "<p></p>",
                text=tgt,
                section=section_idx,
                paragraph=para_idx,
            ))

    return ImportSentencesResponse(
        source_sentences=source_sentences,
        target_sentences=target_sentences,
    )


# ---------------------------------------------------------------------------
# Final confirm: create project with section/paragraph metadata
# ---------------------------------------------------------------------------

class ImportConfirmRequest(BaseModel):
    title: str
    source_lang: str
    target_lang: str
    pairs: list[dict]  # [{source_html, target_html, source_text, target_text, section, paragraph}]


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
            """INSERT INTO pairs (id, project_id, position, section, paragraph,
            source_html, target_html, source_text, target_text, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
            (
                pair_id,
                project_id,
                i,
                pair.get("section", 0),
                pair.get("paragraph", 0),
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


# ---------------------------------------------------------------------------
# Import a pre-aligned artifact (produced externally, e.g. by the Colab
# embedding/LLM pipeline in tradurre.services.pipeline). Flattens the
# artifact's section/paragraph/sentence hierarchy into the same shape the
# text-file wizard's sentence-review step produces, so it reuses the existing
# review-then-/import/confirm flow rather than a parallel project-creation path.
# ---------------------------------------------------------------------------

@router.post("/import/artifact", response_model=ImportArtifactResponse)
async def import_artifact(artifact_file: UploadFile):
    raw = await artifact_file.read()

    try:
        artifact: AlignedArtifact = parse_artifact(raw)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Invalid artifact: {e}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    source_sentences: list[ImportUnit] = []
    target_sentences: list[ImportUnit] = []

    for section_idx, section in enumerate(artifact.sections):
        for para_idx, paragraph in enumerate(section.paragraphs):
            for sentence in paragraph.sentences:
                source_sentences.append(ImportUnit(
                    html=f"<p>{escape(sentence.source_text)}</p>" if sentence.source_text else "<p></p>",
                    text=sentence.source_text,
                    section=section_idx,
                    paragraph=para_idx,
                    confidence=sentence.confidence,
                    method=sentence.method,
                    flags=sentence.flags,
                ))
                target_sentences.append(ImportUnit(
                    html=f"<p>{escape(sentence.target_text)}</p>" if sentence.target_text else "<p></p>",
                    text=sentence.target_text,
                    section=section_idx,
                    paragraph=para_idx,
                    confidence=sentence.confidence,
                    method=sentence.method,
                    flags=sentence.flags,
                ))

    return ImportArtifactResponse(
        title=artifact.title,
        source_lang=artifact.source_lang,
        target_lang=artifact.target_lang,
        source_sentences=source_sentences,
        target_sentences=target_sentences,
        warnings=artifact.warnings,
        stats=artifact.stats,
    )

    return {
        "id": project_id,
        "title": body.title,
        "source_lang": body.source_lang,
        "target_lang": body.target_lang,
        "created_at": now,
        "updated_at": now,
        "pair_count": len(body.pairs),
    }
