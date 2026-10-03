"""Tests for the baseline local aligner (tradurre/services/align.py), on synthetic sentences only."""

import random
import time

from tradurre.services.align import Bead, align

WORDS = ["la", "nuit", "tombait", "sur", "une", "ville", "silencieuse", "et", "froide", "il", "marchait", "vite",
         "sans", "regarder", "derrière", "lui", "les", "rues", "étaient", "vides"]


def _sentence(rng: random.Random, length: int) -> str:
    """Lowercase words (no anchors) adding up to about `length` letters."""
    words: list[str] = []
    while sum(map(len, words)) < length:
        words.append(rng.choice(WORDS))
    return " ".join(words) + "."


def _book(n: int, seed: int = 0, low: int = 60, high: int = 160) -> list[str]:
    rng = random.Random(seed)
    return [_sentence(rng, rng.randint(low, high)) for _ in range(n)]


def _shapes(beads: list[Bead]) -> list[tuple[int, int]]:
    return [(len(b.source), len(b.target)) for b in beads]


def _assert_tiles(beads: list[Bead], n: int, m: int) -> None:
    assert [k for b in beads for k in b.source] == list(range(n))
    assert [k for b in beads for k in b.target] == list(range(m))
    for b in beads:
        assert b.source or b.target
        assert len(b.source) <= 2 and len(b.target) <= 2
        assert 0.0 <= b.confidence <= 1.0


def test_equal_sequences_align_one_to_one():
    source = _book(40)
    beads = align(source, list(source))
    _assert_tiles(beads, 40, 40)
    assert _shapes(beads) == [(1, 1)] * 40
    assert all(b.source == b.target for b in beads)


def test_long_source_sentence_takes_two_target_sentences():
    source = _book(20, seed=1)
    long_sentence = _book(1, seed=2, low=300, high=300)[0]
    halves = [_book(1, seed=3, low=150, high=150)[0], _book(1, seed=4, low=150, high=150)[0]]
    beads = align(source[:10] + [long_sentence] + source[10:], source[:10] + halves + source[10:])
    _assert_tiles(beads, 21, 22)
    assert [(b.source, b.target) for b in beads if len(b.target) == 2] == [([10], [10, 11])]
    assert _shapes(beads).count((1, 1)) == 20


def test_unmatched_source_sentence_is_one_sided():
    source = _book(20, seed=5, low=80, high=120)
    extra = _book(1, seed=6, low=150, high=150)[0]
    beads = align(source[:8] + [extra] + source[8:], source)
    _assert_tiles(beads, 21, 20)
    one_sided = [b for b in beads if not b.target]
    assert [b.source for b in one_sided] == [[8]]
    assert one_sided[0].confidence < 0.4
    assert _shapes(beads).count((1, 1)) == 20


def test_anchors_choose_between_length_equivalent_pairings():
    context = _book(10, seed=7, low=90, high=110)
    pierre = "hier soir dans la rue ils ont vu Pierre marcher seul vers la gare sans regarder personne autour."
    michel = "hier soir dans la rue ils ont vu Michel marcher seul vers la gare sans regarder personne autour."
    source = context[:5] + [pierre, michel] + context[5:]
    for name, paired in (("Pierre", 5), ("Michel", 6)):
        translated = f"ieri sera per strada hanno visto {name} camminare da solo verso la stazione senza guardare."
        beads = align(source, context[:5] + [translated] + context[5:])
        _assert_tiles(beads, 12, 11)
        assert [b.source for b in beads if b.target == [5]] == [[paired]]
        assert [b.source for b in beads if not b.target] == [[11 - paired]]


def test_numbers_are_anchors():
    context = _book(10, seed=8, low=90, high=110)
    source = context[:5] + ["il avait alors 1942 ans et rien de plus à dire.",
                            "il avait alors 1936 ans et rien de plus à dire."] + context[5:]
    beads = align(source, context[:5] + ["aveva allora 1942 anni e niente da dire."] + context[5:])
    assert [b.source for b in beads if b.target == [5]] == [[5]]


def test_empty_sides():
    assert align([], []) == []
    assert _shapes(align(["une phrase.", "deux phrases."], [])) == [(1, 0), (1, 0)]
    assert _shapes(align([], ["una frase."])) == [(0, 1)]


def test_very_different_counts_still_tile():
    beads = align(_book(10, seed=9), _book(30, seed=10))
    _assert_tiles(beads, 10, 30)


def test_random_inputs_always_tile():
    for seed in range(20):
        rng = random.Random(seed)
        n, m = rng.randint(0, 60), rng.randint(0, 60)
        source = _book(n, seed=100 + seed, low=1, high=200)
        target = _book(m, seed=200 + seed, low=1, high=200)
        _assert_tiles(align(source, target), n, m)


def test_book_sized_input_is_fast():
    source = _book(1500, seed=11)
    target = _book(1500, seed=11)
    start = time.perf_counter()
    beads = align(source, target)
    assert time.perf_counter() - start < 5
    _assert_tiles(beads, 1500, 1500)


def test_confidence_of_clean_one_to_one_is_high():
    source = _book(20, seed=12)
    assert all(b.confidence > 0.8 for b in align(source, list(source)))
