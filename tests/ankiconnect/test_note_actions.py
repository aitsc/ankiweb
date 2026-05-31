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


def _basic(front="Q1", back="A1", deck="Default", **extra):
    return {"deckName": deck, "modelName": "Basic", "fields": {"Front": front, "Back": back}, **extra}


def test_add_note_returns_id(client):
    nid = _call(client, "addNote", note=_basic())
    assert isinstance(nid, int)
    assert _call(client, "findNotes", query="deck:Default") == [nid]


def test_add_note_case_insensitive_fields(client):
    nid = _call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
                                         "fields": {"front": "x", "BACK": "y"}})
    assert isinstance(nid, int)


def test_add_note_empty_first_field_errors(client):
    r = client.post("/", json={"action": "addNote", "version": 6, "params": {"note": _basic(front="")}})
    assert "empty" in (r.json()["error"] or "").lower()


def test_add_note_duplicate_errors_unless_allowed(client):
    _call(client, "addNote", note=_basic(front="dup"))
    r = client.post("/", json={"action": "addNote", "version": 6, "params": {"note": _basic(front="dup")}})
    assert "duplicate" in (r.json()["error"] or "").lower()
    nid = _call(client, "addNote", note=_basic(front="dup", options={"allowDuplicate": True}))
    assert isinstance(nid, int)


def test_can_add_note(client):
    assert _call(client, "canAddNote", note=_basic(front="ok")) is True
    assert _call(client, "canAddNote", note=_basic(front="")) is False


def test_can_add_note_with_error_detail(client):
    res = _call(client, "canAddNoteWithErrorDetail", note=_basic(front=""))
    assert res["canAdd"] is False and "error" in res


def test_add_notes_success_returns_ids(client):
    res = _call(client, "addNotes", notes=[_basic(front="g1"), _basic(front="g2")])
    assert len(res) == 2 and all(isinstance(i, int) for i in res)


def test_add_notes_errors_and_rolls_back_on_any_failure(client):
    r = client.post("/", json={"action": "addNotes", "version": 6,
                               "params": {"notes": [_basic(front="g1"), _basic(front="")]}})
    assert r.json()["error"] is not None
    assert _call(client, "findNotes", query="deck:Default") == []


def test_can_add_notes_batch(client):
    res = _call(client, "canAddNotes", notes=[_basic(front="ok"), _basic(front="")])
    assert res == [True, False]
