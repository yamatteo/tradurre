"""Convert uploaded documents (.txt, .docx, .pdf) to a shared plain-text representation.

The rest of the import pipeline (tradurre.services.aligner) consumes raw text with
blank-line paragraph breaks -- the same convention plain .txt exports already use.
This module normalizes .docx and .pdf down to that same convention so the existing
hierarchy/anchor alignment logic applies unchanged regardless of source format.
"""

import logging
import re
from io import BytesIO

logger = logging.getLogger("tradurre.doc_adapter")

SUPPORTED_EXTENSIONS = (".txt", ".docx", ".pdf")

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


def _extension(filename: str) -> str:
    name = (filename or "").lower()
    for ext in SUPPORTED_EXTENSIONS:
        if name.endswith(ext):
            return ext
    return ""


def _load_txt(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("txt content is not valid utf-8, falling back to latin-1")
        return content.decode("latin-1")


def _load_docx(content: bytes) -> str:
    from docx import Document

    doc = Document(BytesIO(content))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    logger.info("docx: extracted %d paragraphs", len(paragraphs))
    return "\n\n".join(paragraphs)


def _load_pdf(content: bytes, generate=None) -> tuple[str, list[str]]:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError(
            "PDF import requires the 'pdf' optional dependency group. "
            "Install with: uv sync --extra pdf"
        ) from e

    from tradurre.services import glyph_resolver

    doc = fitz.open(stream=content, filetype="pdf")
    pages = [page.get_text("text") for page in doc]
    logger.info("pdf: extracted %d pages", len(pages))

    mapping, warnings = glyph_resolver.resolve_pua_glyphs(doc, generate=generate)
    doc.close()
    for w in warnings:
        logger.warning("pdf glyph resolution: %s", w)

    text = "\n\n".join(pages)
    text = glyph_resolver.apply_resolution(text, mapping)
    return normalize_ocr_artifacts(text), warnings


def load_as_text(filename: str, content: bytes) -> str:
    """Dispatch on file extension and return plain text with blank-line paragraph breaks."""
    text, _warnings = load_as_text_with_warnings(filename, content)
    return text


def load_as_text_with_warnings(filename: str, content: bytes, generate=None) -> tuple[str, list[str]]:
    """Like load_as_text, but also returns non-fatal warnings (e.g. unresolved
    PDF glyphs) for callers -- such as the Colab pipeline -- that want to
    surface them somewhere more durable than the log.

    `generate`, if given, is a callable(prompt: str) -> str for an LLM, used
    (PDF only) as a second opinion on OCR-based glyph substitutions -- see
    glyph_resolver.resolve_pua_glyphs. Ignored for other formats.
    """
    ext = _extension(filename)
    if ext == ".txt":
        return _load_txt(content), []
    elif ext == ".docx":
        return _load_docx(content), []
    elif ext == ".pdf":
        return _load_pdf(content, generate=generate)
    else:
        raise ValueError(f"Unsupported file type: {filename!r}")
