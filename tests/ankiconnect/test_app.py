import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.ankiconnect.app import create_ankiconnect_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    with TestClient(create_ankiconnect_app(settings)) as c:
        yield c


def test_version_action(client):
    r = client.post("/", json={"action": "version", "version": 6})
    assert r.status_code == 200
    assert r.json() == {"result": 6, "error": None}


def test_empty_get_is_probe(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"apiVersion": "AnkiConnect v.6"}


def test_disallowed_origin_403(client):
    r = client.post("/", json={"action": "version", "version": 6},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_localhost_origin_ok_with_acao(client):
    r = client.post("/", json={"action": "version", "version": 6},
                    headers={"Origin": "http://localhost"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost"


def test_options_preflight(client):
    r = client.options("/", headers={"Origin": "http://localhost"})
    assert r.status_code == 200
    assert "access-control-allow-origin" in r.headers
