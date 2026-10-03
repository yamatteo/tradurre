"""Opt-in tests on the reference book (PLAN.md, Stage 3 "Reference book").

`library/contrefeu.*.pdf` is copyrighted and local only: these tests skip without it, and assert counts only,
never text (not in assertions, not in messages).
"""

import re
import time
from pathlib import Path

import pytest

from tradurre.services.extract import EXCLUDED_KINDS, extract

LIBRARY = Path(__file__).resolve().parent.parent / "library"

pytestmark = pytest.mark.library

_NUMBER_ONLY = re.compile(r"^\s*([0-9]+|[ivxlcdm]+)\s*$", re.IGNORECASE)


@pytest.fixture(scope="module", params=["fr", "it"])
def side(request):
    path = LIBRARY / f"contrefeu.{request.param}.pdf"
    if not path.exists():
        pytest.skip(f"{path.name} is not present")
    return request.param, extract(path.name, path.read_bytes()).blocks


@pytest.fixture(scope="module")
def both():
    blocks = {}
    for lang in ("fr", "it"):
        path = LIBRARY / f"contrefeu.{lang}.pdf"
        if not path.exists():
            pytest.skip(f"{path.name} is not present")
        blocks[lang] = extract(path.name, path.read_bytes()).blocks
    return blocks


def test_page_numbers_are_found(side):
    lang, blocks = side
    count = sum(b.kind == "page_number" for b in blocks)
    assert count >= {"fr": 110, "it": 150}[lang], f"{lang}: {count} page_number blocks"


def test_no_stray_numbers_in_included_text(side):
    lang, blocks = side
    stray = sum(b.kind not in EXCLUDED_KINDS and b.kind != "heading" and bool(_NUMBER_ONLY.match(b.text))
                for b in blocks)
    assert stray == 0, f"{lang}: {stray} included number-only blocks that aren't headings"


def test_same_number_of_chapter_numbers_on_both_sides(both):
    counts = {lang: sum(b.kind == "heading" and bool(_NUMBER_ONLY.match(b.text)) for b in blocks)
              for lang, blocks in both.items()}
    assert counts["fr"] == counts["it"], f"number-only headings: {counts}"


def test_import_through_the_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from tradurre.app import app

    paths = [LIBRARY / f"contrefeu.{lang}.pdf" for lang in ("fr", "it")]
    for path in paths:
        if not path.exists():
            pytest.skip(f"{path.name} is not present")
    monkeypatch.setattr("tradurre.config.DB_PATH", tmp_path / "library.db")
    monkeypatch.setattr("tradurre.app.DB_PATH", tmp_path / "library.db")
    with TestClient(app) as client:
        start = time.perf_counter()
        resp = client.post("/api/v2/books", files={
            "source": (paths[0].name, paths[0].read_bytes()), "target": (paths[1].name, paths[1].read_bytes()),
        })
        elapsed = time.perf_counter() - start
        assert resp.status_code == 201, resp.status_code
        book = client.get(f"/api/v2/books/{resp.json()['id']}").json()
    beads = book["beads"]
    one_sided = sum(not b["source"] or not b["target"] for b in beads)
    print(f"\nimport: {elapsed:.1f} s, {len(beads)} beads, {one_sided} one-sided")
    assert len(beads) > 1000, f"{len(beads)} beads"
