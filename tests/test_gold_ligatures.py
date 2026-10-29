"""Tests for the ligature metric of the gold (`tradurre/services/gold.py`, `scripts/gold_score.py`).

Synthetic text only. The library test needs `library/femur.gold.zip` (copyrighted, local) and asserts counts only.
"""

import io
import json
import zipfile
from pathlib import Path

import pytest

from tradurre.db import get_connection
from tradurre.services.bundle import export_bundle
from tradurre.services.gold import (
    LIGATURE_GAP, Layer, layer_from_bundle, ligature_positions, score, score_ligatures,
)

from tests.test_books_api import _docx
from tests.test_gold import _script, client, db_path  # noqa: F401  (fixtures)

gold_score = _script("gold_score")

LIBRARY = Path(__file__).resolve().parent.parent / "library"

# "fi nal" and "Th ing" are slips, "of ten" is kept as a real space; each text is invented.
ORIGINAL = ["Un fi nal gris.", "Th ing of ten."]
CORRECTED = ["Un final gris.", "Thing of ten."]


def _gold(original=ORIGINAL, corrected=CORRECTED):
    return Layer([(t, 0) for t in original], [("Cible.", 0)], [True], {"source": list(corrected), "target": ["Cible."]})


def _predicted(texts):
    return Layer([(t, 0) for t in texts], [("Cible.", 0)], [True])


def test_pattern_is_shared_and_case_sensitive_for_th():
    assert LIGATURE_GAP.search("Th ing")
    assert not LIGATURE_GAP.search("th ing")
    assert LIGATURE_GAP.search("FI nal")
    assert not LIGATURE_GAP.search("fi 12")


def test_gold_positions():
    slips, real, skipped = ligature_positions(_gold())["source"]
    assert (len(slips), len(real), skipped) == (2, 1, 0)


def test_perfect_pipeline():
    result = score_ligatures(_gold(), _predicted(CORRECTED))
    total = result.total
    assert (total.slips, total.slips_closed, total.slips_open) == (2, 2, 0)
    assert (total.real, total.real_kept, total.real_joined) == (1, 1, 0)
    assert (total.slip_recall, total.keep_rate) == (1, 1)
    assert result.sides["target"].slips == 0 and result.sides["target"].slip_recall == 1


def test_unchanged_pipeline():
    total = score_ligatures(_gold(), _predicted(ORIGINAL)).total
    assert (total.slips_closed, total.slips_open, total.real_kept) == (0, 2, 1)
    assert (total.slip_recall, total.keep_rate) == (0, 1)


def test_closing_a_real_space_is_a_false_join():
    total = score_ligatures(_gold(), _predicted(["Un final gris.", "Thing often."])).total
    assert (total.real_joined, total.real_kept, total.keep_rate) == (1, 0, 0)


def test_a_segment_boundary_at_the_gap_is_not_a_fix():
    total = score_ligatures(_gold(), _predicted(["Un fi", "nal gris.", "Th", "ing of ten."])).total
    assert (total.slips_closed, total.slips_open) == (0, 2)


def test_whitespace_elsewhere_in_the_run_does_not_matter():
    total = score_ligatures(_gold(), _predicted(["Un fi\n nal gris.", "Thing of ten."])).total
    assert (total.slips_closed, total.slips_open) == (1, 1)


def test_segment_edited_beyond_whitespace_is_skipped():
    gold = _gold(corrected=["Un final gris.", "Thing of-ten."])
    result = score_ligatures(gold, _predicted(CORRECTED))
    total = result.total
    assert (total.skipped_segments, total.slips, total.real) == (1, 1, 0)
    assert (total.slip_recall, total.keep_rate) == (1, 1)  # no real positions: the empty-set convention


def test_stream_mismatch_is_refused_naming_the_side():
    with pytest.raises(ValueError, match=r"the gold doesn't match the current extraction \(source\)"):
        score_ligatures(_gold(), _predicted(["Autre."]))


