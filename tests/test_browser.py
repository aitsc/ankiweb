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
    for q in ("dog", "cat"):
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = q; n["Back"] = q.upper()
        col.add_note(n, col.decks.id("Default"))
    col.tags.bulk_add(col.find_notes(""), "animals")


def _drain_call(ws, fn, tries=6):
    for _ in range(tries):
        m = ws.receive_json()
        if m["type"] == "call" and m["fn"] == fn:
            return m["args"]
    raise AssertionError(f"no {fn} frame")


def test_browse_route_renders(client):
    r = client.get("/browse")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="browser"' in r.text
    assert "id='results'" in r.text or 'id="results"' in r.text
    assert "id='search'" in r.text or 'id="search"' in r.text
    assert "Default" in r.text
    assert "animals" in r.text


def test_browse_search_pushes_rows_and_mirrors_ui_state(client):
    hub = client.app.state.hub
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "search:dog"})
        args = _drain_call(ws, "ankiwebSetRows")
        assert "dog" in args[0] and "cat" not in args[0]
        assert args[1] == 1
    assert hub.ui_state.browser_open is True
    assert hub.ui_state.last_browse_query == "dog"
    assert len(hub.ui_state.matched_card_ids) == 1


def test_browse_searchdeck_and_searchtag(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"searchdeck:{did}"})
        rows = _drain_call(ws, "ankiwebSetRows")[0]
        assert "dog" in rows and "cat" in rows
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "searchtag:animals"})
        rows = _drain_call(ws, "ankiwebSetRows")[0]
        assert "dog" in rows and "cat" in rows


def test_browse_open_pushes_detail_and_selection(client):
    cid = client.portal.call(client.app.state.service.run, lambda col: list(col.find_cards("dog"))[0])
    hub = client.app.state.hub
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"open:{cid}"})
        detail = _drain_call(ws, "ankiwebSetDetail")[0]
        assert "DOG" in detail
        assert "Front" in detail and "Back" in detail
    assert hub.ui_state.selected_card_ids == [cid]
    assert len(hub.ui_state.selected_note_ids) == 1


def test_browse_invalid_search_does_not_crash(client):
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "search:deck:((("})
        args = _drain_call(ws, "ankiwebSetRows")
        assert args[1] == 0
