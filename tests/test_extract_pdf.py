"""Tests for PDF extraction in `tradurre/services/extract.py` (PDFs built in the test, no fixtures)."""

import pytest

pymupdf = pytest.importorskip("pymupdf")

from tradurre.services.extract import _pdf_lines  # noqa: E402

PORTRAIT = (439, 651)  # the reference book's French page
SPREAD = (765, 595)  # the reference book's Italian two-up spread


def _doc(pages):
    """A PDF with one page per `(size, [(x, y, text), ...])`; `y` is the text baseline."""
    doc = pymupdf.open()
    for (width, height), lines in pages:
        page = doc.new_page(width=width, height=height)
        for x, y, text in lines:
            page.insert_text((x, y), text, fontsize=11)
    return doc


def _column(x, first, texts):
    return [(x, first + 14 * i, text) for i, text in enumerate(texts)]


def test_portrait_page_reads_top_to_bottom():
    # Inserted bottom-up, read top-down.
    doc = _doc([(PORTRAIT, [(60, 300, "troisième"), (60, 200, "deuxième"), (60, 100, "première")])])
    lines, sizes = _pdf_lines(doc)
    assert [line.text for line in lines] == ["première", "deuxième", "troisième"]
    assert {line.page for line in lines} == {0}
    assert sizes == [PORTRAIT]
    assert lines[0].size == pytest.approx(11)


def test_two_up_spreads_split_into_logical_pages():
    left = ["gauche un", "gauche deux", "gauche trois"]
    right = ["droite un", "droite deux", "droite trois"]
    doc = _doc([
        # Right column inserted first: reading order must still put the left page first.
        (SPREAD, _column(450, 100, right) + _column(60, 100, left)),
        (SPREAD, _column(450, 100, ["seule à droite"])),  # a page with text only on the right
        (SPREAD, _column(60, 100, ["fin gauche"]) + _column(450, 100, ["fin droite"])),
    ])  # 2 of the 3 spreads look two-up (≥ 60%), so all three are split
    lines, sizes = _pdf_lines(doc)
    assert sizes == [(SPREAD[0] / 2, SPREAD[1])] * 6
    assert [(line.page, line.text) for line in lines] == (
        [(0, t) for t in left] + [(1, t) for t in right] + [(3, "seule à droite"), (4, "fin gauche"), (5, "fin droite")]
    )
    right_line = next(line for line in lines if line.text == "droite un")
    assert right_line.x0 == pytest.approx(450 - SPREAD[0] / 2, abs=1)
    assert next(line for line in lines if line.text == "gauche un").x0 == pytest.approx(60, abs=1)


def test_landscape_with_one_centred_column_is_not_split():
    texts = ["une ligne centrée", "une autre ligne", "et une troisième"]
    doc = _doc([(SPREAD, _column(300, 100, texts)), (SPREAD, _column(300, 100, texts))])
    lines, sizes = _pdf_lines(doc)
    assert sizes == [SPREAD, SPREAD]
    assert [line.page for line in lines] == [0, 0, 0, 1, 1, 1]
    assert lines[0].x0 == pytest.approx(300, abs=1)


def test_blank_lines_are_dropped():
    doc = _doc([(PORTRAIT, [(60, 100, "texte"), (60, 120, "   ")])])
    lines, _ = _pdf_lines(doc)
    assert [line.text for line in lines] == ["texte"]
