import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    with TestClient(create_app(settings)) as c:
        # seed a card so the deck browser has content
        c.portal.call(c.app.state.service.run, _seed)
        yield c


def _seed(col):
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"
    col.add_note(n, col.decks.id("Default"))


def test_root_serves_deckbrowser(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Default" in r.text
    assert 'window.__ankiwebContext="deckbrowser"' in r.text
    assert "/_anki/css/deckbrowser.css" in r.text


def test_deckbrowser_route(client):
    r = client.get("/deckbrowser")
    assert r.status_code == 200
    assert "studiedToday" in r.text


def test_open_command_sets_current_and_navigates(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "deckbrowser", "arg": f"open:{did}"})
        # A run_op-backed command may also broadcast an {type:opchanges} frame; drain
        # until the navigate call (set_current is all-False so usually no opchanges frame,
        # but this is robust for any run_op-backed command).
        msg = ws.receive_json()
        while msg["type"] != "call":
            msg = ws.receive_json()
        assert msg["fn"] == "ankiwebNavigate"
        assert msg["args"] == ["/overview"]
    # current deck is now Default
    cur = client.portal.call(client.app.state.service.run, lambda col: col.decks.get_current_id())
    assert cur == did


def test_overview_route(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    r = client.get("/overview")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="overview"' in r.text
    assert "/_anki/css/overview.css" in r.text


def test_overview_study_navigates_to_reviewer(client):
    with client.websocket_connect("/ws?context=overview") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "overview", "arg": "study"})
        msg = ws.receive_json()
        while msg["type"] != "call":
            msg = ws.receive_json()
        assert msg["fn"] == "ankiwebNavigate"
        assert msg["args"] == ["/reviewer"]


def test_overview_decks_navigates_home(client):
    with client.websocket_connect("/ws?context=overview") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "overview", "arg": "decks"})
        msg = ws.receive_json()
        while msg["type"] != "call":
            msg = ws.receive_json()
        assert msg["fn"] == "ankiwebNavigate"
        assert msg["args"] == ["/deckbrowser"]


def test_reviewer_placeholder(client):
    r = client.get("/reviewer")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="reviewer"' in r.text
    # placeholder offers a way back to decks
    assert "pycmd" in r.text and "decks" in r.text
