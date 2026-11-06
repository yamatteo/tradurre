"""Transferring a gold book's marks and edits onto a fresh import (synthetic texts only)."""

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain.history import transaction, undo
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.services.gold import Layer
from tradurre.services.transfer import apply_transfer, plan_transfer
import scripts.gold_transfer as cli

SOURCE = ["Alfa beta.", "Gamma delta.", "Omega zeta.", "Sigma tau.", "Ypsilon phi."]
TARGET = ["Uno due.", "Tre quattro.", "Cinque sei.", "Sette otto.", "Nove dieci."]


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture()
def conn(db_path):
    c = get_connection(db_path)
    init_db(c)
    with transaction(c):
        c.execute("INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
                  "VALUES ('p1', 'Book', 'fr', 'it', 'now', 'now')")
    yield c
    c.close()


def _book(conn, source, target, beads, excluded_source=()):
    """`source`/`target`: segment texts in one paragraph block each (segments in `excluded_source` go in an excluded
    block of their own, first); `beads`: (source indexes, target indexes) over the included ones."""
    with transaction(conn):
        blocks = [NewBlock("paragraph", [t], excluded=True) for t in excluded_source]
        blocks.append(NewBlock("paragraph", source))
        ids = create_document(conn, "p1", "source", "a.txt", "txt", blocks)[len(excluded_source)]
        (tids,) = create_document(conn, "p1", "target", "b.txt", "txt", [NewBlock("paragraph", target)])
        return append_beads(conn, "p1", [NewBead([ids[i] for i in s], [tids[i] for i in t], 0.9, "length")
                                         for s, t in beads])


def _fresh(conn):
    return _book(conn, SOURCE, TARGET, [([k], [k]) for k in range(5)])


def _gold(corrected=True):
    # Coarser than the fresh book: the first two sentences share a segment and a bead.
    source = ["Alfa beta. Gamma delta.", SOURCE[2], SOURCE[3], "Ypsilon phi."]
    target = ["Uno due. Tre quattro.", TARGET[2], TARGET[3], TARGET[4]]
    layer = Layer([(t, k) for k, t in enumerate(source)], [(t, k) for k, t in enumerate(target)],
                  [True, True, False, True])
    if corrected:
        layer.corrected = {
            "source": ["Alfa beta. Gamma delta!", "Omega zetta.", SOURCE[3], "Ypsilonphi."],
            "target": [target[0], target[1], "Sette otto!", target[3]],
        }
        layer.source[3] = ("Ypsilon phi.", 3)
    return layer


def _levels(conn):
    return [r[0] for r in conn.execute("SELECT review_level FROM beads ORDER BY ord")]


def _texts(conn):
    return [r[0] for r in conn.execute("SELECT text FROM segments ORDER BY id")]


def test_marks(conn):
    ids = _fresh(conn)
    plan = plan_transfer(conn, "p1", _gold())
    # Turn 0 and 1: an edge inside the gold bead; turn 3: gold bead not reviewed; turns 2 and 4 match.
    assert (plan.turns_marked, plan.turns_total) == (2, 5)
    assert plan.beads_to_mark == [ids[2], ids[4]]
    with transaction(conn):
        apply_transfer(conn, "p1", plan, _gold())
    assert _levels(conn) == [0, 0, 2, 0, 2]


def test_edits(conn):
    _fresh(conn)
    conn.execute("UPDATE segments SET original_text = 'Ypsilonphi.', text = 'Ypsilonphi.' WHERE text = 'Ypsilon phi.'")
    conn.commit()
    plan = plan_transfer(conn, "p1", _gold())
    source, target = plan.edits["source"], plan.edits["target"]
    assert (len(source.applied), source.already, source.unplaced) == (1, 0, [0])  # the merged gold segment: unplaced
    assert (source.spacing, source.spacing_matched) == (1, 1)  # "Ypsilonphi.": spacing, the book already has it
    assert (len(target.applied), target.already, target.unplaced) == (1, 0, [])
    with transaction(conn):
        apply_transfer(conn, "p1", plan, _gold())
    assert "Omega zetta." in _texts(conn) and "Sette otto!" in _texts(conn)
    assert "Gamma delta." in _texts(conn)  # the unplaced one is untouched


