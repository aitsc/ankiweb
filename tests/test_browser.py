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
    col.decks.id("Spanish")


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
        assert "iframe" in detail and "/edit?nid=" in detail
    assert hub.ui_state.selected_card_ids == [cid]
    assert len(hub.ui_state.selected_note_ids) == 1


def test_browse_invalid_search_does_not_crash(client):
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "search:deck:((("})
        args = _drain_call(ws, "ankiwebSetRows")
        assert args[1] == 0


def _run(client, fn):
    return client.portal.call(client.app.state.service.run, fn)


def test_select_then_suspend(client):
    hub = client.app.state.hub
    cids = _run(client, lambda col: list(col.find_cards("")))
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser",
                      "arg": "select:" + ",".join(str(c) for c in cids)})
        _drain_call(ws, "ankiwebSetDetail")
        assert hub.ui_state.selected_card_ids == cids
        assert len(hub.ui_state.selected_note_ids) == 2
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "suspend"})
        _drain_call(ws, "ankiwebSetRows")
    assert all(_run(client, lambda col, c=c: col.get_card(c).queue) == -1 for c in cids)


def test_select_one_pushes_detail(client):
    cid = _run(client, lambda col: list(col.find_cards("dog"))[0])
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        detail = _drain_call(ws, "ankiwebSetDetail")[0]
        assert "iframe" in detail and "/edit?nid=" in detail


def test_delete_removes_notes(client):
    cid = _run(client, lambda col: list(col.find_cards("dog"))[0])
    before = _run(client, lambda col: len(col.find_notes("")))
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        _drain_call(ws, "ankiwebSetDetail")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "delete"})
        _drain_call(ws, "ankiwebSetRows")
    assert _run(client, lambda col: len(col.find_notes(""))) == before - 1


def test_changedeck_moves_card(client):
    cid = _run(client, lambda col: list(col.find_cards("dog"))[0])
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        _drain_call(ws, "ankiwebSetDetail")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "changedeck:Spanish"})
        _drain_call(ws, "ankiwebSetRows")
    did = _run(client, lambda col: col.get_card(cid).did)
    assert did == _run(client, lambda col: col.decks.id("Spanish"))


def test_add_and_remove_tag(client):
    cid = _run(client, lambda col: list(col.find_cards("dog"))[0])
    nid = _run(client, lambda col: col.get_card(cid).nid)
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        _drain_call(ws, "ankiwebSetDetail")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "addtag:marked"})
        _drain_call(ws, "ankiwebSetRows")
    assert "marked" in _run(client, lambda col: col.get_note(nid).tags)
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        _drain_call(ws, "ankiwebSetDetail")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "removetag:marked"})
        _drain_call(ws, "ankiwebSetRows")
    assert "marked" not in _run(client, lambda col: col.get_note(nid).tags)


def test_setdue_runs(client):
    cid = _run(client, lambda col: list(col.find_cards("dog"))[0])
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        _drain_call(ws, "ankiwebSetDetail")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "setdue:0"})
        _drain_call(ws, "ankiwebSetRows")


def test_browse_refresh_repushes_rows(client):
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "search:dog"})
        _drain_call(ws, "ankiwebSetRows")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "refresh"})
        args = _drain_call(ws, "ankiwebSetRows")
        assert "dog" in args[0]
