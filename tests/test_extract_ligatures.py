"""Stray spaces inside f/fi/fl/Th ligature glyphs of a PDF (extract.py, `_stray_space_indexes`). Synthetic data only."""

import importlib.util
from pathlib import Path

import pymupdf
import pytest

from tradurre.services.extract import _stray_space_indexes, extract

LIBRARY = Path(__file__).resolve().parent.parent / "library"


def _chars(spec: str, step: float = 5.0, offsets: dict[int, float] | None = None):
    """Characters laid out `step` apart; `offsets` moves the x0 of the space at an index (relative to the origin
    of the glyph before it)."""
    out = []
    for i, c in enumerate(spec):
        origin = i * step
        x0 = origin
        if offsets and i in offsets:
            x0 = (i - 1) * step + offsets[i]
        out.append((c, origin, x0))
    return out


def test_stray_space_after_fi_is_dropped():
    assert _stray_space_indexes(_chars("fi lm", offsets={2: -3.0})) == {2}


def test_real_space_after_fi_is_kept():
    assert _stray_space_indexes(_chars("fi lm", offsets={2: 4.0})) == set()
    assert _stray_space_indexes(_chars("fi lm", offsets={2: 0.0})) == set()
    assert _stray_space_indexes(_chars("fi lm", offsets={2: -1.0})) == set()


def test_mixed_run_keeps_the_real_space():
    chars = _chars("xfi  lm", offsets={3: -3.0, 4: 4.0})
    assert _stray_space_indexes(chars) == {3}


def test_stray_space_after_another_letter_is_kept():
    assert _stray_space_indexes(_chars("ab cd", offsets={2: -3.0})) == set()


def test_capital_th_is_dropped_lowercase_is_kept():
    assert _stray_space_indexes(_chars("Th ab", offsets={2: -3.0})) == {2}
    assert _stray_space_indexes(_chars("th ab", offsets={2: -3.0})) == set()


def test_run_of_two_strays_after_ffi_is_dropped():
    chars = _chars("ffi  x")
    chars[3] = (" ", 15.0, 8.0)
    chars[4] = (" ", 20.0, 8.5)
    assert _stray_space_indexes(chars) == {3, 4}


def test_f_and_fl_and_ligature_code_points():
    assert _stray_space_indexes(_chars("f x", offsets={1: -3.0})) == {1}
    assert _stray_space_indexes(_chars("fl x", offsets={2: -3.0})) == {2}
    assert _stray_space_indexes(_chars("\ufb01 x", offsets={1: -3.0})) == {1}
    assert _stray_space_indexes(_chars("a\ufb03 x", offsets={2: -3.0})) == {2}
    assert _stray_space_indexes(_chars("\ufb00 x", offsets={1: -3.0})) == {1}


def test_capital_f_counts_as_f():
    assert _stray_space_indexes(_chars("Fi x", offsets={2: -3.0})) == {2}


def test_leading_space_and_no_glyph():
    assert _stray_space_indexes(_chars(" fi", offsets={0: -3.0})) == set()
    assert _stray_space_indexes([]) == set()
    assert _stray_space_indexes(_chars("   ")) == set()


def test_single_letter_before_space_after_th_boundary():
    # "h" alone, with "T" absent: not a ligature
    assert _stray_space_indexes(_chars("h x", offsets={1: -3.0})) == set()


def _pdf(pieces: list[tuple[float, str]]) -> bytes:
    """One page with each piece of text placed at an absolute x on one baseline."""
    doc = pymupdf.open()
    page = doc.new_page()
    for x, text in pieces:
        page.insert_text((x, 100), text, fontsize=12, fontname="helv")
    return doc.tobytes()


def test_end_to_end_stray_space_in_a_ligature_is_dropped_real_one_kept():
    # "fi" then a space drawn inside the glyph (x 73 < the origin of "i"), then "lm"; a second word follows a
    # space at a real position.
    pdf = _pdf([(72, "fi"), (73, " "), (80, "lm"), (95, " "), (100, "abc")])
    assert [b.text for b in extract("a.pdf", pdf).blocks] == ["film abc"]


def test_end_to_end_plain_text_is_unchanged():
    pdf = _pdf([(72, "Une phrase simple qui fait plusieurs mots.")])
    assert [b.text for b in extract("a.pdf", pdf).blocks] == ["Une phrase simple qui fait plusieurs mots."]


def _script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent.parent / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.library
def test_femur_ligature_gaps_are_closed():
    gold_path, source, target = LIBRARY / "femur.gold.zip", LIBRARY / "femur.fr.pdf", LIBRARY / "femur.it.pdf"
    for path in (gold_path, source, target):
        if not path.exists():
            pytest.skip(f"{path.name} is not present")
    from tradurre.services.gold import layer_from_bundle, score_ligatures

    gold_rebase = _script("gold_rebase")
    gold_score = _script("gold_score")
    texts, kinds = gold_rebase.extraction_blocks(source, target)
    rebased, _ = gold_rebase.rebase(gold_rebase.read_bundle(gold_path), texts, kinds)
    predicted, _, _ = gold_score._build(source, target)
    counts = score_ligatures(layer_from_bundle(gold_rebase.bundle_bytes(rebased)), predicted).total
    assert counts.slips > 0
    assert counts.real_joined == 0
    assert counts.slips_closed == counts.slips
