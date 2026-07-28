import re
from html import escape
from io import BytesIO

from docx import Document

from tradurre.models import ImportParagraph


def _runs_to_html(runs) -> str:
    parts = []
    for run in runs:
        text = escape(run.text)
        if run.bold:
            text = f"<strong>{text}</strong>"
        if run.italic:
            text = f"<em>{text}</em>"
        if run.underline:
            text = f"<u>{text}</u>"
        parts.append(text)
    return "".join(parts)


def extract_paragraphs_docx(file_bytes: bytes) -> list[ImportParagraph]:
    doc = Document(BytesIO(file_bytes))
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        html = f"<p>{_runs_to_html(para.runs)}</p>"
        paragraphs.append(ImportParagraph(html=html, text=text))
    return paragraphs


def extract_paragraphs_from_text(content: str) -> list[ImportParagraph]:
    raw_paragraphs = re.split(r"\n\s*\n", content)
    paragraphs = []
    for raw in raw_paragraphs:
        text = raw.strip()
        if not text:
            continue
        html = f"<p>{escape(text)}</p>"
        paragraphs.append(ImportParagraph(html=html, text=text))
    return paragraphs


def extract_paragraphs_txt(file_bytes: bytes) -> list[ImportParagraph]:
    return extract_paragraphs_from_text(file_bytes.decode("utf-8"))


def extract_paragraphs_pdf(file_bytes: bytes) -> list[ImportParagraph]:
    from tradurre.services.doc_adapter import load_as_text

    return extract_paragraphs_from_text(load_as_text("file.pdf", file_bytes))


def extract_and_align_txt(
    source_bytes: bytes, target_bytes: bytes
) -> tuple[list[ImportParagraph], list[ImportParagraph]]:
    """Smart-align two .txt files at sentence level using anchors.

    Returns two equal-length lists of ImportParagraph ready for preview.
    """
    from tradurre.services.aligner import smart_align

    source_text = source_bytes.decode("utf-8")
    target_text = target_bytes.decode("utf-8")

    pairs = smart_align(source_text, target_text)

    source_paragraphs = []
    target_paragraphs = []
    for src, tgt in pairs:
        source_paragraphs.append(ImportParagraph(
            html=f"<p>{escape(src)}</p>" if src else "<p></p>",
            text=src,
        ))
        target_paragraphs.append(ImportParagraph(
            html=f"<p>{escape(tgt)}</p>" if tgt else "<p></p>",
            text=tgt,
        ))

    return source_paragraphs, target_paragraphs
