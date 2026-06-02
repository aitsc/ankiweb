import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _seed(client):
    def seed(col):
        did = col.decks.id("Default")
        col.decks.set_current(did)
        for i in range(2):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"] = f"f{i}"; n["Back"] = f"b{i}"
            col.add_note(n, did)
        return did
    return client.portal.call(client.app.state.service.run, seed)


def test_overview_renders_description_editor(client):
    _seed(client)
    r = client.get("/overview")
    assert "Edit Description" in r.text
    assert "id='descbox'" in r.text
    assert "setdesc:" in r.text


def test_setdesc_persists_and_reloads(client):
    did = _seed(client)
    with client.websocket_connect("/ws?context=overview") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "overview",
                      "arg": "setdesc:" + json.dumps({"desc": "Hello **world**", "md": True})})
        m = ws.receive_json()
        while not (m["type"] == "call" and m["fn"] == "ankiwebReload"):
            m = ws.receive_json()
    deck = client.portal.call(client.app.state.service.run, lambda col: col.decks.get(did))
    assert deck["desc"] == "Hello **world**"
    assert deck["md"] is True
    # the rendered overview now shows the markdown-rendered description
    r = client.get("/overview")
    assert "<strong>world</strong>" in r.text
