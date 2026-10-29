"""Tests for `scripts/gold_rebase.py`, on synthetic text only."""

import copy
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

_PATH = Path(__file__).parent.parent / "scripts" / "gold_rebase.py"
_spec = importlib.util.spec_from_file_location("gold_rebase", _PATH)
tool = importlib.util.module_from_spec(_spec)
sys.modules["gold_rebase"] = tool
_spec.loader.exec_module(tool)


def blk(kind: str, excluded: bool, *segments: tuple[str, int | None], page: int = 1) -> dict:
    return {"kind": kind, "excluded": excluded, "page": page,
            "segments": [{"text": t, "original_text": t, "bead": b} for t, b in segments]}


def bundle(source: list[dict], target: list[dict], n_beads: int) -> dict:
    return {
        "format": "tradurre-bundle", "version": 1, "app_version": "0.2.0", "exported_at": "2026-10-01T00:00:00",
        "book": {"title": "T", "source_lang": "fr", "target_lang": "it",
                 "created_at": "2026-10-01", "updated_at": "2026-10-01"},
        "beads": [{"confidence": 1.0, "method": "manual", "reviewed": i % 2 == 0} for i in range(n_beads)],
        "runs": [],
        "documents": [
            {"side": "source", "filename": "a.pdf", "format": "pdf", "blocks": source},
            {"side": "target", "filename": "b.pdf", "format": "pdf", "blocks": target},
        ],
    }


def target_blocks() -> list[dict]:
    return [blk("paragraph", False, ("zoru", 0)), blk("paragraph", False, ("fimu pala.", 1)),
            blk("paragraph", False, ("tuvo", 2))]


def split_gold(page_number: tuple[str, int | None], excluded: bool = False) -> dict:
    """A paragraph split by a page number: bead 1 holds the page number and the second half."""
    source = [
        blk("paragraph", False, ("kolo mira", 0)),
        blk("page_number", excluded, page_number),
        blk("paragraph", False, ("senu tora.", 1)),
        blk("paragraph", False, ("luma", 2)),
    ]
    return bundle(source, target_blocks(), 3)


TEXTS = {"source": ["kolo mira senu tora.", "12", "luma"], "target": ["zoru", "fimu pala.", "tuvo"]}
KINDS = {"source": ["paragraph", "page_number", "paragraph"], "target": ["paragraph"] * 3}


def flat(b: dict, side: str = "source") -> list[tuple]:
    return [(s["text"], s["bead"], blk_["excluded"]) for d in b["documents"] if d["side"] == side
            for blk_ in d["blocks"] for s in blk_["segments"]]


def run(b: dict, texts: dict = TEXTS, kinds: dict = KINDS):
    after, stats = tool.rebase(b, texts, kinds)
    return after, stats, tool.check(b, after, texts, stats)


def test_a_split_paragraph_is_merged_and_the_interleaved_block_moves_after_it():
    b = bundle([blk("paragraph", False, ("kolo mira", 0)), blk("footnote", True, ("note", None)),
                blk("paragraph", False, ("senu tora.", 0)), blk("paragraph", False, ("luma", 1))],
               [blk("paragraph", False, ("zoru", 0)), blk("paragraph", False, ("tuvo", 1))], 2)
    texts = {"source": ["kolo mira senu tora.", "note", "luma"], "target": ["zoru", "tuvo"]}
    after, stats, _ = run(b, texts, {"source": ["paragraph", "footnote", "paragraph"], "target": ["paragraph"] * 2})
    source = after["documents"][0]["blocks"]
    assert [[s["text"] for s in x["segments"]] for x in source] == [["kolo mira", "senu tora."], ["note"], ["luma"]]
    assert [x["kind"] for x in source] == ["paragraph", "footnote", "paragraph"]
    assert stats["source"]["merged"] == 1 and stats["source"]["moved"] == 1
    assert stats["source"]["blocks_in"] == 4 and stats["source"]["blocks_out"] == 3
    assert stats["source"]["neutralised"] == 0


