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


def _err(client, action, **params):
    r = client.post("/", json={"action": action, "version": 6, "params": params})
    return r.json()["error"]


def test_update_note_fields_and_tags(client):
    nid = _call(client, "addNote", note=_basic(front="u1"))
    assert _call(client, "updateNoteFields",
                 note={"id": nid, "fields": {"Back": "newback"}}) is None
    info = _call(client, "notesInfo", notes=[nid])[0]
    assert info["fields"]["Back"]["value"] == "newback"
    assert _call(client, "updateNote", note={"id": nid, "tags": ["x", "y"]}) is None
    assert set(_call(client, "getNoteTags", note=nid)) == {"x", "y"}


def test_bulk_tags(client):
    nid = _call(client, "addNote", note=_basic(front="t1"))
    assert _call(client, "addTags", notes=[nid], tags="marked blue") is None
    assert "marked" in _call(client, "getNoteTags", note=nid)
    assert _call(client, "removeTags", notes=[nid], tags="blue") is None
    assert "blue" not in _call(client, "getNoteTags", note=nid)
    assert "marked" in _call(client, "getTags")


def test_clear_unused_tags(client):
    assert _call(client, "clearUnusedTags") is None


# Task 3: Note query/info/delete actions
def test_notes_info_shape(client):
    nid = _call(client, "addNote", note=_basic(front="info1"))
    info = _call(client, "notesInfo", notes=[nid])[0]
    assert info["noteId"] == nid
    assert info["modelName"] == "Basic"
    assert info["fields"]["Front"]["value"] == "info1"
    assert info["fields"]["Front"]["order"] == 0
    assert isinstance(info["tags"], list) and isinstance(info["cards"], list)


def test_notes_info_by_query(client):
    _call(client, "addNote", note=_basic(front="byq"))
    res = _call(client, "notesInfo", query="deck:Default")
    assert len(res) == 1


def test_delete_notes(client):
    nid = _call(client, "addNote", note=_basic(front="del"))
    assert _call(client, "deleteNotes", notes=[nid]) is None
    assert _call(client, "findNotes", query="deck:Default") == []


def test_cards_to_notes(client):
    nid = _call(client, "addNote", note=_basic(front="c2n"))
    cards = _call(client, "findCards", query="deck:Default")
    assert _call(client, "cardsToNotes", cards=cards) == [nid]


def test_notes_mod_time(client):
    nid = _call(client, "addNote", note=_basic(front="mt"))
    res = _call(client, "notesModTime", notes=[nid])
    assert res[0]["noteId"] == nid and isinstance(res[0]["mod"], int)