@pytest.mark.parametrize("corrected", ["Sigmatau.", "Sig-ma tau."])  # whitespace removed; a hyphen added
def test_spacing_edit_is_counted_not_applied(conn, corrected):
    _fresh(conn)
    before = _texts(conn)
    gold = Layer([(t, k) for k, t in enumerate(SOURCE)], [(t, k) for k, t in enumerate(TARGET)], [True] * 5)
    gold.corrected = {"source": list(SOURCE), "target": list(TARGET)}
    gold.corrected["source"][3] = corrected
    plan = plan_transfer(conn, "p1", gold)
    source = plan.edits["source"]
    assert (source.spacing, source.spacing_matched) == (1, 0)
    assert (source.applied, source.already, source.unplaced) == ([], 0, [])
    with transaction(conn):
        apply_transfer(conn, "p1", plan, gold)
    assert _texts(conn) == before


def test_spacing_edit_matched_by_the_fresh_original(conn):
    _fresh(conn)
    conn.execute("UPDATE segments SET original_text = 'Sigmatau.', text = 'Sigmatau.' WHERE text = 'Sigma tau.'")
    conn.commit()
    gold = Layer([(t, k) for k, t in enumerate(SOURCE)], [(t, k) for k, t in enumerate(TARGET)], [True] * 5)
    gold.corrected = {"source": list(SOURCE), "target": list(TARGET)}
    gold.corrected["source"][3] = "Sigmatau."
    source = plan_transfer(conn, "p1", gold).edits["source"]
    assert (source.spacing, source.spacing_matched, source.applied, source.unplaced) == (1, 1, [], [])


def test_empty_corrected_text_is_unplaced(conn):
    _fresh(conn)
    gold = _gold()
    gold.corrected["source"][1] = "  "
    assert plan_transfer(conn, "p1", gold).edits["source"].unplaced == [0, 1]


def test_exclusion_difference_is_reported_not_changed(conn):
    _book(conn, SOURCE[:2], TARGET[:2], [([0, 1], [0, 1])], excluded_source=["Titulus."])
    gold = Layer([("Titulus.", 0), (SOURCE[0], 0), (SOURCE[1], 0)], [(t, 0) for t in TARGET[:2]], [True])
    plan = plan_transfer(conn, "p1", gold)
    assert (plan.exclusions["source"].gold_only, plan.exclusions["source"].fresh_only) == (0, len("Titulus."))
    assert len(plan.exclusions["source"].blocks) == 1
    assert plan.exclusions["target"].blocks == []
    assert conn.execute("SELECT COUNT(*) FROM blocks WHERE excluded = 1").fetchone()[0] == 1


def test_one_undo_reverts_everything(conn):
    _fresh(conn)
    before = _texts(conn)
    with transaction(conn):
        operation = apply_transfer(conn, "p1", plan_transfer(conn, "p1", _gold()), _gold())
    assert operation is not None and _texts(conn) != before and any(_levels(conn))
    with transaction(conn):
        assert undo(conn, "p1") == operation
    assert _texts(conn) == before and _levels(conn) == [0] * 5


def test_dry_run_writes_nothing(conn, db_path, tmp_path, capsys):
    _fresh(conn)
    conn.commit()
    before = conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
    snapshot = (_levels(conn), _texts(conn))
    import json
    from tradurre.services.gold import layer_to_json
    gold_file = tmp_path / "gold.json"
    gold_file.write_text(json.dumps(layer_to_json(_gold(corrected=False))))
    assert cli.main(["--book", "p1", "--gold", str(gold_file), "--db", str(db_path)]) == 0
    assert "dry run" in capsys.readouterr().out
    assert conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == before
    assert (_levels(conn), _texts(conn)) == snapshot
    assert cli.main(["--book", "p1", "--gold", str(gold_file), "--db", str(db_path), "--apply"]) == 0
    assert _levels(conn) == [0, 0, 2, 0, 2]


def test_apply_refused_with_existing_marks(conn):
    ids = _fresh(conn)
    conn.execute("UPDATE beads SET review_level = 1 WHERE id = ?", (ids[0],))
    conn.commit()
    with pytest.raises(ValueError, match="already"):
        apply_transfer(conn, "p1", plan_transfer(conn, "p1", _gold()), _gold())


def test_apply_refused_with_existing_edits(conn):
    _fresh(conn)
    conn.execute("UPDATE segments SET text = 'Altro.' WHERE id = (SELECT MIN(id) FROM segments)")
    conn.commit()
    with pytest.raises(ValueError, match="already"):
        apply_transfer(conn, "p1", plan_transfer(conn, "p1", _gold()), _gold())


def test_text_mismatch_refused(conn):
    _book(conn, SOURCE[:2], TARGET[:2], [([0], [0]), ([1], [1])])
    with pytest.raises(ValueError, match="doesn't match"):
        plan_transfer(conn, "p1", _gold())
