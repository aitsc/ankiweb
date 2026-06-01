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


def _seed(client, n=3):
    def seed(col):
        did = col.decks.id("Default")
        col.decks.set_current(did)
        for i in range(n):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = f"f{i}"; note["Back"] = f"b{i}"
            col.add_note(note, did)
        return did
    return client.portal.call(client.app.state.service.run, seed)


def test_custom_study_route_renders_form(client):
    _seed(client)
    r = client.get("/custom-study")
    assert r.status_code == 200
    body = r.text
    assert "Increase today's new card limit" in body
    assert "Study by card state or tag" in body
    assert 'name="r"' in body
    assert 'id="spin"' in body


def _drain_for(ws, fn):
    m = ws.receive_json()
    while not (m["type"] == "call" and m["fn"] == fn):
        m = ws.receive_json()
    return m


def test_custom_study_new_limit_navigates_and_broadcasts(client):
    _seed(client)
    with client.websocket_connect("/ws?context=customstudy") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "customstudy",
                      "arg": "submit:" + json.dumps({"radio": 1, "value": 5})})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == ["/overview"]


def test_custom_study_cram_creates_filtered_deck(client):
    _seed(client)
    with client.websocket_connect("/ws?context=customstudy") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "customstudy",
                      "arg": "submit:" + json.dumps(
                          {"radio": 6, "value": 50, "cram_kind": 1,
                           "include": [], "exclude": []})})
        _drain_for(ws, "ankiwebNavigate")
    cur = client.portal.call(
        client.app.state.service.run,
        lambda col: (col.decks.get(col.decks.get_current_id())["name"],
                     bool(col.decks.get(col.decks.get_current_id()).get("dyn"))))
    assert cur[1] is True
    assert cur[0] == "Custom Study Session"


def test_custom_study_error_when_no_cards_match(client):
    _seed(client)
    with client.websocket_connect("/ws?context=customstudy") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "customstudy",
                      "arg": "submit:" + json.dumps({"radio": 3, "value": 1})})
        m = ws.receive_json()
        seen_err = False
        for _ in range(10):
            if m["type"] == "call" and m["fn"] == "ankiwebCustomStudyError":
                seen_err = True
                assert "matched" in m["args"][0].lower() or "card" in m["args"][0].lower()
                break
            if m["type"] == "call" and m["fn"] == "ankiwebNavigate":
                pytest.fail("navigated despite CustomStudyError")
            m = ws.receive_json()
        assert seen_err


def test_overview_studymore_navigates_to_custom_study(client):
    _seed(client)
    with client.websocket_connect("/ws?context=overview") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "overview", "arg": "studymore"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == ["/custom-study"]


def test_overview_opts_navigates_to_deck_options(client):
    did = _seed(client)
    with client.websocket_connect("/ws?context=overview") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "overview", "arg": "opts"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == [f"/deck-options/{did}"]
