"""Structured extraction: files in, kinded blocks out (SPEC §3.1 step 2; PLAN.md, "Structured extraction").

One block is one paragraph-like unit; splitting into sentences comes later. `doc_adapter` stays the v0.1 import's
extractor; this module only borrows its cleanup.
"""

import re
from dataclasses import dataclass, field
from io import BytesIO

from tradurre.services.doc_adapter import normalize_ocr_artifacts

# Block kinds the import excludes by default (SPEC §2: not aligned, not searched, revealable).
EXCLUDED_KINDS = {"running_head", "page_number", "footnote", "front_matter", "back_matter"}


@dataclass
class ExtractedBlock:
    kind: str  # one of the kinds in the `blocks` schema
    text: str
    page: int | None = None  # 1-based logical page, PDF only


@dataclass
class Extraction:
    blocks: list[ExtractedBlock]
    warnings: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    """Cleanup shared by every format: OCR artifacts, then whitespace runs collapsed to one space."""
    return re.sub(r"\s+", " ", normalize_ocr_artifacts(text)).strip()


def _extract_txt(content: bytes) -> Extraction:
    warnings: list[str] = []
    try:
        text = content.decode("utf-8-sig")  # drops a byte-order mark, if any
    except UnicodeDecodeError:
        warnings.append("The text file is not valid UTF-8; it was read as Latin-1.")
        text = content.decode("latin-1")
    lines = text.splitlines()
    filled = [i for i, line in enumerate(lines) if line.strip()]
    if filled and any(not line.strip() for line in lines[filled[0]:filled[-1]]):
        # Paragraphs separated by blank lines; the lines inside one are wrapped text.
        chunks: list[list[str]] = [[]]
        for line in lines:
            if line.strip():
                chunks[-1].append(line)
            elif chunks[-1]:
                chunks.append([])
        texts = [" ".join(chunk) for chunk in chunks]
    else:
        texts = lines
    blocks = [ExtractedBlock("paragraph", cleaned) for t in texts if (cleaned := _clean(t))]
    return Extraction(blocks, warnings)


def _extract_docx(content: bytes) -> Extraction:
    from docx import Document

    blocks: list[ExtractedBlock] = []
    for paragraph in Document(BytesIO(content)).paragraphs:
        text = _clean(paragraph.text)
        if not text:
            continue
        style = paragraph.style.name if paragraph.style is not None else ""
        kind = "heading" if (style or "").startswith(("Heading", "Title")) else "paragraph"
        blocks.append(ExtractedBlock(kind, text))
    return Extraction(blocks)


def extract(filename: str, content: bytes) -> Extraction:
    """Extract the blocks of a .txt, .docx or .pdf file, in reading order."""
    name = (filename or "").lower()
    if name.endswith(".txt"):
        return _extract_txt(content)
    if name.endswith(".docx"):
        return _extract_docx(content)
    if name.endswith(".pdf"):
        raise NotImplementedError("PDF extraction is not implemented yet")
    raise ValueError(f"Unsupported file type: {filename!r} (expected .txt, .docx or .pdf)")
