import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gank_api import storage
from gank_api.config import settings
from gank_api.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "db.sqlite3")

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({"1": [2], "2": [1, 3], "3": [2]}))
    monkeypatch.setattr(settings, "universe_graph_path", graph_path)

    conn = storage.connect(settings.db_path)
    conn.execute(
        "INSERT INTO gank_events (killmail_id, sequence_id, occurred_at, solar_system_id, region_id, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, 1, datetime.now(UTC).isoformat(), 1, 10000002, json.dumps({"killmail_id": 1})),
    )
    conn.execute(
        "INSERT INTO gank_events (killmail_id, sequence_id, occurred_at, solar_system_id, region_id, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (2, 2, datetime.now(UTC).isoformat(), 1, 10000043, json.dumps({"killmail_id": 2})),
    )
    conn.commit()
    conn.close()

    with TestClient(app) as test_client:
        yield test_client


def test_feed_filters_by_region_id(client: TestClient):
    resp = client.get("/feed", params={"region_id": 10000002})
    assert resp.status_code == 200
    assert [e["killmail_id"] for e in resp.json()] == [1]


def test_feed_different_region_returns_different_events(client: TestClient):
    resp = client.get("/feed", params={"region_id": 10000043})
    assert resp.status_code == 200
    assert [e["killmail_id"] for e in resp.json()] == [2]


def test_feed_requires_region_id(client: TestClient):
    resp = client.get("/feed")
    assert resp.status_code == 422  # required query param missing


def test_jump_distance_known_route(client: TestClient):
    resp = client.get("/jump-distance", params={"from_system_id": 1, "to_system_id": 3})
    assert resp.status_code == 200
    assert resp.json() == {"jumps": 2}


def test_jump_distance_same_system(client: TestClient):
    resp = client.get("/jump-distance", params={"from_system_id": 1, "to_system_id": 1})
    assert resp.json() == {"jumps": 0}


def test_jump_distance_no_path_returns_404(client: TestClient):
    resp = client.get("/jump-distance", params={"from_system_id": 1, "to_system_id": 999})
    assert resp.status_code == 404


def test_me_location_requires_auth(client: TestClient):
    resp = client.get("/me/location")
    assert resp.status_code in (401, 403)  # HTTPBearer rejects missing credentials


def test_me_location_rejects_invalid_token(client: TestClient):
    resp = client.get("/me/location", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
