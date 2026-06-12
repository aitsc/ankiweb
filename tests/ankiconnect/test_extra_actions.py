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


@pytest.fixture
def nclient(tmp_path: Path):
    from ankiweb.notifier import NotifierState
    state = NotifierState(tmp_path / "notify.json")
    with TestClient(create_ankiconnect_app(
            Settings(collection_path=tmp_path / "c.anki2"), notifier=state)) as c:
        yield c  # c.app.state.notifier is `state`


def _post(client, path, **params):
    r = client.post(path, json=params)
    assert r.status_code == 200, r.text
    return r.json()


def _model_names(client):
    return client.post("/actions/modelNames", json={}).json()["result"]


def _add_note(client, deck, model, fields):
    """Add a note (always allowing duplicates) and return its noteId."""
    r = _post(client, "/actions/addNote",
              note={"deckName": deck, "modelName": model, "fields": fields,
                    "options": {"allowDuplicate": True}})
    return r["result"]


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


# ----- extendCardLimits (today's new/review limit add/subtract) -----
def test_extend_card_limits_new(client):
    _post(client, "/actions/createDeck", deck="CS")
    notes = [{"deckName": "CS", "modelName": "Basic", "fields": {"Front": f"Q{i}", "Back": "A"}}
             for i in range(25)]  # > the default daily new limit (20) -> new_count gets capped
    _post(client, "/actions/addNotes", notes=notes)
    base = _post(client, "/extra_actions/extendCardLimits", deck="CS", new=0)["result"]["new_count"]
    assert base > 5  # capped by today's new limit, not 25
    r = _post(client, "/extra_actions/extendCardLimits", deck="CS", new=-5)
    assert r["error"] is None and r["result"]["new_count"] == base - 5
    r = _post(client, "/extra_actions/extendCardLimits", deck="CS", new=5)
    assert r["result"]["new_count"] == base  # back to the cap (deltas accumulate)


def test_extend_card_limits_by_id_and_review(client):
    did = _post(client, "/actions/createDeck", deck="CS2")["result"]
    r = _post(client, "/extra_actions/extendCardLimits", deckId=did, new=1, review=3)
    assert r["error"] is None and r["result"]["deckId"] == did
    assert {"new_count", "learn_count", "review_count"} <= set(r["result"])


def test_extend_card_limits_deck_not_found(client):
    r = _post(client, "/extra_actions/extendCardLimits", deck="NoSuchDeck", new=1)
    assert r["result"] is None and "deck was not found" in r["error"]


def test_extend_card_limits_not_on_root(client):
    body = client.post("/", json={"action": "extendCardLimits", "version": 6,
                                  "params": {"deck": "Default", "new": 1}}).json()
    assert body["result"] is None and "unsupported action" in body["error"]
    assert client.post("/actions/extendCardLimits", json={"deck": "x"}).status_code == 404


# ----- push-notifications config get/set -----
def test_get_notify_config(nclient):
    r = _post(nclient, "/extra_actions/getNotifyConfig")
    assert r["error"] is None
    cfg = r["result"]
    assert cfg["enabled"] is False and cfg["scope"] == "leaf" and cfg["active"] is False
    assert "status" in cfg and "lastError" in cfg["status"]


def test_set_notify_config_partial(nclient):
    r = _post(nclient, "/extra_actions/setNotifyConfig",
              enabled=True, url="http://hook", poll_sec=5)
    assert r["error"] is None
    res = r["result"]
    assert res["enabled"] is True and res["url"] == "http://hook" and res["poll_sec"] == 5
    state = nclient.app.state.notifier
    assert state.config.enabled and state.config.url == "http://hook"
    assert state.changed.is_set()                       # running notifier woken
    # a second partial update changes only the URL; enabled/poll stay
    _post(nclient, "/extra_actions/setNotifyConfig", url="http://hook2")
    assert state.config.enabled is True and state.config.url == "http://hook2"
    assert state.config.poll_sec == 5


def test_set_notify_config_persists(nclient, tmp_path):
    _post(nclient, "/extra_actions/setNotifyConfig", enabled=True, url="http://x",
          scope="all", token="tok")
    from ankiweb.notifier import NotifyConfig
    saved = NotifyConfig.load(tmp_path / "notify.json")
    assert saved.url == "http://x" and saved.scope == "all" and saved.token == "tok"