def test_gold_without_corrected_texts_is_refused():
    plain = _predicted(ORIGINAL)
    with pytest.raises(ValueError, match="no corrected texts"):
        score_ligatures(plain, plain)


def test_score_is_unchanged_by_corrected_texts():
    assert score(_gold(), _predicted(ORIGINAL)).alignment_f1 == score(_predicted(ORIGINAL), _predicted(ORIGINAL)).alignment_f1


# --- Bundles ---

def _bundle(segments_by_side):
    """A tiny bundle; each side is a list of blocks, each a (excluded, [(text, original_text, bead)])."""
    documents = [
        {"side": side, "filename": f"{side}.txt", "format": "txt",
         "blocks": [{"kind": "paragraph", "excluded": excluded, "page": None,
                     "segments": [{"text": t, "original_text": o, "bead": b} for t, o, b in segments]}
                    for excluded, segments in blocks]}
        for side, blocks in segments_by_side.items()
    ]
    data = {"format": "tradurre-bundle", "version": 1, "documents": documents,
            "beads": [{"reviewed": True}, {"reviewed": False}]}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("bundle.json", json.dumps(data))
    return out.getvalue()


def test_layer_from_bundle_round_trips_its_fields():
    data = _bundle({
        "source": [(True, [("Titre", "Titre", None)]), (False, [("Un final.", "Un fi nal.", 0)])],
        "target": [(False, [("Cible.", "Cible.", 1)])],
    })
    layer = layer_from_bundle(data)
    assert layer.source == [("Titre", None), ("Un fi nal.", 0)]
    assert layer.target == [("Cible.", 1)]
    assert layer.reviewed == [True, False]
    assert layer.corrected == {"source": ["Titre", "Un final."], "target": ["Cible."]}


# --- The script ---

def test_score_script_with_a_bundle_gold(client, db_path, tmp_path, capsys):  # noqa: F811
    source = _docx(("paragraph", "Un fi nal gris. Il parla."))
    target = _docx(("paragraph", "Una fine grigia. Parlò."))
    resp = client.post("/api/v2/books", files={"source": ("livre.docx", source), "target": ("libro.docx", target)})
    assert resp.status_code == 201
    conn = get_connection(db_path)
    try:
        data = export_bundle(conn, resp.json()["id"])
    finally:
        conn.close()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        bundle = json.loads(z.read("bundle.json"))
    closed = 0
    for document in bundle["documents"]:
        for block in document["blocks"]:
            for segment in block["segments"]:
                if "fi nal" in segment["text"]:
                    segment["text"] = segment["text"].replace("fi nal", "final")
                    closed += 1
    assert closed == 1
    gold = tmp_path / "gold.zip"
    with zipfile.ZipFile(gold, "w") as z:
        z.writestr("bundle.json", json.dumps(bundle))
    (tmp_path / "livre.docx").write_bytes(source)
    (tmp_path / "libro.docx").write_bytes(target)
    capsys.readouterr()

    argv = ["--gold", str(gold), "--source", str(tmp_path / "livre.docx"), "--target", str(tmp_path / "libro.docx")]
    assert gold_score.main(argv) == 0
    out = capsys.readouterr().out
    assert "ligatures, source: slips 1 (closed 0, open 1), real 0 (kept 0, joined 0), skipped segments 0" in out
    assert "ligatures, total: slips 1" in out
    assert "alignment and exclusion are not scored" in out
    assert "alignment:" not in out


# --- The real book ---

@pytest.mark.library
def test_femur_gold_counts():
    path = LIBRARY / "femur.gold.zip"
    if not path.exists():
        pytest.skip(f"{path.name} is not present")
    positions = ligature_positions(layer_from_bundle(path.read_bytes()))
    slips = sum(len(s) for s, _, _ in positions.values())
    real = sum(len(r) for _, r, _ in positions.values())
    skipped = sum(k for _, _, k in positions.values())
    assert (slips, real) == (825, 41)
    assert skipped > 0
