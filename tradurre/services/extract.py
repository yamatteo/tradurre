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


@dataclass
class _Line:
    """One text line of a PDF, on a logical page (a two-up spread's half counts as its own page)."""

    page: int  # 0-based logical page
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    size: float  # the largest span size in the line


def _page_lines(page) -> list[_Line]:
    """The page's non-blank lines, in PyMuPDF's order, with `page` still unset (0)."""
    lines: list[_Line] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = line["spans"]
            text = "".join(span["text"] for span in spans)
            if not text.strip():
                continue
            x0, y0, x1, y1 = line["bbox"]
            lines.append(_Line(0, x0, y0, x1, y1, text, max(span["size"] for span in spans)))
    return lines


def _looks_two_up(lines: list[_Line], width: float) -> bool:
    """At least 20% of the lines are centred left of the middle and at least 20% right of it."""
    left = sum(1 for line in lines if (line.x0 + line.x1) / 2 < width / 2)
    return left >= 0.2 * len(lines) and len(lines) - left >= 0.2 * len(lines)


def _pdf_lines(doc) -> tuple[list[_Line], list[tuple[float, float]]]:
    """The lines of every logical page in reading order, and each logical page's (width, height).

    Two-up spreads are decided once per document: if at least 60% of the landscape pages with text look two-up,
    every landscape page is split at its middle into two logical pages (even a blank or one-column one).
    """
    pages = [(page.rect.width, page.rect.height, _page_lines(page)) for page in doc]
    landscape = [(w, lines) for w, h, lines in pages if w > h and lines]
    two_up = bool(landscape) and sum(_looks_two_up(lines, w) for w, lines in landscape) >= 0.6 * len(landscape)

    out: list[_Line] = []
    sizes: list[tuple[float, float]] = []
    for width, height, lines in pages:
        if two_up and width > height:
            half = width / 2
            left = [line for line in lines if (line.x0 + line.x1) / 2 < half]
            right = [line for line in lines if (line.x0 + line.x1) / 2 >= half]
            for line in right:
                line.x0 -= half
                line.x1 -= half
            groups = [left, right]
            sizes += [(half, height), (half, height)]
        else:
            groups = [lines]
            sizes.append((width, height))
        for offset, group in enumerate(groups):
            number = len(sizes) - len(groups) + offset
            for line in sorted(group, key=lambda line: (line.y0, line.x0)):
                line.page = number
                out.append(line)
    return out, sizes


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
