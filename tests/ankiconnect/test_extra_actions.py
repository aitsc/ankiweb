"""Tests for the ankiweb-original /extra_actions/<name> surface (deleteModel)."""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.ankiconnect.app import create_ankiconnect_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_ankiconnect_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _post(client, path, **params):
    r = client.post(path, json=params)
    assert r.status_code == 200, r.text
    return r.json()


def _model_names(client):
    return client.post("/actions/modelNames", json={}).json()["result"]


def test_delete_model_unused(client):
    assert "Basic (and reversed card)" in _model_names(client)
    r = _post(client, "/extra_actions/deleteModel", modelName="Basic (and reversed card)")
    assert r == {"result": True, "error": None}
    assert "Basic (and reversed card)" not in _model_names(client)


def test_delete_model_by_id(client):
    mid = client.post("/actions/modelNamesAndIds", json={}).json()["result"][
        "Basic (optional reversed card)"]
    assert _post(client, "/extra_actions/deleteModel", modelId=mid) == {"result": True, "error": None}
    assert "Basic (optional reversed card)" not in _model_names(client)


def test_delete_model_in_use_fails_and_keeps_it(client):
    client.post("/actions/addNote", json={"note": {"deckName": "Default", "modelName": "Basic",
                "fields": {"Front": "Q", "Back": "A"}}})
    r = _post(client, "/extra_actions/deleteModel", modelName="Basic")
    assert r["result"] is None and "note(s) still use it" in r["error"]
    assert "Basic" in _model_names(client)  # NOT removed


def test_delete_model_not_found(client):
    r = _post(client, "/extra_actions/deleteModel", modelName="NoSuchModel")
    assert r["result"] is None and "model was not found" in r["error"]


def test_delete_model_not_on_canonical_root(client):
    # the canonical POST / dispatcher must NOT know deleteModel
    body = client.post("/", json={"action": "deleteModel", "version": 6,
                                  "params": {"modelName": "Basic (and reversed card)"}}).json()
    assert body["result"] is None and "unsupported action" in body["error"]
    # and it is not under /actions/ either
    assert client.post("/actions/deleteModel", json={"modelName": "x"}).status_code == 404
    # the model is untouched
    assert "Basic (and reversed card)" in _model_names(client)


def test_delete_model_in_openapi(client):
    schema = client.get("/openapi.json").json()
    assert "/extra_actions/deleteModel" in schema["paths"]
    assert "/actions/deleteModel" not in schema["paths"]
    assert "DeleteModelParams" in schema["components"]["schemas"]
    # tagged separately from the canonical actions
    assert "extra_actions" in schema["paths"]["/extra_actions/deleteModel"]["post"]["tags"]
