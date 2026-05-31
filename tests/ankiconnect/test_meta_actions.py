import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.ankiconnect.app import create_ankiconnect_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_ankiconnect_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _call(client, action, **params):
    r = client.post("/", json={"action": action, "version": 6, "params": params})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None, body["error"]
    return body["result"]


def test_version(client):
    assert _call(client, "version") == 6


def test_api_reflect_lists_actions(client):
    res = _call(client, "apiReflect", scopes=["actions"])
    assert res["scopes"] == ["actions"]
    # deckNames isn't registered until Task 5 (decks); assert meta actions here
    assert "version" in res["actions"] and "requestPermission" in res["actions"]
    assert "multi" in res["actions"]


def test_request_permission_granted_for_localhost(client):
    r = client.post("/", json={"action": "requestPermission", "version": 6},
                    headers={"Origin": "http://localhost"})
    res = r.json()["result"]
    assert res["permission"] == "granted"


def test_get_profiles(client):
    assert _call(client, "getProfiles") == ["User 1"]
    assert _call(client, "getActiveProfile") == "User 1"


def test_reload_collection(client):
    assert _call(client, "reloadCollection") is None


def test_sync_excluded(client):
    r = client.post("/", json={"action": "sync", "version": 6})
    assert r.json()["error"] is not None  # sync is out of scope
