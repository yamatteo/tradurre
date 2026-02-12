"""Tests for the pairs API endpoints, especially position management."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tradurre.app import app
from tradurre.config import DB_PATH as ORIG_DB_PATH
from tradurre.db import get_connection, init_db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Create a test client backed by a temporary database."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("tradurre.config.DB_PATH", db_path)
    monkeypatch.setattr("tradurre.app.DB_PATH", db_path)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def project_id(client):
    """Create a project and return its id."""
    resp = client.post(
        "/api/v1/projects",
        json={"title": "Test", "source_lang": "en", "target_lang": "it"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_pair(client, project_id, source="src", target="tgt", position=None):
    """Helper to create a pair, optionally at a specific position."""
    body = {
        "source_html": f"<p>{source}</p>",
        "target_html": f"<p>{target}</p>",
        "source_text": source,
        "target_text": target,
    }
    if position is not None:
        body["position"] = position
    resp = client.post(f"/api/v1/projects/{project_id}/pairs", json=body)
    return resp


def _get_pairs(client, project_id):
    """Get all pairs for a project, ordered by position."""
    resp = client.get(f"/api/v1/projects/{project_id}/pairs")
    assert resp.status_code == 200
    return resp.json()


class TestCreatePairPositionShift:
    """Test that inserting a pair at a specific position correctly shifts others."""

    def test_insert_at_beginning(self, client, project_id):
        """Insert at position 0 when pairs already exist at 0, 1, 2."""
        # Create 3 pairs at the end (positions 0, 1, 2)
        for i in range(3):
            resp = _create_pair(client, project_id, source=f"original-{i}")
            assert resp.status_code == 201

        # Insert at position 0 — this must shift all existing pairs
        resp = _create_pair(client, project_id, source="inserted", position=0)
        assert resp.status_code == 201, f"Insert failed: {resp.text}"

        pairs = _get_pairs(client, project_id)
        positions = [p["position"] for p in pairs]
        sources = [p["source_text"] for p in pairs]

        assert positions == [0, 1, 2, 3]
        assert sources[0] == "inserted"
        assert sources[1] == "original-0"
        assert sources[2] == "original-1"
        assert sources[3] == "original-2"

    def test_insert_in_middle(self, client, project_id):
        """Insert at position 1 when pairs exist at 0, 1, 2."""
        for i in range(3):
            resp = _create_pair(client, project_id, source=f"original-{i}")
            assert resp.status_code == 201

        resp = _create_pair(client, project_id, source="inserted", position=1)
        assert resp.status_code == 201, f"Insert failed: {resp.text}"

        pairs = _get_pairs(client, project_id)
        positions = [p["position"] for p in pairs]
        sources = [p["source_text"] for p in pairs]

        assert positions == [0, 1, 2, 3]
        assert sources[0] == "original-0"
        assert sources[1] == "inserted"
        assert sources[2] == "original-1"
        assert sources[3] == "original-2"

    def test_insert_at_end(self, client, project_id):
        """Insert at position 3 (after last) — no shifting needed."""
        for i in range(3):
            resp = _create_pair(client, project_id, source=f"original-{i}")
            assert resp.status_code == 201

        resp = _create_pair(client, project_id, source="inserted", position=3)
        assert resp.status_code == 201, f"Insert failed: {resp.text}"

        pairs = _get_pairs(client, project_id)
        positions = [p["position"] for p in pairs]
        sources = [p["source_text"] for p in pairs]

        assert positions == [0, 1, 2, 3]
        assert sources[3] == "inserted"


class TestDeletePairPositionShift:
    """Test that deleting a pair correctly closes the gap in positions."""

    def test_delete_middle(self, client, project_id):
        """Delete the middle pair and verify gap is closed."""
        pair_ids = []
        for i in range(3):
            resp = _create_pair(client, project_id, source=f"s-{i}")
            assert resp.status_code == 201
            pair_ids.append(resp.json()["id"])

        # Delete pair at position 1
        resp = client.delete(f"/api/v1/pairs/{pair_ids[1]}")
        assert resp.status_code == 204

        pairs = _get_pairs(client, project_id)
        positions = [p["position"] for p in pairs]
        sources = [p["source_text"] for p in pairs]

        assert positions == [0, 1]
        assert sources[0] == "s-0"
        assert sources[1] == "s-2"

    def test_delete_first(self, client, project_id):
        """Delete the first pair and verify positions are re-compacted."""
        pair_ids = []
        for i in range(3):
            resp = _create_pair(client, project_id, source=f"s-{i}")
            assert resp.status_code == 201
            pair_ids.append(resp.json()["id"])

        resp = client.delete(f"/api/v1/pairs/{pair_ids[0]}")
        assert resp.status_code == 204

        pairs = _get_pairs(client, project_id)
        positions = [p["position"] for p in pairs]
        sources = [p["source_text"] for p in pairs]

        assert positions == [0, 1]
        assert sources[0] == "s-1"
        assert sources[1] == "s-2"


class TestSplitPairPositionShift:
    """Test that splitting a pair correctly shifts subsequent positions."""

    def test_split_middle(self, client, project_id):
        """Split the middle pair and verify positions are correct."""
        pair_ids = []
        for i in range(3):
            resp = _create_pair(client, project_id, source=f"s-{i}", target=f"t-{i}")
            assert resp.status_code == 201
            pair_ids.append(resp.json()["id"])

        resp = client.post(
            f"/api/v1/pairs/{pair_ids[1]}/split",
            json={
                "source_html_before": "<p>s-1a</p>",
                "source_html_after": "<p>s-1b</p>",
                "target_html_before": "<p>t-1a</p>",
                "target_html_after": "<p>t-1b</p>",
            },
        )
        assert resp.status_code == 201, f"Split failed: {resp.text}"

        pairs = _get_pairs(client, project_id)
        positions = [p["position"] for p in pairs]
        sources = [p["source_text"] for p in pairs]

        assert positions == [0, 1, 2, 3]
        assert sources[0] == "s-0"
        assert sources[1] == "s-1a"
        assert sources[2] == "s-1b"
        assert sources[3] == "s-2"


class TestMergePairPositionShift:
    """Test that merging pairs correctly closes the position gap."""

    def test_merge_middle(self, client, project_id):
        """Merge pair at position 1 with pair at position 2."""
        pair_ids = []
        for i in range(4):
            resp = _create_pair(client, project_id, source=f"s-{i}", target=f"t-{i}")
            assert resp.status_code == 201
            pair_ids.append(resp.json()["id"])

        resp = client.post(f"/api/v1/pairs/{pair_ids[1]}/merge")
        assert resp.status_code == 200, f"Merge failed: {resp.text}"

        pairs = _get_pairs(client, project_id)
        positions = [p["position"] for p in pairs]

        assert positions == [0, 1, 2]
        # Position 0 is unchanged
        assert pairs[0]["source_text"] == "s-0"
        # Position 1 is the merged pair
        assert "s-1" in pairs[1]["source_html"]
        assert "s-2" in pairs[1]["source_html"]
        # Position 2 was the old position 3
        assert pairs[2]["source_text"] == "s-3"
