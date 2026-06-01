import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        c.portal.call(c.app.state.service.run, _seed)
        yield c


def _seed(col):
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "CapitalFrance"; n["Back"] = "Paris"
    n.tags = ["geo"]
    col.add_note(n, col.decks.id("Default"))


def _nid(client):
    return client.portal.call(client.app.state.service.run, lambda col: list(col.find_notes(""))[0])


def _drain_call(ws, fn, tries=6):
    for _ in range(tries):
        m = ws.receive_json()
        if m["type"] == "call" and m["fn"] == fn:
            return m["args"]
    raise AssertionError(f"no {fn} frame")


def test_edit_route_renders(client):
    nid = _nid(client)
    r = client.get(f"/edit?nid={nid}")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="editor"' in r.text
    assert "/_anki/js/editor.js" in r.text
    assert "/_anki/css/editor.css" in r.text
    assert "setupEditor" in r.text and f"window.__ankiwebEditNid={nid}" in r.text


def test_editor_load_pushes_note(client):
    nid = _nid(client)
    with client.websocket_connect("/ws?context=editor") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["noteId"] == nid
        assert data["fields"][0][0] == "Front" and data["fields"][0][1] == "CapitalFrance"
        assert data["fields"][1][1] == "Paris"
        assert len(data["fonts"]) == len(data["fields"])
        assert data["fonts"][0][0] and isinstance(data["fonts"][0][1], int)
        assert data["io"] is False
        assert data["tags"] == ["geo"]
        assert "id" in data["meta"] and "modTime" in data["meta"]


def test_editor_blur_saves_field(client):
    nid = _nid(client)
    with client.websocket_connect("/ws?context=editor") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"blur:1:{nid}:Lyon"})
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["fields"][1][1] == "Lyon"
    assert client.portal.call(client.app.state.service.run,
                              lambda col: col.get_note(nid).fields[1]) == "Lyon"


def test_editor_key_saves_field(client):
    nid = _nid(client)
    with client.websocket_connect("/ws?context=editor") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"key:0:{nid}:Berlin"})
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["fields"][0][1] == "Berlin"


def test_editor_blur_munges_bare_br(client):
    nid = _nid(client)
    with client.websocket_connect("/ws?context=editor") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"blur:1:{nid}:<br>"})
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["fields"][1][1] == ""


def test_editor_savetags(client):
    nid = _nid(client)
    with client.websocket_connect("/ws?context=editor") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": 'saveTags:["x","y"]'})
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["tags"] == ["x", "y"]
