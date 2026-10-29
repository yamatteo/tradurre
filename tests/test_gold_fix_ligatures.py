"""Tests for `scripts/gold_fix_ligatures.py`, on synthetic text only."""

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

_PATH = Path(__file__).parent.parent / "scripts" / "gold_fix_ligatures.py"
_spec = importlib.util.spec_from_file_location("gold_fix_ligatures", _PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["gold_fix_ligatures"] = tool
_spec.loader.exec_module(tool)


def bundle(*segments: tuple[str, str]) -> dict:
    """One source document, one block, the given (text, original_text) segments; an empty target."""
    return {
        "format": "tradurre-bundle",
        "version": 1,
        "book": {"title": "T"},
        "beads": [],
        "runs": [],
        "documents": [
            {"side": "source", "blocks": [
                {"kind": "paragraph", "excluded": False, "page": 3,
                 "segments": [{"text": t, "original_text": o, "bead": None} for t, o in segments]},
            ]},
            {"side": "target", "blocks": []},
        ],
    }


def decision(block, segment, offset, what, cls="pdf", side="source"):
    return {"side": side, "block": str(block), "segment": str(segment), "offset": str(offset),
            "decision": what, "class": cls, "note": ""}


def texts(b: dict) -> list[str]:
    return [s["text"] for s in b["documents"][0]["blocks"][0]["segments"]]


# --- Candidates ---


def test_candidates_are_gaps_after_f_fi_fl_before_a_letter():
    b = bundle(("des fi lms et un chef de gare, du fl ot, l'eff et, 5 f 3, fi .", "x"))
    offsets = [c.offset for c in tool.find_candidates(b) if c.kind == "open"]
    text = b["documents"][0]["blocks"][0]["segments"][0]["text"]
    assert [text[o - 2 : o] for o in offsets] == ["fi", "ef", "fl", "ff"]


def test_a_gap_before_a_hyphen_is_a_candidate_and_one_before_a_digit_or_dot_is_not():
    b = bundle(("trafi -quer 3 f 4 fi . fi", "x"))
    assert len(tool.find_candidates(b)) == 1


def test_capital_th_is_a_candidate_case_sensitively():
    b = bundle(("le Th ora, un mon th ora, TH ora, Th 3, Th .", "x"))
    text = b["documents"][0]["blocks"][0]["segments"][0]["text"]
    offsets = [c.offset for c in tool.find_candidates(b) if c.kind == "open"]
    assert [text[o - 2 : o] for o in offsets] == ["Th"]


def test_translator_gaps_include_a_capital_th():
    assert tool.translator_gaps("le Th ora", "le Thora") == [(5, 5)]
    assert tool.translator_gaps("un mon th ora", "un monthora") == []


def test_a_th_stray_decision_applies_and_changes_whitespace_only():
    b = bundle(("le Th ora de Th ula", "x"))
    out = tool.apply_decisions(b, [decision(0, 0, 5, "join")] + [decision(0, 0, 15, "keep")])
    assert texts(out) == ["le Thora de Th ula"]
    assert tool.check_gold(b, out)["whitespace removed"] == 1


def test_translator_gaps_are_found_by_comparing_with_the_original():
    original = "Il a souff ert, un cer-veau, des fi lms."
    text = "Il a souffert, un cerveau, des fi lms."
    assert tool.translator_gaps(original, text) == [(10, 10)]  # the hyphen removal is not a ligature fix
    b = bundle((text, original))
    kinds = [(c.kind, c.offset) for c in tool.find_candidates(b)]
    assert ("translator", 10) in kinds
    assert [k for k, _ in kinds].count("open") == 1


def test_classify_run():
    assert tool.classify_run((-3.2,)) == "stray"
    assert tool.classify_run((-6.0, -3.0)) == "stray"
    assert tool.classify_run((0.0,)) == "real"
    assert tool.classify_run((4.9,)) == "real"
    assert tool.classify_run((-6.0, -3.0, 0.0)) == "ligature+real"


# --- Apply ---


def test_apply_joins_only_the_join_rows():
    b = bundle(("des fi lms et le fi l.", "des fi lms et le fi l."))
    rows = [decision(0, 0, 6, "join"), decision(0, 0, 19, "keep")]
    assert [c.offset for c in tool.find_candidates(b)] == [6, 19]
    assert texts(tool.apply_decisions(b, rows)) == ["des films et le fi l."]


def test_apply_with_two_joins_in_one_segment_keeps_offsets_right():
    text = "fi lms, fl ots, eff et"
    b = bundle((text, text))
    rows = [decision(0, 0, o, "join") for o in (2, 10, 19)]
    assert [c.offset for c in tool.find_candidates(b)] == [2, 10, 19]
    assert texts(tool.apply_decisions(b, rows)) == ["films, flots, effet"]


def test_doubtful_rows_are_not_applied():
    b = bundle(("fi lms", "fi lms"))
    assert texts(tool.apply_decisions(b, [decision(0, 0, 2, "doubtful", "context")])) == ["fi lms"]


def test_apply_does_not_change_its_input():
    b = bundle(("fi lms", "fi lms"))
    tool.apply_decisions(b, [decision(0, 0, 2, "join")])
    assert texts(b) == ["fi lms"]


def test_apply_fails_when_the_offset_is_not_a_candidate():
    b = bundle(("fi lms", "fi lms"))
    with pytest.raises(ValueError, match="does not match a candidate"):
        tool.apply_decisions(b, [decision(0, 0, 3, "join")])
    with pytest.raises(ValueError, match="does not match a candidate"):
        tool.apply_decisions(b, [decision(0, 1, 2, "join")])


def test_apply_fails_when_a_candidate_is_undecided_or_decided_twice():
    b = bundle(("fi lms, fl ots", "x"))
    with pytest.raises(ValueError, match="no decision"):
        tool.apply_decisions(b, [decision(0, 0, 2, "join")])
    with pytest.raises(ValueError, match="duplicate"):
        tool.apply_decisions(b, [decision(0, 0, 2, "join"), decision(0, 0, 2, "keep"), decision(0, 0, 10, "join")])


def test_apply_never_reverts_the_translators_edit_and_may_fix_another_gap_in_the_segment():
    original = "un eff et et des fi lms"
    text = "un effet et des fi lms"  # she closed the first gap
    b = bundle((text, original))
    candidates = tool.find_candidates(b)
    assert [(c.kind, c.offset) for c in candidates] == [("translator", 6), ("open", 18)]
    rows = [decision(0, 0, c.offset, "join", "translator" if c.kind == "translator" else "pdf") for c in candidates]
    assert texts(tool.apply_decisions(b, rows)) == ["un effet et des films"]
    reverting = [decision(0, 0, c.offset, "keep", "translator" if c.kind == "translator" else "pdf")
                 for c in candidates]
    with pytest.raises(ValueError, match="cannot be reverted"):
        tool.apply_decisions(b, reverting)


def test_apply_checks_the_class_matches_the_kind():
    original = "un eff et"
    b = bundle(("un effet", original))
    with pytest.raises(ValueError, match="class"):
        tool.apply_decisions(b, [decision(0, 0, 6, "join", "pdf")])


def test_decisions_file_rejects_unknown_values(tmp_path):
    path = tmp_path / "d.tsv"
    path.write_text("side\tblock\tsegment\toffset\tdecision\tclass\tnote\nsource\t0\t0\t2\tmaybe\tpdf\t\n")
    with pytest.raises(ValueError):
        tool.read_decisions(path)


# --- Check ---


def test_check_accepts_removed_whitespace_only():
    original = bundle(("fi lms, fl ots", "fi lms, fl ots"))
    gold = tool.apply_decisions(original, [decision(0, 0, 2, "join"), decision(0, 0, 10, "keep")])
    assert tool.check_gold(original, gold) == {
        "segments changed": 1, "whitespace removed": 1, "translator fixes kept": 0}


def test_check_rejects_a_changed_letter_added_whitespace_or_another_field():
    original = bundle(("fi lms", "fi lms"))

    def changed(**edit):
        gold = json.loads(json.dumps(original))
        seg = gold["documents"][0]["blocks"][0]["segments"][0]
        seg.update(edit)
        return gold

    with pytest.raises(AssertionError, match="whitespace only"):
        tool.check_gold(original, changed(text="fi mls"))
    with pytest.raises(AssertionError, match="whitespace only"):
        tool.check_gold(original, changed(text="filmz"))
    with pytest.raises(AssertionError, match="whitespace added"):
        tool.check_gold(original, changed(text="fi  lms"))
    with pytest.raises(AssertionError, match="other than segment text"):
        tool.check_gold(original, changed(original_text="films"))
    gold = changed()
    gold["documents"][0]["blocks"][0]["excluded"] = True
    with pytest.raises(AssertionError, match="other than segment text"):
        tool.check_gold(original, gold)


def test_check_counts_the_translators_fixes_kept():
    b = bundle(("un effet", "un eff et"))
    assert tool.check_gold(b, tool.apply_decisions(b, [decision(0, 0, 6, "join", "translator")]))[
        "translator fixes kept"] == 1


# --- Writing, and the survey ---


def test_write_bundle_is_deterministic_and_has_one_entry(tmp_path):
    b = bundle(("fi lms", "fi lms"))
    tool.write_bundle(tmp_path / "a.zip", b)
    tool.write_bundle(tmp_path / "b.zip", b)
    assert (tmp_path / "a.zip").read_bytes() == (tmp_path / "b.zip").read_bytes()
    assert zipfile.ZipFile(tmp_path / "a.zip").namelist() == ["bundle.json"]
    assert tool.read_bundle(tmp_path / "a.zip") == b


def test_dropped_survey_finds_a_missing_group_in_a_token_and_between_fragments():
    common = "Le difficile est fini. Le difficile est fini. Le difficile est fini. "
    b = bundle((common + "Un diicile cas. Il faut dé nir ce mot. dé fini dé fini.", "x"))
    found = {(shape, repair) for *_, shape, repair in tool.dropped_survey(b)}
    assert ("inside-token", "difficile") in found
    b = bundle(("Le définir est utile. Il faut définir ce mot. Il faut dé nir ce mot.", "x"))
    assert any(shape == "fragment-gap" and repair == "définir" for *_, shape, repair in tool.dropped_survey(b))
