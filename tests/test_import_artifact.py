"""Tests for POST /import/artifact -- loading a pre-aligned artifact into the
existing sentence-review-then-confirm import flow."""

import json

import pytest
from fastapi.testclient import TestClient

from tradurre.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("tradurre.config.DB_PATH", db_path)
    monkeypatch.setattr("tradurre.app.DB_PATH", db_path)
    with TestClient(app) as c:
        yield c


def _sample_artifact(**overrides) -> dict:
    artifact = {
        "format": "tradurre-aligned-bitext",
        "version": 1,
        "title": "Sample Book",
        "source_lang": "fr",
        "target_lang": "it",
        "generated_at": "2026-07-28T00:00:00+00:00",
        "generator": {"pipeline": "test", "stages": ["baseline"]},
        "sections": [
            {
                "paragraphs": [
                    {
                        "sentences": [
                            {
                                "source_text": "Bonjour le monde.",
                                "target_text": "Ciao mondo.",
                                "confidence": 0.95,
                                "method": "anchor",
                                "flags": [],
                            },
                            {
                                "source_text": "Il fait beau.",
                                "target_text": "Fa bel tempo.",
                                "confidence": 0.3,
                                "method": "fallback",
                                "flags": ["low_confidence"],
                            },
                        ]
                    }
                ]
            }
        ],
        "warnings": ["embedding stage skipped: no GPU"],
        "stats": {"counts": {"anchor": 1, "fallback": 1}},
    }
    artifact.update(overrides)
    return artifact


def _post_artifact(client, artifact: dict):
    files = {"artifact_file": ("artifact.json", json.dumps(artifact), "application/json")}
    return client.post("/api/v1/import/artifact", files=files)


class TestImportArtifact:
    def test_flattens_hierarchy_into_sentence_units(self, client):
        resp = _post_artifact(client, _sample_artifact())
        assert resp.status_code == 200
        data = resp.json()

        assert data["title"] == "Sample Book"
        assert data["source_lang"] == "fr"
        assert data["target_lang"] == "it"
        assert len(data["source_sentences"]) == 2
        assert len(data["target_sentences"]) == 2

        first = data["source_sentences"][0]
        assert first["text"] == "Bonjour le monde."
        assert first["confidence"] == 0.95
        assert first["method"] == "anchor"

        second = data["target_sentences"][1]
        assert second["text"] == "Fa bel tempo."
        assert second["flags"] == ["low_confidence"]

    def test_carries_warnings_and_stats(self, client):
        resp = _post_artifact(client, _sample_artifact())
        data = resp.json()
        assert data["warnings"] == ["embedding stage skipped: no GPU"]
        assert data["stats"]["counts"]["anchor"] == 1

    def test_rejects_wrong_format(self, client):
        bad = _sample_artifact()
        bad["format"] = "something-else"
        resp = _post_artifact(client, bad)
        assert resp.status_code == 422

    def test_rejects_malformed_json(self, client):
        files = {"artifact_file": ("artifact.json", "not json", "application/json")}
        resp = client.post("/api/v1/import/artifact", files=files)
        assert resp.status_code == 422

    def test_rejects_missing_required_field(self, client):
        bad = _sample_artifact()
        del bad["source_lang"]
        resp = _post_artifact(client, bad)
        assert resp.status_code == 422


class TestImportArtifactThenConfirm:
    def test_full_flow_creates_project_with_correct_hierarchy(self, client):
        resp = _post_artifact(client, _sample_artifact())
        data = resp.json()

        pairs = []
        for src, tgt in zip(data["source_sentences"], data["target_sentences"]):
            pairs.append({
                "source_html": src["html"],
                "target_html": tgt["html"],
                "source_text": src["text"],
                "target_text": tgt["text"],
                "section": src["section"],
                "paragraph": src["paragraph"],
            })

        confirm_resp = client.post(
            "/api/v1/import/confirm",
            json={
                "title": data["title"],
                "source_lang": data["source_lang"],
                "target_lang": data["target_lang"],
                "pairs": pairs,
            },
        )
        assert confirm_resp.status_code == 201
        project = confirm_resp.json()
        assert project["pair_count"] == 2

        pairs_resp = client.get(f"/api/v1/projects/{project['id']}/pairs")
        stored = pairs_resp.json()
        assert len(stored) == 2
        assert stored[0]["source_text"] == "Bonjour le monde."
        assert stored[1]["target_text"] == "Fa bel tempo."
        assert all(p["section"] == 0 and p["paragraph"] == 0 for p in stored)
