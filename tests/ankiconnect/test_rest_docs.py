"""Tests for the typed /actions/<name> REST surface + OpenAPI schemas."""
import inspect
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.ankiconnect.app import create_ankiconnect_app
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.ankiconnect.registry import ACTION_SPECS, EXTRA_ACTION_SPECS


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_ankiconnect_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


@pytest.fixture
def keyed_client(tmp_path: Path):
    cfg = AnkiConnectConfig(api_key="topsecret")
    with TestClient(create_ankiconnect_app(
            Settings(collection_path=tmp_path / "c.anki2"), config=cfg)) as c:
        yield c


def _call(client, action, **params):
    r = client.post("/", json={"action": action, "version": 6, "params": params})
    assert r.status_code == 200
    return r.json()


def _add(client, front="Q"):
    return _call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
                                          "fields": {"Front": front, "Back": "A"}})["result"]


# --- registry completeness guard: model fields must equal the handler's accepted params ---
def test_params_model_matches_handler_signature():
    mismatches = []
    for name, spec in {**ACTION_SPECS, **EXTRA_ACTION_SPECS}.items():  # both namespaces
        if spec.params_model is None:
            continue
        sig = inspect.signature(spec.handler)
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            continue  # handler takes **kwargs -> accepts anything, can't cross-check
        handler_params = {p for p in sig.parameters if p != "rt"}
        model_fields = set(spec.params_model.model_fields.keys())
        if model_fields != handler_params:
            mismatches.append({"action": name, "model_only": sorted(model_fields - handler_params),
                               "handler_only": sorted(handler_params - model_fields)})
    assert not mismatches, mismatches


# --- OpenAPI shape: one documented /actions/<name> per action, with distinct schemas ---
def test_openapi_has_a_route_per_action(client):
    schema = client.get("/openapi.json").json()
    routed = {p[len("/actions/"):] for p in schema["paths"] if p.startswith("/actions/")}
    # exactly one route per registered action (the router's source of truth)
    assert routed == set(ACTION_SPECS)
    assert len(routed) >= 121  # the full ankiweb action surface


def test_openapi_tag_descriptions(client):
    tags = {t["name"]: t.get("description", "")
            for t in client.get("/openapi.json").json().get("tags", [])}
    assert "actions" in tags and "extra_actions" in tags
    assert "Native AnkiConnect actions" in tags["actions"] and "POST /" in tags["actions"]
    assert "NOT part of AnkiConnect" in tags["extra_actions"]
    assert "/extra_actions/" in tags["extra_actions"]


def test_openapi_distinct_request_schemas(client):
    schema = client.get("/openapi.json").json()
    comps = schema["components"]["schemas"]
    # the cards models we authored show up as named schemas
    assert "FindCardsParams" in comps and "SetEaseFactorsParams" in comps
    ref = schema["paths"]["/actions/setEaseFactors"]["post"]["requestBody"]["content"][
        "application/json"]["schema"]["$ref"]
    assert ref.endswith("/SetEaseFactorsParams")


# --- behavior parity: REST route returns exactly what POST / does (same dispatch_one) ---
def test_rest_matches_canonical_post(client):
    _add(client, "parity")
    canonical = _call(client, "findCards", query="deck:Default")["result"]
    rest = client.post("/actions/findCards", json={"query": "deck:Default"}).json()
    assert rest == {"result": canonical, "error": None}


def test_rest_invalid_id_leniency(client):
    # the hardened behavior flows through the REST route too
    rest = client.post("/actions/answerCards",
                       json={"answers": [{"cardId": 99999, "ease": 3}]}).json()
    assert rest == {"result": [False], "error": None}


def test_rest_extra_param_forbidden(client):
    # extra="forbid" on the typed model -> 422 (the canonical POST / stays lenient separately)
    r = client.post("/actions/findCards", json={"query": "x", "bogus": 1})
    assert r.status_code == 422


# --- apiKey gate via X-API-Key header ---
def test_rest_apikey_required_when_configured(keyed_client):
    no_key = keyed_client.post("/actions/findCards", json={"query": "deck:Default"}).json()
    assert no_key["error"] and "api key" in no_key["error"].lower()
    ok = keyed_client.post("/actions/findCards", json={"query": "deck:Default"},
                           headers={"X-API-Key": "topsecret"}).json()
    assert ok["error"] is None and isinstance(ok["result"], list)


def test_canonical_post_body_key_still_works(keyed_client):
    # POST / continues to read the key from the body, as upstream does
    r = keyed_client.post("/", json={"action": "findCards", "version": 6,
                                     "params": {"query": "deck:Default"}, "key": "topsecret"})
    assert r.json()["error"] is None