def test_the_target_is_unchanged_and_the_input_is_not_modified():
    b = split_gold(("12", 1))
    original = copy.deepcopy(b)
    after, stats, _ = run(b)
    assert b == original
    assert after["documents"][1] == b["documents"][1]
    assert stats["target"]["merged"] == 0 and stats["target"]["moved"] == 0


def test_an_included_moved_block_with_a_bead_is_neutralised():
    b = split_gold(("12", 1))
    after, stats, counts = run(b)
    assert flat(after) == [("kolo mira", 0, False), ("senu tora.", 1, False), ("12", None, True), ("luma", 2, False)]
    pn = after["documents"][0]["blocks"][1]
    assert pn["kind"] == "page_number" and pn["segments"][0]["original_text"] == "12"
    assert stats["source"]["neutralised"] == 1
    assert counts["source segments"] == 4
    assert after["beads"] == b["beads"]


def test_neutralised_bundle_restores_and_passes_the_invariants(tmp_path):
    from tradurre.db import get_connection, init_db
    from tradurre.domain.invariants import check_project
    from tradurre.services.bundle import import_bundle

    b = split_gold(("12", 1))
    after, _, _ = run(b)
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    try:
        book_id = import_bundle(conn, tool.bundle_bytes(after))
        assert check_project(conn, book_id) == []
    finally:
        conn.close()


def test_an_excluded_moved_block_is_left_alone():
    after, stats, _ = run(split_gold(("12", None), excluded=True))
    assert flat(after)[2] == ("12", None, True)
    assert stats["source"]["neutralised"] == 0


def test_an_included_moved_block_without_a_bead_is_left_alone_and_the_check_states_it():
    b = split_gold(("12", None))
    after, stats = tool.rebase(b, TEXTS, KINDS)
    assert flat(after)[2] == ("12", None, False)
    assert stats["source"]["neutralised"] == 0
    with pytest.raises(AssertionError, match="included order"):
        tool.check(b, after, TEXTS, stats)


def test_a_bead_left_without_segments_stops_the_rebase():
    # the page number alone is bead 3; neutralising it would leave that bead empty
    source = [blk("paragraph", False, ("kolo mira", 0)), blk("page_number", False, ("12", 3)),
              blk("paragraph", False, ("senu tora.", 1)), blk("paragraph", False, ("luma", 2))]
    b = bundle(source, target_blocks(), 4)
    with pytest.raises(tool.RebaseError, match="without segments"):
        tool.rebase(b, TEXTS, KINDS)


def test_a_second_run_changes_nothing():
    b = split_gold(("12", 1))
    once, _, _ = run(b)
    twice, stats, _ = run(once)
    assert twice == once
    assert stats["source"]["merged"] == 0 and stats["source"]["moved"] == 0 and stats["source"]["neutralised"] == 0


def test_a_merged_block_is_never_neutralised():
    # both halves are included with beads; the merge keeps them as they are
    source = [blk("paragraph", False, ("kolo", 0)), blk("paragraph", False, ("mira", 0)),
              blk("paragraph", False, ("luma", 1))]
    b = bundle(source, [blk("paragraph", False, ("zoru", 0)), blk("paragraph", False, ("tuvo", 1))], 2)
    texts = {"source": ["kolomira", "luma"], "target": ["zoru", "tuvo"]}
    after, stats, _ = run(b, texts, {"source": ["paragraph"] * 2, "target": ["paragraph"] * 2})
    assert flat(after) == [("kolo", 0, False), ("mira", 0, False), ("luma", 1, False)]
    assert stats["source"]["merged"] == 1 and stats["source"]["neutralised"] == 0


UNMOVED_TEXTS = {"source": ["kolo mira", "12", "senu tora.", "luma"], "target": TEXTS["target"]}


def unmoved(text: str, kind: str = "page_number", bead: int | None = 0):
    """An included, bead-bearing block `text` between two paragraphs that the extraction cuts the same way."""
    source = [blk("paragraph", False, ("kolo mira", 0)), blk(kind, False, (text, bead)),
              blk("paragraph", False, ("senu tora.", 1)), blk("paragraph", False, ("luma", 2))]
    b = bundle(source, target_blocks(), 3)
    texts = {"source": ["kolo mira", text, "senu tora.", "luma"], "target": TEXTS["target"]}
    return b, texts, {"source": ["paragraph", kind, "paragraph", "paragraph"], "target": ["paragraph"] * 3}


