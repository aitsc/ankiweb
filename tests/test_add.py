import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _run(client, fn):
    return client.portal.call(client.app.state.service.run, fn)


def _drain_call(ws, fn, tries=8):
    for _ in range(tries):
        m = ws.receive_json()
        if m["type"] == "call" and m["fn"] == fn:
            return m["args"]
    raise AssertionError(f"no {fn} frame")


def test_add_route_renders(client):
    r = client.get("/add")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="add"' in r.text
    assert "/_anki/js/editor.js" in r.text
    assert "setupEditor" in r.text and "addnote:" in r.text
    assert "id='add-deck'" in r.text and "id='add-notetype'" in r.text
    assert "Default" in r.text and "Basic" in r.text


def test_add_ready_pushes_empty_fields(client):
    with client.websocket_connect("/ws?context=add") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": "addReady"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["noteId"] == 0
        assert [f[0] for f in data["fields"]] == ["Front", "Back"]
        assert all(f[1] == "" for f in data["fields"])
        assert len(data["fonts"]) == 2


def test_addnote_creates_note(client):
    before = _run(client, lambda col: len(col.find_notes("")))
    with client.websocket_connect("/ws?context=add") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": "addReady"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": 'addnote:["Hello","World"]'})
        _drain_call(ws, "ankiwebToast")
    assert _run(client, lambda col: len(col.find_notes(""))) == before + 1
    note = _run(client, lambda col: col.get_note(list(col.find_notes("Hello"))[0]))
    assert note.fields == ["Hello", "World"]


def test_addnote_empty_rejected(client):
    before = _run(client, lambda col: len(col.find_notes("")))
    with client.websocket_connect("/ws?context=add") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": "addReady"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": 'addnote:["<br>",""]'})
        toast = _drain_call(ws, "ankiwebToast")[0]
        assert "empty" in toast.lower()
    assert _run(client, lambda col: len(col.find_notes(""))) == before


def test_setnotetype_reloads_fields(client):
    cloze_id = _run(client, lambda col: col.models.by_name("Cloze")["id"])
    with client.websocket_connect("/ws?context=add") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": "addReady"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": f"setnotetype:{cloze_id}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert "Text" in [f[0] for f in data["fields"]]


def test_setdeck_and_tags_applied(client):
    other = _run(client, lambda col: col.decks.id("Target"))
    with client.websocket_connect("/ws?context=add") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": "addReady"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": f"setdeck:{other}"})
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": 'saveTags:["mytag"]'})
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": 'addnote:["Q","A"]'})
        _drain_call(ws, "ankiwebToast")
    nid = _run(client, lambda col: list(col.find_notes("Q"))[0])
    note = _run(client, lambda col: col.get_note(nid))
    assert "mytag" in note.tags
    assert _run(client, lambda col, n=note: col.get_card(n.card_ids()[0]).did) == other