def test_set_notify_config_bad_token(nclient):
    r = _post(nclient, "/extra_actions/setNotifyConfig", token="secret你")
    assert r["result"] is None and "latin-1" in r["error"]
    assert nclient.app.state.notifier.config.token == ""   # not applied


def test_set_notify_config_scope_normalize_and_resync(nclient):
    _post(nclient, "/extra_actions/setNotifyConfig", scope="bogus", enabled=True,
          url="http://x", resync=True)
    state = nclient.app.state.notifier
    assert state.config.scope == "leaf"          # invalid normalized
    assert state.resync_pending is True          # resync requested


def test_notify_config_unavailable_without_notifier(client):
    # the plain `client` fixture injects no NotifierState
    for action in ("getNotifyConfig", "setNotifyConfig"):
        r = _post(client, f"/extra_actions/{action}")
        assert r["result"] is None and "not available" in r["error"]


def test_notify_config_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/extra_actions/getNotifyConfig" in paths
    assert "/extra_actions/setNotifyConfig" in paths
    assert "/actions/setNotifyConfig" not in paths  # extra-only, not a canonical action


# ----- removeDuplicateNotes (all-fields, deck-scoped de-duplication) -----
def test_remove_duplicate_notes_keeps_oldest(client):
    _post(client, "/actions/createDeck", deck="Dup")
    a = _add_note(client, "Dup", "Basic", {"Front": "Q", "Back": "A"})
    b = _add_note(client, "Dup", "Basic", {"Front": "Q", "Back": "A"})
    c = _add_note(client, "Dup", "Basic", {"Front": "Q", "Back": "A"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="Dup")["result"]
    assert r["duplicateGroups"] == 1
    assert r["duplicateNotes"] == 2
    assert r["deleted"] == 2
    assert r["dryRun"] is False
    assert r["notesScanned"] == 3
    assert r["groups"][0]["model"] == "Basic"
    assert r["groups"][0]["kept"] == a                      # oldest survives
    assert r["groups"][0]["deleted"] == [b, c]              # newer copies, ascending nid
    remaining = client.post("/actions/findNotes", json={"query": "deck:Dup"}).json()["result"]
    assert remaining == [a]


def test_remove_duplicate_notes_dry_run(client):
    _post(client, "/actions/createDeck", deck="DupDry")
    a = _add_note(client, "DupDry", "Basic", {"Front": "Q", "Back": "A"})
    b = _add_note(client, "DupDry", "Basic", {"Front": "Q", "Back": "A"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="DupDry", dryRun=True)["result"]
    assert r["dryRun"] is True
    assert r["duplicateGroups"] == 1 and r["duplicateNotes"] == 1  # 2 identical -> 1 redundant
    assert r["deleted"] == 0                                 # nothing removed
    remaining = client.post("/actions/findNotes", json={"query": "deck:DupDry"}).json()["result"]
    assert sorted(remaining) == sorted([a, b])


def test_remove_duplicate_notes_by_id(client):
    did = _post(client, "/actions/createDeck", deck="DupId")["result"]
    _add_note(client, "DupId", "Basic", {"Front": "Q", "Back": "A"})
    _add_note(client, "DupId", "Basic", {"Front": "Q", "Back": "A"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deckId=did)["result"]
    assert r["deckId"] == did and r["deck"] == "DupId"
    assert r["deleted"] == 1


def test_remove_duplicate_notes_no_duplicates(client):
    _post(client, "/actions/createDeck", deck="Uniq")
    _add_note(client, "Uniq", "Basic", {"Front": "Q1", "Back": "A"})
    _add_note(client, "Uniq", "Basic", {"Front": "Q2", "Back": "A"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="Uniq")["result"]
    assert r["duplicateGroups"] == 0 and r["duplicateNotes"] == 0 and r["deleted"] == 0
    assert r["groups"] == []


def test_remove_duplicate_notes_deck_not_found(client):
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="NoSuchDeck")
    assert r["result"] is None and "deck was not found" in r["error"]
