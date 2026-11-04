"""Tests for `scripts/gold_fix_beads.py`, on synthetic text only."""

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).parent.parent / "scripts" / "gold_fix_beads.py"
_spec = importlib.util.spec_from_file_location("gold_fix_beads", _PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["gold_fix_beads"] = tool
_spec.loader.exec_module(tool)


def seg(text: str, bead: int | None) -> dict:
    return {"text": text, "original_text": text, "bead": bead}


def bundle() -> dict:
    """Source beads: 0 "kolo", 1 "mira" + "senu", 2 "tora"; target beads 0-2 one segment each."""
    def doc(side, segments):
        return {"side": side, "filename": "a", "format": "txt",
                "blocks": [{"kind": "paragraph", "excluded": False, "page": 1, "segments": [s]} for s in segments]}
    return {
        "format": "tradurre-bundle", "version": 1, "app_version": "0.2.0", "exported_at": "2026-10-01T00:00:00",
        "book": {"title": "T", "source_lang": "fr", "target_lang": "it",
                 "created_at": "2026-10-01", "updated_at": "2026-10-01"},
        "beads": [{"confidence": 1.0, "method": "manual", "reviewed": False} for _ in range(3)],
        "runs": [],
        "documents": [
            doc("source", [seg("kolo.", 0), seg("mira.", 1), seg("senu.", 1), seg("tora.", 2)]),
            doc("target", [seg("zoru.", 0), seg("fimu.", 1), seg("tuvo.", 2)]),
        ],
    }


def row(side, src, dst, text, note="x"):
    return {"side": side, "from_bead": str(src), "to_bead": str(dst), "fingerprint": tool.fingerprint(text),
            "note": note}


def beads_of(b, side):
    return [(s["original_text"], s["bead"]) for s in tool._segments(b, side)]


def test_a_move_is_applied_and_nothing_else_changes():
    original = bundle()
    fixed, counts = tool.apply_decisions(bundle(), [row("source", 1, 2, "senu.")])
    assert counts == {"applied": 1, "skipped": 0}
    assert beads_of(fixed, "source") == [("kolo.", 0), ("mira.", 1), ("senu.", 2), ("tora.", 2)]
    assert beads_of(fixed, "target") == beads_of(original, "target")
    assert fixed["beads"] == original["beads"]
    tool.check_restores(fixed)


def test_a_second_run_skips_the_applied_rows():
    rows = [row("source", 1, 2, "senu."), row("source", 1, 0, "mira.")]
    once, _ = tool.apply_decisions(bundle(), rows)
    again, counts = tool.apply_decisions(once, rows)
    assert counts == {"applied": 0, "skipped": 2}
    assert again == once


def test_a_move_between_beads_that_are_not_adjacent_fails():
    with pytest.raises(tool.FixError, match="not adjacent"):
        tool.apply_decisions(bundle(), [row("source", 0, 2, "kolo.")])


def test_a_missing_or_ambiguous_fingerprint_fails():
    with pytest.raises(tool.FixError, match="no segment"):
        tool.apply_decisions(bundle(), [row("source", 1, 2, "nope.")])
    b = bundle()
    b["documents"][0]["blocks"][2]["segments"][0] = seg("mira.", 1)
    with pytest.raises(tool.FixError, match="2 segments"):
        tool.apply_decisions(b, [row("source", 1, 2, "mira.")])


def test_a_move_that_empties_a_bead_fails():
    with pytest.raises(tool.FixError, match="empty"):
        tool.apply_decisions(bundle(), [row("source", 0, 1, "kolo."), row("target", 0, 1, "zoru.")])
    # a bead that keeps the other side's segment is fine
    fixed, _ = tool.apply_decisions(bundle(), [row("source", 0, 1, "kolo.")])
    assert beads_of(fixed, "source")[0] == ("kolo.", 1)


def test_main_writes_a_deterministic_clean_bundle(tmp_path):
    gold, decisions, out = tmp_path / "g.zip", tmp_path / "d.tsv", tmp_path / "o.zip"
    gold.write_bytes(tool.bundle_bytes(bundle()))
    decisions.write_text("side\tfrom_bead\tto_bead\tfingerprint\tnote\n"
                         f"source\t1\t2\t{tool.fingerprint('senu.')}\tmoved\n", encoding="utf-8")
    argv = ["--gold", str(gold), "--decisions", str(decisions), "--out", str(out)]
    assert tool.main(argv) == 0
    first = out.read_bytes()
    assert tool.main(["--gold", str(out), "--decisions", str(decisions), "--out", str(out)]) == 0
    assert out.read_bytes() == first
    assert gold.read_bytes() == tool.bundle_bytes(bundle())
