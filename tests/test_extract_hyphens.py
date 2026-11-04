"""Line-end hard hyphens follow the book's own spelling (invented words throughout): a soft-hyphen book keeps a hard
hyphen unless it spells the joined word elsewhere; any other book drops it unless the pair or a particle shows it real."""

import pytest

from tradurre.services.extract import _book_lexicon, _join_lines


SOFT = "Un mot cou­"  # a line ending in a soft hyphen: marks a soft-hyphen book


def _join(lines, *others, soft=True):
    """Join `lines` using a lexicon built from them and the `others` (more lines of the same book), which also
    holds a soft-hyphen line unless `soft` is false."""
    more = [[o] for o in others] + ([[SOFT]] if soft else [])
    return _join_lines(lines, _book_lexicon([lines, *more]))


def test_mode_is_soft_when_a_line_ends_in_a_soft_hyphen():
    assert _book_lexicon([["Un mot cou­", "pé."]]).soft
    assert not _book_lexicon([["Un mot-", "coupé."]]).soft


def test_hard_book_drops_an_unknown_split():
    assert _join(["Une zorb-", "tavale rare."], soft=False) == "Une zorbtavale rare."


def test_hard_book_keeps_a_particle():
    assert _join(["Dis-", "moi ça."], soft=False) == "Dis-moi ça."
    assert _join(["Voilà-", "T ça."], soft=False) == "Voilà-T ça."
    assert _join(["Est-", "ce vrai."], soft=False) == "Est-ce vrai."


def test_hard_book_keeps_a_known_pair():
    assert _join(["Une zorb-", "tavale rare."], "Une zorb-tavale ici.", soft=False) == "Une zorb-tavale rare."


def test_split_word_is_joined_when_the_book_spells_it_elsewhere():
    assert _join(["Le glorbat se tra-", "mouille ici."], "Un tramouille au loin.") == "Le glorbat se tramouille ici."


def test_compound_is_kept_when_the_pair_appears_mid_line():
    assert _join(["Une zorb-", "tavale rare."], "Une zorb-tavale ici.", "Un zorbtavale.") == "Une zorb-tavale rare."


def test_unknown_is_kept():
    assert _join(["Une zorb-", "tavale rare."]) == "Une zorb-tavale rare."


def test_multi_hyphen_compound():
    assert _join(["Un qux-bli-", "mor ici."], "Un qux-bli-mor, puis un blimor.") == "Un qux-bli-mor ici."


def test_case_insensitive():
    assert _join(["Le TRA-", "mouille."], "Le Tramouille.") == "Le TRAmouille."


def test_words_touching_a_line_end_hyphen_do_not_count():
    # the only evidence for the joined word is the split itself
    assert _join(["Le tra-", "mouille ici."]) == "Le tra-mouille ici."
    assert _join(["Le tra-", "mouille ici."], "Le tra-") == "Le tra-mouille ici."


def test_soft_hyphen_and_no_lexicon_are_unchanged():
    assert _join(["Le tra­", "mouille."]) == "Le tramouille."
    assert _join(["Une zorb-", "tavale rare."]) == "Une zorb-tavale rare."
    assert _join_lines(["Le tra-", "mouille."]) == "Le tra-mouille."


def test_pdf_drops_the_split_hyphen():
    pymupdf = pytest.importorskip("pymupdf")  # noqa: F841
    from tests.test_extract_pdf import PORTRAIT, _blocks, _body

    lines = _body(74, 100, ["Le glorbat se tra-"]) + _body(60, 114, ["mouille ici."])
    lines += _body(74, 142, ["Un tramouille au loin"]) + _body(60, 156, ["et finit.", "Fin."])
    assert _blocks([(PORTRAIT, lines)]) == [
        ("paragraph", "Le glorbat se tramouille ici."),
        ("paragraph", "Un tramouille au loin et finit. Fin."),
    ]