def test_an_unmoved_page_number_in_a_bead_is_neutralised_and_the_bundle_restores(tmp_path):
    from tradurre.db import get_connection, init_db
    from tradurre.domain.invariants import check_project
    from tradurre.services.bundle import import_bundle

    b, texts, kinds = unmoved("66")
    after, stats, _ = run(b, texts, kinds)
    assert flat(after) == [("kolo mira", 0, False), ("66", None, True), ("senu tora.", 1, False), ("luma", 2, False)]
    assert stats["source"]["neutralised"] == 1 and stats["source"]["neutralised_moved"] == 0
    assert after["beads"] == b["beads"]
    conn = get_connection(tmp_path / "t.db")
    init_db(conn)
    try:
        assert check_project(conn, import_bundle(conn, tool.bundle_bytes(after))) == []
    finally:
        conn.close()


@pytest.mark.parametrize("text", ["ab", "1a", "1234", "x"])
def test_only_digits_of_at_most_three_characters_qualify(text):
    b, texts, kinds = unmoved(text, bead=1)
    after, stats, _ = run(b, texts, kinds)
    assert after["documents"][0]["blocks"] == b["documents"][0]["blocks"]
    assert stats["source"]["neutralised"] == 0


def test_a_digit_block_the_extraction_keeps_included_is_not_neutralised():
    b, texts, kinds = unmoved("12", kind="heading", bead=1)
    after, stats, _ = run(b, texts, kinds)
    assert after["documents"][0]["blocks"] == b["documents"][0]["blocks"]
    assert stats["source"]["neutralised"] == 0


def test_without_kinds_nothing_is_neutralised():
    b, texts, _ = unmoved("12")
    after, stats = tool.rebase(b, texts)
    assert after["documents"][0]["blocks"] == b["documents"][0]["blocks"]
    assert stats["source"]["neutralised"] == 0


def test_an_unmoved_page_number_alone_in_its_bead_stops_the_rebase():
    b, texts, kinds = unmoved("12", bead=3)
    b["beads"].append(b["beads"][0])
    with pytest.raises(tool.RebaseError, match="without segments"):
        tool.rebase(b, texts, kinds)


def test_a_second_run_on_an_unmoved_page_number_changes_nothing():
    b, texts, kinds = unmoved("66")
    once, _, _ = run(b, texts, kinds)
    twice, stats, _ = run(once, texts, kinds)
    assert twice == once and stats["source"]["neutralised"] == 0


def test_merging_parts_that_differ_in_excluded_fails():
    source = [blk("paragraph", False, ("kolo", 0)), blk("paragraph", True, ("mira", None)),
              blk("paragraph", False, ("luma", 1))]
    b = bundle(source, [blk("paragraph", False, ("zoru", 0)), blk("paragraph", False, ("tuvo", 1))], 2)
    with pytest.raises(tool.RebaseError, match="excluded"):
        tool.rebase(b, {"source": ["kolomira", "luma"], "target": ["zoru", "tuvo"]})


def test_a_text_that_differs_fails():
    with pytest.raises(tool.RebaseError, match="text differs"):
        tool.rebase(split_gold(("12", 1)), {"source": ["kolo xxxx", "12", "luma"], "target": TEXTS["target"]})


def test_leftover_gold_blocks_fail():
    with pytest.raises(tool.RebaseError, match="left over"):
        tool.rebase(split_gold(("12", 1)), {"source": ["kolo mira senu tora."], "target": TEXTS["target"]})


def test_bundle_round_trip_is_deterministic(tmp_path):
    b = split_gold(("12", 1))
    path = tmp_path / "x.zip"
    tool.write_bundle(path, b)
    assert tool.read_bundle(path) == b
    assert path.read_bytes() == tool.bundle_bytes(b)
    with zipfile.ZipFile(path) as z:
        assert json.loads(z.read("bundle.json")) == b
