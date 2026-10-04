"""Write the checklist fixtures in .docx and .pdf (PLAN.md, "Checklist fixtures: a .docx and a .pdf").

    uv run python scripts/make_fixtures.py

From the synthetic `tests/fixtures/easy.source.txt` and `easy.target.txt`: `easy.source.docx`, one Word paragraph per
paragraph of the text, and `easy.target.pdf`, the Italian flowed over A5 pages with the running head "Facile" and a
page number. Both are rewritten byte for byte the same on every run: the metadata and the zip entries' dates are
fixed.
"""

import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pymupdf
from docx import Document

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
FIXED = datetime(2026, 1, 1)

# A5 in points; the running head and the page number sit inside the top and bottom 15 % the extractor looks at.
WIDTH, HEIGHT = 420, 595
LEFT, RIGHT = 60, 360
INDENT = 18
SIZE, LEADING = 12, 18
HEAD_Y, TOP_Y, BOTTOM_Y, NUMBER_Y = 55, 110, 480, 560
RUNNING_HEAD = "Facile"


def _paragraphs(path: Path) -> list[str]:
    """The text's blank-line paragraphs, each with its wrapped lines joined by one space."""
    text = path.read_text(encoding="utf-8")
    return [" ".join(line.strip() for line in block.splitlines()) for block in text.split("\n\n") if block.strip()]


def _fixed_zip(content: bytes) -> bytes:
    """`content` (a zip) with every entry dated `FIXED`, in the same order and compression."""
    out = BytesIO()
    with zipfile.ZipFile(BytesIO(content)) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            fixed = zipfile.ZipInfo(info.filename, date_time=FIXED.timetuple()[:6])
            fixed.compress_type = info.compress_type
            fixed.external_attr = info.external_attr
            dst.writestr(fixed, src.read(info))
    return out.getvalue()


def make_docx(paragraphs: list[str]) -> bytes:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    props = doc.core_properties
    props.author = props.last_modified_by = "tradurre"
    props.created = props.modified = FIXED
    props.revision = 1
    buffer = BytesIO()
    doc.save(buffer)
    return _fixed_zip(buffer.getvalue())


def _wrap(font: pymupdf.Font, text: str, first_width: float, width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and font.text_length(candidate, fontsize=SIZE) > (width if lines else first_width):
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    return lines


def make_pdf(paragraphs: list[str]) -> bytes:
    font = pymupdf.Font("helv")
    width = RIGHT - LEFT
    # (x, text) per line; a paragraph's first line is indented, which is how the extractor finds paragraphs.
    flow = [
        (LEFT + (INDENT if k == 0 else 0), line)
        for text in paragraphs
        for k, line in enumerate(_wrap(font, text, width - INDENT, width))
    ]
    per_page = int((BOTTOM_Y - TOP_Y) // LEADING) + 1
    doc = pymupdf.open()
    for start in range(0, len(flow), per_page):
        page = doc.new_page(width=WIDTH, height=HEIGHT)
        page.insert_font(fontname="F0", fontbuffer=font.buffer)
        number = doc.page_count
        page.insert_text((LEFT, HEAD_Y), RUNNING_HEAD, fontsize=SIZE - 2, fontname="F0")
        for k, (x, line) in enumerate(flow[start:start + per_page]):
            page.insert_text((x, TOP_Y + k * LEADING), line, fontsize=SIZE, fontname="F0")
        label = str(number)
        page.insert_text(
            ((WIDTH - font.text_length(label, fontsize=SIZE - 2)) / 2, NUMBER_Y), label,
            fontsize=SIZE - 2, fontname="F0",
        )
    if doc.page_count < 3:
        raise SystemExit(f"the target fills {doc.page_count} pages; the running head needs at least 3")
    stamp = f"D:{FIXED:%Y%m%d%H%M%S}"
    doc.set_metadata({"title": RUNNING_HEAD, "producer": "tradurre", "creator": "tradurre",
                      "creationDate": stamp, "modDate": stamp})
    return doc.tobytes(garbage=3, deflate=True, no_new_id=True)


def main() -> None:
    docx_path = FIXTURES / "easy.source.docx"
    pdf_path = FIXTURES / "easy.target.pdf"
    docx_path.write_bytes(make_docx(_paragraphs(FIXTURES / "easy.source.txt")))
    pdf_path.write_bytes(make_pdf(_paragraphs(FIXTURES / "easy.target.txt")))
    print(f"Wrote {docx_path.name} and {pdf_path.name} in {FIXTURES}")


if __name__ == "__main__":
    main()
