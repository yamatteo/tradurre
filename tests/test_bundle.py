"""Tests for the project bundle (tradurre.services.bundle)."""

import io
import json
import zipfile

import pytest

from tradurre.db import get_connection, init_db
from tradurre.domain.history import transaction
from tradurre.domain.invariants import check_project
from tradurre.domain.layer import NewBead, NewBlock, append_beads, create_document
from tradurre.domain.search import search_beads
from tradurre.domain.segments import edit_text
from tradurre.services.bundle import BundleError, export_bundle, import_bundle


@pytest.fixture()
def conn(tmp_path):
    """Source: heading [h], running head [r] excluded, paragraph [s1, s2], footnote [f] excluded, paragraph [s3];
    target: paragraph [t0, t1, tx, t2, t3]; beads (h | t0), (s1 | t1) reviewed, ( | tx), (s2 | t2), (s3 | t3);
    s2 edited; one import run with a warning."""
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    with transaction(conn):
        conn.execute(
            "INSERT INTO projects (id, title, source_lang, target_lang, created_at, updated_at) "
            "VALUES ('p1', 'Livre', 'fr', 'it', '2026-10-01', '2026-10-02')"
        )
        (h,), _, (s1, s2), _, (s3,) = create_document(conn, "p1", "source", "fr.pdf", "pdf", [
            NewBlock("heading", ["Chapitre un"], page=1),
            NewBlock("running_head", ["Contrefeu"], excluded=True, page=1),
            NewBlock("paragraph", ["Il partit.", "Il marcha."], page=1),
            NewBlock("footnote", ["Une note."], excluded=True, page=1),
            NewBlock("paragraph", ["Fin."], page=2),
        ])
        (t0, t1, tx, t2, t3), = create_document(conn, "p1", "target", "it.docx", "docx", [
            NewBlock("paragraph", ["Capitolo uno", "Partì.", "Solo qui.", "Camminò.", "Fine."]),
        ])
        beads = append_beads(conn, "p1", [
            NewBead([h], [t0], 0.9, "anchor"),
            NewBead([s1], [t1], 0.8, "length"),
            NewBead([], [tx], 0.2, "length"),
            NewBead([s2], [t2], 0.7, "length"),
            NewBead([s3], [t3], 1.0, "manual"),
        ])
        conn.execute("UPDATE beads SET reviewed = 1 WHERE id = ?", (beads[1],))
        run_id = conn.execute(
            "INSERT INTO runs (project_id, kind, created_at, app_version, stats) "
            "VALUES ('p1', 'import', '2026-10-01', '0.1.0', '{\"beads\": 5}')"
        ).lastrowid
        conn.execute("INSERT INTO warnings (run_id, side, message) VALUES (?, 'source', 'A warning.')", (run_id,))
    with transaction(conn):
        edit_text(conn, "p1", s2, "Il marchait.")
    assert check_project(conn, "p1") == []
    yield conn
    conn.close()


def _json(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return json.loads(z.read("bundle.json"))


def _zip(bundle: dict, name: str = "bundle.json") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(name, json.dumps(bundle))
    return out.getvalue()


def _normal(data: bytes) -> dict:
    bundle = _json(data)
    del bundle["exported_at"]
    return bundle


def _projects(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]


def test_round_trip(conn):
    data = export_bundle(conn, "p1")
    book_id = import_bundle(conn, data)
    assert book_id != "p1"
    assert _normal(export_bundle(conn, book_id)) == _normal(data)
    assert check_project(conn, book_id) == []
    assert {hit["project_id"] for hit in search_beads(conn, "marchait")} == {"p1", book_id}


def test_contents(conn):
    data = export_bundle(conn, "p1")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.namelist() == ["bundle.json"]
    bundle = _json(data)
    assert (bundle["format"], bundle["version"]) == ("tradurre-bundle", 1)
    assert bundle["book"] == {"title": "Livre", "source_lang": "fr", "target_lang": "it",
                              "created_at": "2026-10-01", "updated_at": "2026-10-02"}
    assert [d["side"] for d in bundle["documents"]] == ["source", "target"]
    source = bundle["documents"][0]["blocks"]
    assert [(b["kind"], b["excluded"]) for b in source] == [
        ("heading", False), ("running_head", True), ("paragraph", False), ("footnote", True), ("paragraph", False),
    ]
    assert source[1]["segments"] == [{"text": "Contrefeu", "original_text": "Contrefeu", "bead": None}]
    assert source[2]["segments"][1] == {"text": "Il marchait.", "original_text": "Il marcha.", "bead": 3}
    assert [b["reviewed"] for b in bundle["beads"]] == [False, True, False, False, False]
    assert bundle["runs"] == [{"kind": "import", "created_at": "2026-10-01", "app_version": "0.1.0",
                               "stats": {"beads": 5}, "warnings": [{"side": "source", "message": "A warning."}]}]


def _refused(conn, data: bytes, message: str):
    before = _projects(conn)
    with pytest.raises(BundleError, match=message):
        import_bundle(conn, data)
    assert _projects(conn) == before


def test_refused_not_a_bundle(conn):
    bundle = _json(export_bundle(conn, "p1"))
    _refused(conn, b"garbage", "Not a Tradurre bundle")
    _refused(conn, _zip(bundle, "other.json"), "Not a Tradurre bundle")
    _refused(conn, _zip({**bundle, "format": "other"}), "Not a Tradurre bundle")


def test_refused_newer_version(conn):
    bundle = _json(export_bundle(conn, "p1"))
    _refused(conn, _zip({**bundle, "version": 2}), r"needs a newer Tradurre \(version 2\)")


def test_refused_bead_out_of_range(conn):
    bundle = _json(export_bundle(conn, "p1"))
    bundle["documents"][0]["blocks"][2]["segments"][1]["bead"] = 99
    _refused(conn, _zip(bundle), r"documents\[0\]\.blocks\[2\]\.segments\[1\]\.bead is out of range")


def test_refused_bead_without_segments(conn):
    bundle = _json(export_bundle(conn, "p1"))
    bundle["beads"].append({"confidence": 0.5, "method": "length", "reviewed": False})
    _refused(conn, _zip(bundle), "I3")


def test_refused_excluded_segment_with_bead(conn):
    bundle = _json(export_bundle(conn, "p1"))
    bundle["documents"][0]["blocks"][1]["segments"][0]["bead"] = 0
    _refused(conn, _zip(bundle), "I1")


def test_refused_missing_key_and_wrong_type(conn):
    bundle = _json(export_bundle(conn, "p1"))
    del bundle["beads"][0]["method"]
    _refused(conn, _zip(bundle), r"beads\[0\]\.method is missing")
    bundle = _json(export_bundle(conn, "p1"))
    bundle["documents"][1]["blocks"][0]["excluded"] = "no"
    _refused(conn, _zip(bundle), r"documents\[1\]\.blocks\[0\]\.excluded has the wrong type")


def test_refused_value_the_schema_refuses(conn):
    bundle = _json(export_bundle(conn, "p1"))
    bundle["beads"][0]["method"] = "guess"
    _refused(conn, _zip(bundle), "Malformed bundle: CHECK constraint failed")
