"""Turn and paragraph levels of `score` (hand-built layers, invented words)."""

import importlib.util
from pathlib import Path

import pytest

from tradurre.services.gold import Layer, is_speech, layer_from_bundle, score

LIBRARY = Path(__file__).resolve().parent.parent / "library"


def _layer(source, target, blocks=None):
    n = 1 + max(bead for _, bead in source + target if bead is not None)
    return Layer(source, target, [True] * n, None, blocks)


@pytest.mark.parametrize("text", ["— Alfa.", "– Alfa.", "- Alfa.", "« Alfa.", "  \n— Alfa.", "\t« Alfa."])
def test_openers_are_speech(text):
    assert is_speech(text)


@pytest.mark.parametrize("text", ["Alfa beta.", "Alfa — beta.", "", "   ", "(Alfa)."])
def test_narration_is_not_speech(text):
    assert not is_speech(text)


# Block 1: a speech paragraph of three sentences; block 2: narration of two; block 3: narration of one.
SOURCE = ["— Alfa beta.", "Gamma delta.", "Omega zeta.", "Sigma tau.", "Ypsilon phi.", "Chi psi."]
TARGET = ["— Uno due.", "Tre quattro.", "Cinque sei.", "Sette otto.", "Nove dieci.", "Undici."]
BLOCKS = {"source": [1, 1, 1, 2, 2, 3], "target": [1, 1, 1, 2, 2, 3]}


def _beads(source_beads, target_beads=None):
    target_beads = source_beads if target_beads is None else target_beads
    return (list(zip(SOURCE, source_beads)), list(zip(TARGET, target_beads)))


FINE = _layer(*_beads([0, 1, 2, 3, 4, 5]), BLOCKS)  # one bead per sentence
TURNS = _layer(*_beads([0, 0, 0, 1, 2, 3]))  # the speech paragraph as one bead


def test_turn_level_accepts_a_speech_paragraph_as_one_bead():
    result = score(TURNS, FINE)
    assert result.alignment_precision < 1
    assert result.alignment_recall == 1.0
    assert (result.turn_precision, result.turn_recall, result.turn_f1) == (1.0, 1.0, 1.0)
    assert result.turn_boundaries == 3
    assert result.gold_inside_speech == 0


def test_gold_boundary_inside_speech_lowers_turn_recall():
    # The translator split the speech paragraph after its first sentence.
    gold = _layer(*_beads([0, 1, 1, 2, 3, 4]))
    result = score(gold, FINE)
    assert result.gold_inside_speech == 1
    assert result.turn_recall == 3 / 4
    assert result.turn_precision == 1.0
    assert result.turn_boundaries == 3
    assert result.alignment_recall == 1.0


def test_paragraph_level_keeps_only_block_breaks_on_both_sides():
    # The gold cuts the narration block between its sentences too; the prediction misses the end of block 2.
    gold = _layer(*_beads([0, 0, 0, 1, 2, 3]))
    predicted = _layer(*_beads([0, 0, 0, 1, 1, 2]), BLOCKS)
    result = score(gold, predicted)
    assert result.paragraph_boundaries == (2, 2)
    assert (result.paragraph_precision, result.paragraph_recall, result.paragraph_f1) == (1.0, 1.0, 1.0)
    assert result.alignment_recall == 2 / 3  # the sentence level sees the narration cut


def test_paragraph_level_counts_a_missed_break():
    gold = _layer(*_beads([0, 1, 1, 2, 2, 3]))
    predicted = _layer(*_beads([0, 1, 1, 1, 1, 2]), BLOCKS)  # misses the break between blocks 1 and 2
    result = score(gold, predicted)
    assert result.paragraph_boundaries == (2, 1)
    assert result.paragraph_recall == 1 / 2
    assert result.paragraph_precision == 1.0


def test_without_blocks_the_levels_keep_their_defaults():
    result = score(TURNS, _layer(*_beads([0, 1, 2, 3, 4, 5])))
    assert result.turn_boundaries == 0
    assert result.gold_inside_speech == 0
    assert result.paragraph_boundaries == (0, 0)
    assert (result.turn_f1, result.paragraph_f1) == (1.0, 1.0)


def _script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent.parent / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.library
def test_femur_levels():
    source, target = LIBRARY / "femur.fr.pdf", LIBRARY / "femur.it.pdf"
    gold_path = LIBRARY / "femur.gold.rebased.zip"
    for path in (source, target, gold_path):
        if not path.exists():
            pytest.skip(f"{path.name} is not present")
    predicted, _, _ = _script("gold_score")._build(source, target)
    result = score(layer_from_bundle(gold_path.read_bytes()), predicted)
    assert result.turn_f1 >= 0.98
    assert result.paragraph_f1 >= 0.99
