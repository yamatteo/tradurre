"""Tests for search over the bead index (tradurre.domain.search)."""

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain.history import transaction
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.search import END, START, _unfold_highlight, fts_query, search_beads


def _add_project(conn, project_id, title):
    conn.execute(
        "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
        "VALUES (?, ?, 'fr', 'it', 'now', 'now')",
        (project_id, title),
    )


@pytest.fixture()
def db(tmp_path):
    """p1 "Contre": A (s1 | t1), B (s2 | t2) reviewed, an excluded footnote. p2 "Saisons": one bead."""
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with transaction(conn):
        _add_project(conn, "p1", "Contre")
        _add_project(conn, "p2", "Saisons")
        (s1, s2), _ = create_document(conn, "p1", "source", "fr.txt", "txt", [
            NewBlock("paragraph", ["Le désœuvrement de l’homme.", "Il partit sans un mot."]),
            NewBlock("footnote", ["Zanzibar introuvable."], excluded=True),
        ])
        (t1, t2), = create_document(conn, "p1", "target", "it.txt", "txt", [
            NewBlock("paragraph", ["L'ozio dell'uomo.", "Partì senza una parola."]),
        ])
        a, b = append_beads(conn, "p1", [NewBead([s1], [t1], 0.9, "anchor"), NewBead([s2], [t2], 0.9, "anchor")])
        conn.execute("UPDATE beads SET reviewed = 1 WHERE id = ?", (b,))
        (u1,), = create_document(conn, "p2", "source", "fr.txt", "txt", [NewBlock("paragraph", ["Été chaud."])])
        (v1,), = create_document(conn, "p2", "target", "it.txt", "txt", [NewBlock("paragraph", ["Estate calda."])])
        (c,) = append_beads(conn, "p2", [NewBead([u1], [v1], 0.9, "anchor")])
    yield conn, dict(A=a, B=b, C=c)
    conn.close()


# fts_query


def test_fts_query_words_and_phrase():
    assert fts_query("homme partit") == '{source target} : ("homme" "partit")'
    assert fts_query('"de l homme" mot') == '{source target} : ("de l homme" "mot")'


def test_fts_query_folds_ligatures():
    assert fts_query("Désœuvrement") == '{source target} : ("Désoeuvrement")'


def test_fts_query_stray_quote():
    assert fts_query('homme "partit') == '{source target} : ("homme" """partit")'


def test_fts_query_operators_are_literal():
    assert fts_query("homme OR NEAR* -mot") == '{source target} : ("homme" "OR" "NEAR*" "-mot")'


def test_fts_query_sides():
    assert fts_query("mot", "source") == 'source : ("mot")'
    assert fts_query("mot", "target") == 'target : ("mot")'


def test_fts_query_nothing_to_search():
    assert fts_query("") is None
    assert fts_query('  "" " - ') is None


def test_fts_query_bad_side():
    with pytest.raises(ValueError):
        fts_query("mot", "left")


# _unfold_highlight


def test_unfold_ligature_inside():
    assert _unfold_highlight("Le désœuvrement.", f"Le {START}désoeuvrement{END}.") == f"Le {START}désœuvrement{END}."


def test_unfold_ligature_at_start_and_end():
    assert _unfold_highlight("œuvre cæ x", f"{START}oeuvre{END} {START}cae{END} x") == (
        f"{START}œuvre{END} {START}cæ{END} x"
    )


def test_unfold_marker_inside_ligature_never_splits_it():
    assert _unfold_highlight("œ", f"o{START}e{END}") == f"{START}œ{END}"
    assert _unfold_highlight("œ", f"{START}o{END}e") == f"{START}œ{END}"


def test_unfold_without_markers():
    assert _unfold_highlight("Été œ", "Été oe") == "Été œ"


# search_beads


def test_ligature_query_highlights_real_text(db):
    conn, ids = db
    (hit,) = search_beads(conn, "desoeuvrement")
    assert hit["bead_id"] == ids["A"]
    assert hit["source"] == f"Le {START}désœuvrement{END} de l’homme."
    assert hit["target"] == "L'ozio dell'uomo."
    assert (hit["title"], hit["position"], hit["reviewed"], hit["project_id"]) == ("Contre", 1, False, "p1")


def test_phrase_across_apostrophe(db):
    conn, ids = db
    assert [h["bead_id"] for h in search_beads(conn, '"l homme"')] == [ids["A"]]


def test_accents_and_case(db):
    conn, ids = db
    (hit,) = search_beads(conn, "ete")
    assert hit["bead_id"] == ids["C"]
    assert hit["source"] == f"{START}Été{END} chaud."
    assert (hit["title"], hit["position"]) == ("Saisons", 1)
    assert [h["bead_id"] for h in search_beads(conn, "PARTI")] == [ids["B"]]


def test_side_filter(db):
    conn, ids = db
    assert search_beads(conn, "homme", side="target") == []
    assert [h["bead_id"] for h in search_beads(conn, "uomo", side="target")] == [ids["A"]]


def test_project_filter_and_reviewed(db):
    conn, ids = db
    hits = search_beads(conn, "partit", project_id="p1")
    assert [(h["bead_id"], h["position"], h["reviewed"]) for h in hits] == [(ids["B"], 2, True)]
    assert search_beads(conn, "partit", project_id="p2") == []


def test_excluded_text_not_found(db):
    conn, _ = db
    assert search_beads(conn, "zanzibar") == []


def test_hostile_query(db):
    conn, _ = db
    assert search_beads(conn, '"a" OR NEAR(') == []
    assert search_beads(conn, "") == []
