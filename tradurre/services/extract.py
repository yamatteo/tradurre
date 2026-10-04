"""Structured extraction: files in, kinded blocks out (SPEC §3.1 step 2; PLAN.md, "Structured extraction").

One block is one paragraph-like unit; splitting into sentences comes later.
"""

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from io import BytesIO

_LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}

# Control characters other than \n and \t, which OCR/PDF extraction sometimes emits.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_ocr_artifacts(text: str) -> str:
    """Conservative cleanup for OCR/PDF-extracted text.

    Only touches whitespace, control characters, and typographic ligatures --
    never rewords or reflows actual content.
    """
    for lig, plain in _LIGATURES.items():
        text = text.replace(lig, plain)
    text = _CONTROL_CHARS.sub("", text)
    # Collapse runs of horizontal whitespace (not newlines) without touching line structure.
    text = re.sub(r"[ \t]+", " ", text)
    return text


# PDF support (pymupdf) failed to load, as on a Windows without the runtime its DLL needs (PLAN.md, "PDF support that
# can't load: a clear message").
PDF_RUNTIME_MISSING = (
    "PDF support can't load on this computer. Install the Microsoft Visual C++ Redistributable "
    "(https://aka.ms/vs/17/release/vc_redist.x64.exe), then restart Tradurre. Text and Word files still work."
)

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


_PAGE_NUMBER = re.compile(r"^\s*([0-9]+|[ivxlcdm]+)\s*$", re.IGNORECASE)
# Case-sensitive: lower-case Roman numerals would catch Italian words ("di", "mi", "vi") wrapped alone on a line.
_CHAPTER_NUMBER = re.compile(r"^\s*([0-9]+|[IVXLC]+)\s*$")
_BAND = 0.15  # top/bottom band, as a share of the page height, measured on the line's vertical centre
_FREQUENT_SLOT = 0.25  # page numbers sit in the same (band, size) slot on at least this share of logical pages


def _band(line: _Line, height: float) -> str | None:
    centre = (line.y0 + line.y1) / 2
    if centre <= _BAND * height:
        return "top"
    if centre >= (1 - _BAND) * height:
        return "bottom"
    return None


def _classify(lines: list[_Line], sizes: list[tuple[float, float]], body_size: float) -> list[str]:
    """The kind of every line: page_number, running_head, heading, footnote or paragraph."""
    bands = [_band(line, sizes[line.page][1]) for line in lines]

    slots: dict[tuple[str, int], set[int]] = defaultdict(set)
    for line, band in zip(lines, bands):
        if band and line.size <= body_size + 0.5 and _PAGE_NUMBER.match(line.text):
            slots[(band, round(line.size))].add(line.page)
    frequent = {slot for slot, pages in slots.items() if len(pages) >= _FREQUENT_SLOT * len(sizes)}

    def head_key(line: _Line) -> str:
        return re.sub(r"\d", "", line.text).casefold().strip()

    head_pages: dict[str, set[int]] = defaultdict(set)
    for line, band in zip(lines, bands):
        if band == "top" and head_key(line):
            head_pages[head_key(line)].add(line.page)

    kinds: list[str] = []
    for line, band in zip(lines, bands):
        height = sizes[line.page][1]
        if band and (band, round(line.size)) in frequent and _PAGE_NUMBER.match(line.text):
            kinds.append("page_number")
        elif band == "top" and head_key(line) and len(head_pages[head_key(line)]) >= 3:
            kinds.append("running_head")
        elif line.size >= body_size * 1.1 or _CHAPTER_NUMBER.match(line.text):
            kinds.append("heading")
        elif line.size <= body_size * 0.9 and (line.y0 + line.y1) / 2 >= 0.6 * height:
            kinds.append("footnote")
        else:
            kinds.append("paragraph")
    return kinds


