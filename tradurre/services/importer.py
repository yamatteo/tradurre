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


def extract_paragraphs_txt(file_bytes: bytes) -> list[ImportParagraph]:
    content = file_bytes.decode("utf-8")
    raw_paragraphs = re.split(r"\n\s*\n", content)
    paragraphs = []
    for raw in raw_paragraphs:
        text = raw.strip()
        if not text:
            continue
        html = f"<p>{escape(text)}</p>"
        paragraphs.append(ImportParagraph(html=html, text=text))
    return paragraphs
