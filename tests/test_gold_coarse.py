"""Coarse alignment precision, per-side exclusion and the hyphen-blind comparison of `score` (hand-built layers)."""

import importlib.util
from pathlib import Path

import pytest

from tradurre.services.gold import Layer, score

LIBRARY = Path(__file__).resolve().parent.parent / "library"


def _layer(source, target):
    n = 1 + max(bead for _, bead in source + target if bead is not None)
    return Layer(source, target, [True] * n)


# One gold bead holds two sentences per side.
COARSE = _layer(
    [("Alfa beta.", 0), ("Gamma delta.", 0), ("Omega.", 1)],
    [("Uno due.", 0), ("Tre quattro.", 0), ("Fine.", 1)],
)
FINER = _layer(
    [("Alfa beta.", 0), ("Gamma delta.", 1), ("Omega.", 2)],
    [("Uno due.", 0), ("Tre quattro.", 1), ("Fine.", 2)],
)


def test_finer_split_is_inside_gold():
    result = score(COARSE, FINER)
    assert (result.on_gold, result.inside_gold, result.elsewhere) == (1, 1, 0)
    assert result.coarse_precision == 1.0
    assert result.alignment_precision == 0.5
    assert result.alignment_recall == 1.0


def test_boundary_across_gold_borders_is_elsewhere():
    # Gold ends (3, 6) and (9, 9); the prediction cuts at (4, 5): later on the source, earlier on the target.
    gold = _layer([("aaa", 0), ("bbbbbb", 1)], [("cccccc", 0), ("ddd", 1)])
    predicted = _layer([("aaab", 0), ("bbbbb", 1)], [("ccccc", 0), ("cddd", 1)])
    result = score(gold, predicted)
    assert (result.on_gold, result.inside_gold, result.elsewhere) == (0, 0, 1)
    assert result.coarse_precision == 0.0
    assert result.alignment_recall == 0.0


def test_identical_layers_are_all_on_gold():
    result = score(FINER, FINER)
    assert (result.on_gold, result.inside_gold, result.elsewhere) == (2, 0, 0)
    assert result.coarse_precision == 1.0
    assert result.on_gold + result.inside_gold + result.elsewhere == result.predicted_boundaries


def test_beads_without_characters_on_a_side_do_not_break_the_classification():
    gold = _layer([("aaa", 0), ("bbb", 1), ("ccc", 2)], [("ddd", 0), ("eee", 2), ("fff", 2)])  # bead 1: source only
    result = score(gold, gold)
    assert result.on_gold + result.inside_gold + result.elsewhere == result.predicted_boundaries
    assert result.coarse_precision == 1.0


def test_empty_sets_convention():
    one = _layer([("aaa", 0), ("bbb", 0)], [("ccc", 0), ("ddd", 0)])
    split = _layer([("aaa", 0), ("bbb", 1)], [("ccc", 0), ("ddd", 1)])
    assert score(one, one).coarse_precision == 1.0  # nothing predicted, nothing in gold
    assert score(one, split).coarse_precision == 1.0  # inside the single gold bead
    assert score(split, one).coarse_precision == 0.0  # nothing predicted, something in gold


def test_exclusion_by_side():
    gold = _layer([("Titre.", None), ("aaa", 0)], [("Titolo.", None), ("bbb", 0)])
    # Source is right; the target keeps its title as a bead of its own.
    predicted = _layer([("Titre.", None), ("aaa", 0)], [("Titolo.", 0), ("bbb", 0)])
    result = score(gold, predicted)
    assert result.exclusion_by_side["source"] == (1.0, 1.0)
    assert result.exclusion_by_side["target"] == (0.0, 0.0)
    assert result.exclusion_recall == 6 / 13  # pooled fields keep their meaning


def test_exclusion_by_side_empty_sets():
    result = score(COARSE, COARSE)
    assert result.exclusion_by_side == {"source": (1.0, 1.0), "target": (1.0, 1.0)}


def test_comparison_ignores_hyphens_and_soft_hyphens():
    gold = _layer([("Alfa-beta gam­madelta.", 0), ("Omega.", 1)], [("Uno due.", 0), ("Fine.", 1)])
    predicted = _layer([("Alfabeta gammadelta.", 0), ("Om-ega.", 1)], [("Uno due.", 0), ("Fi­ne.", 1)])
    result = score(gold, predicted)
    assert (result.alignment_precision, result.alignment_recall, result.coarse_precision) == (1, 1, 1)


def test_real_text_difference_still_raises():
    gold = _layer([("Alfa-beta.", 0)], [("Uno.", 0)])
    other = _layer([("Alfa-gamma.", 0)], [("Uno.", 0)])
    with pytest.raises(ValueError, match="source"):
        score(gold, other)


def _script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent.parent / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.library
def test_femur_alignment_is_covered_by_the_coarse_gold():
    source, target = LIBRARY / "femur.fr.pdf", LIBRARY / "femur.it.pdf"
    gold_path = LIBRARY / "femur.gold.rebased.zip"
    original = LIBRARY / "femur.gold.zip"
    for path in (source, target, gold_path if gold_path.exists() else original):
        if not path.exists():
            pytest.skip(f"{path.name} is not present")
    from tradurre.services.gold import layer_from_bundle

    gold_score = _script("gold_score")
    if gold_path.exists():
        gold = layer_from_bundle(gold_path.read_bytes())
    else:
        gold_rebase = _script("gold_rebase")
        texts, kinds = gold_rebase.extraction_blocks(source, target)
        rebased, _ = gold_rebase.rebase(gold_rebase.read_bundle(original), texts, kinds)
        gold = layer_from_bundle(gold_rebase.bundle_bytes(rebased))
    predicted, _, _ = gold_score._build(source, target)
    result = score(gold, predicted)  # raises on a text mismatch
    assert result.on_gold + result.inside_gold + result.elsewhere == result.predicted_boundaries
    assert result.coarse_precision >= 0.99
    assert result.alignment_recall >= 0.99