def _join_lines(texts: list[str]) -> str:
    """Join a block's lines: soft hyphens vanish, a hard hyphen after a letter is kept, otherwise one space."""
    out = ""
    for text in texts:
        text = text.rstrip()
        if not out:
            out = text
        elif out.endswith("\u00ad"):
            out = out[:-1] + text.lstrip()
        elif re.search(r"[^\W\d_]-$", out):
            out += text.lstrip()
        else:
            out += " " + text.lstrip()
    return out.replace("\u00ad", "")


def _extract_pdf(content: bytes) -> Extraction:
    try:
        import pymupdf
    except ImportError:
        raise ValueError(PDF_RUNTIME_MISSING) from None

    from tradurre.services.glyph_resolver import apply_resolution, resolve_pua_glyphs

    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
    except pymupdf.FileDataError:  # also an empty file (EmptyFileError is a subclass)
        raise ValueError("The file is not a readable PDF") from None
    mapping, warnings = resolve_pua_glyphs(doc)
    lines, sizes = _pdf_lines(doc)
    if not lines:
        return Extraction([], warnings)

    weights: Counter[float] = Counter()
    for line in lines:
        weights[round(line.size, 1)] += len(line.text)
    body_size = weights.most_common(1)[0][0]

    body_x: dict[int, Counter[int]] = defaultdict(Counter)
    for line in lines:
        if abs(line.size - body_size) <= 0.5:
            body_x[line.page][round(line.x0)] += 1
    default_left = sum(body_x.values(), Counter()).most_common(1)[0][0] if body_x else 0
    left = {page: xs.most_common(1)[0][0] for page, xs in body_x.items()}

    kinds = _classify(lines, sizes, body_size)
    body = [line for line, kind in zip(lines, kinds) if kind == "paragraph"]
    pitches = [b.y0 - a.y0 for a, b in zip(body, body[1:]) if a.page == b.page and b.y0 > a.y0]
    pitch = statistics.median(pitches) if pitches else body_size * 1.2

    # Blocks in order of their first line; a paragraph stays open across excluded lines (page numbers, running
    # heads, footnotes), so it can continue over a page break.
    blocks: list[tuple[str, list[_Line]]] = []
    paragraph: list[_Line] | None = None
    for line, kind in zip(lines, kinds):
        if kind == "paragraph":
            previous = paragraph[-1] if paragraph else None
            indented = line.x0 >= left.get(line.page, default_left) + 0.5 * body_size
            gap = previous is not None and previous.page == line.page and line.y0 - previous.y0 > 1.5 * pitch
            if paragraph is None or indented or gap:
                paragraph = []
                blocks.append(("paragraph", paragraph))
            paragraph.append(line)
            continue
        if kind not in EXCLUDED_KINDS:
            paragraph = None  # a heading ends the paragraph
        previous_block = blocks[-1] if blocks else None
        if (
            kind in ("page_number", "running_head")
            or previous_block is None
            or previous_block[0] != kind
            or previous_block[1][-1].page != line.page  # only paragraphs run over a page break
        ):
            blocks.append((kind, [line]))
        else:
            blocks[-1][1].append(line)

    extracted = []
    for kind, block_lines in blocks:
        text = _clean(apply_resolution(_join_lines([line.text for line in block_lines]), mapping))
        if text:
            extracted.append(ExtractedBlock(kind, text, block_lines[0].page + 1))
    return Extraction(extracted, warnings)


def extract(filename: str, content: bytes) -> Extraction:
    """Extract the blocks of a .txt, .docx or .pdf file, in reading order, with marked front and back matter
    re-kinded (`matter.mark_matter`)."""
    from tradurre.services.matter import mark_matter  # matter imports this module

    name = (filename or "").lower()
    if name.endswith(".txt"):
        extraction = _extract_txt(content)
    elif name.endswith(".docx"):
        extraction = _extract_docx(content)
    elif name.endswith(".pdf"):
        extraction = _extract_pdf(content)
    else:
        raise ValueError(f"Unsupported file type: {filename!r} (expected .txt, .docx or .pdf)")
    return Extraction(mark_matter(extraction.blocks), extraction.warnings)
