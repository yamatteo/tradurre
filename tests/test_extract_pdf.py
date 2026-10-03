"""Tests for PDF extraction in `tradurre/services/extract.py` (PDFs built in the test, no fixtures)."""

import pytest

pymupdf = pytest.importorskip("pymupdf")

from tradurre.services.extract import _pdf_lines, extract  # noqa: E402

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


# --- Blocks (`extract` on .pdf) ---

BODY = 11.9  # the reference book's French body size


def _pdf(pages) -> bytes:
    """PDF bytes, one page per `(size, [(x, baseline_y, text, fontsize), ...])`, in an embedded font (which keeps
    U+00AD soft hyphens in the extracted text; the base-14 fonts turn them into "-")."""
    font = pymupdf.Font("helv")
    doc = pymupdf.open()
    for (width, height), lines in pages:
        page = doc.new_page(width=width, height=height)
        page.insert_font(fontname="F0", fontbuffer=font.buffer)
        for x, y, text, size in lines:
            page.insert_text((x, y), text, fontsize=size, fontname="F0")
    return doc.tobytes()


def _body(x, first, texts, size=BODY, pitch=14):
    return [(x, first + pitch * i, text, size) for i, text in enumerate(texts)]


def _blocks(pages):
    return [(b.kind, b.text) for b in extract("livre.pdf", _pdf(pages)).blocks]


def test_indented_lines_start_paragraphs():
    lines = _body(74, 100, ["Le premier paragraphe"]) + _body(60, 114, ["continue ici", "et finit là."])
    lines += _body(74, 142, ["Le second commence"]) + _body(60, 156, ["et finit."])
    assert _blocks([(PORTRAIT, lines)]) == [
        ("paragraph", "Le premier paragraphe continue ici et finit là."),
        ("paragraph", "Le second commence et finit."),
    ]


def test_paragraph_continues_over_a_page_break_and_page_numbers_at_87_percent():
    # FR-like: the page number's baseline at 576 puts the line at y0/h ≈ 0.87.
    page1 = _body(74, 500, ["La phrase commence"]) + _body(60, 514, ["en bas de page"]) + [(210, 576, "7", 10)]
    page2 = _body(60, 80, ["et finit en haut.", "Encore une ligne."]) + [(210, 576, "8", 10)]
    blocks = extract("livre.pdf", _pdf([(PORTRAIT, page1), (PORTRAIT, page2)])).blocks
    assert [(b.kind, b.text, b.page) for b in blocks] == [
        ("paragraph", "La phrase commence en bas de page et finit en haut. Encore une ligne.", 1),
        ("page_number", "7", 1),
        ("page_number", "8", 2),
    ]


def test_rare_top_number_is_a_heading_not_a_page_number():
    # IT-like: page numbers (size 8.2) at the bottom of all 10 pages; a chapter number (size 11, smaller than the
    # body) at the top of 2 of them.
    pages = []
    for k in range(10):
        lines = _body(60, 120, [f"Texte de la page {k}, assez long pour être le corps."], size=12.5)
        lines.append((210, 600, str(k + 1), 8.2))
        if k in (2, 6):
            lines.append((210, 55, "IV" if k == 2 else "5", 11))
        pages.append((PORTRAIT, lines))
    kinds = [(kind, text) for kind, text in _blocks(pages) if kind != "paragraph"]
    assert ("heading", "IV") in kinds and ("heading", "5") in kinds
    assert [text for kind, text in kinds if kind == "page_number"] == [str(k + 1) for k in range(10)]


def test_soft_and_hard_hyphens_at_line_ends():
    lines = _body(74, 100, ["Le commen­", "cement de la porte-", "fenêtre."])
    assert _blocks([(PORTRAIT, lines)]) == [("paragraph", "Le commencement de la porte-fenêtre.")]


def _with_top_line(n_pages):
    return [(PORTRAIT, [(150, 40, "Contrefeu", BODY)] + _body(74, 120, [f"Page {k} du livre."]))
            for k in range(n_pages)]


def test_running_head_needs_three_pages():
    assert [kind for kind, _ in _blocks(_with_top_line(3)) if kind == "running_head"] == ["running_head"] * 3
    assert all(kind != "running_head" for kind, _ in _blocks(_with_top_line(2)))


def test_larger_line_is_a_heading_and_small_bottom_text_a_footnote():
    lines = [(60, 100, "Chapitre premier", 14)] + _body(74, 130, ["Le texte du chapitre", "qui continue."])
    lines += [(60, 560, "1. Une note de bas de page.", 9)]
    assert _blocks([(PORTRAIT, lines)]) == [
        ("heading", "Chapitre premier"),
        ("paragraph", "Le texte du chapitre qui continue."),
        ("footnote", "1. Une note de bas de page."),
    ]


def test_two_up_document_reads_left_page_then_right_page():
    def spread(k):
        # Right column inserted first; each column is one paragraph, its first line indented (right-hand x is
        # shifted by half the spread's width, so 456.5/442.5 become 74/60 like the left column).
        right = _body(456.5, 100, [f"Droite {k}"]) + _body(442.5, 114, ["suite", "et fin."])
        left = _body(74, 100, [f"Gauche {k}"]) + _body(60, 114, ["suite", "et fin."])
        return (SPREAD, right + left)

    assert [text for _, text in _blocks([spread(1), spread(2)])] == [
        "Gauche 1 suite et fin.", "Droite 1 suite et fin.", "Gauche 2 suite et fin.", "Droite 2 suite et fin.",
    ]


def test_headings_on_different_pages_stay_apart():
    # A front-matter heading, a blank page, then a chapter number at the top of the next page.
    pages = [
        (PORTRAIT, [(60, 300, "Un titre de faux-titre", 14)]),
        (PORTRAIT, []),
        (PORTRAIT, [(210, 55, "1", 11)] + _body(74, 120, ["Le chapitre commence", "et continue."])),
    ]
    # More body pages, so a number on one page in seven is rare (a page number's slot needs 25% of the pages).
    pages += [(PORTRAIT, _body(60, 300, [f"et continue page {k}."])) for k in range(4)]
    assert _blocks(pages)[:3] == [
        ("heading", "Un titre de faux-titre"),
        ("heading", "1"),
        ("paragraph", "Le chapitre commence et continue. et continue page 0. et continue page 1. et continue page 2. "
                      "et continue page 3."),
    ]


def test_footnotes_on_consecutive_pages_stay_apart():
    page1 = _body(74, 100, ["Un paragraphe qui", "passe à la page"]) + [(60, 560, "1. Première note.", 9)]
    page2 = _body(60, 100, ["suivante et finit."]) + [(60, 560, "2. Seconde note.", 9)]
    assert _blocks([(PORTRAIT, page1), (PORTRAIT, page2)]) == [
        ("paragraph", "Un paragraphe qui passe à la page suivante et finit."),
        ("footnote", "1. Première note."),
        ("footnote", "2. Seconde note."),
    ]
