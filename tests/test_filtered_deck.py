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


def _seed(client, n=4):
    def seed(col):
        did = col.decks.id("Default")
        col.decks.set_current(did)
        for i in range(n):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = f"f{i}"; note["Back"] = f"b{i}"
            col.add_note(note, did)
        return did
    return client.portal.call(client.app.state.service.run, seed)


def _make_filtered(client, search="deck:Default", limit=10):
    def mk(col):
        import anki.decks_pb2 as dp
        g = col.sched.get_or_create_filtered_deck(0)
        g.name = "Filt"
        del g.config.search_terms[:]
        g.config.search_terms.append(
            dp.Deck.Filtered.SearchTerm(search=search, limit=limit, order=5))
        return col.sched.add_or_update_filtered_deck(g).id
    return client.portal.call(client.app.state.service.run, mk)


def _drain_for(ws, fn):
    m = ws.receive_json()
    while not (m["type"] == "call" and m["fn"] == fn):
        m = ws.receive_json()
    return m


def test_filtered_deck_new_route_renders(client):
    _seed(client)
    r = client.get("/filtered-deck")
    assert r.status_code == 200
    body = r.text
    assert 'id="name"' in body
    assert 'id="search1"' in body
    assert "Random" in body and "Order due" in body   # order labels
    assert ">Build<" in body                            # new-deck OK label


def test_filtered_deck_edit_route_renders(client):
    _seed(client)
    did = _make_filtered(client)
    r = client.get(f"/filtered-deck/{did}")
    assert r.status_code == 200
    assert "Filt" in r.text
    assert ">Rebuild<" in r.text                          # edit OK label


def test_filtered_deck_create_saves_and_navigates(client):
    _seed(client)
    payload = {"id": 0, "name": "NewFiltered", "reschedule": True,
               "search1": "deck:Default", "limit1": 10, "order1": 1,
               "second": False, "search2": "", "limit2": 20, "order2": 5,
               "preview_again": 60, "preview_hard": 600, "preview_good": 0,
               "allow_empty": False}
    with client.websocket_connect("/ws?context=filtereddeck") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "filtereddeck",
                      "arg": "submit:" + json.dumps(payload)})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == ["/overview"]
    info = client.portal.call(
        client.app.state.service.run,
        lambda col: (col.decks.by_name("NewFiltered") is not None,
                     bool(col.decks.by_name("NewFiltered")["dyn"])))
    assert info == (True, True)


def test_filtered_deck_edit_renames(client):
    _seed(client)
    did = _make_filtered(client)
    payload = {"id": did, "name": "Renamed", "reschedule": True,
               "search1": "deck:Default", "limit1": 10, "order1": 5,
               "second": False, "search2": "", "limit2": 20, "order2": 5,
               "preview_again": 60, "preview_hard": 600, "preview_good": 0,
               "allow_empty": True}
    with client.websocket_connect("/ws?context=filtereddeck") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "filtereddeck",
                      "arg": "submit:" + json.dumps(payload)})
        _drain_for(ws, "ankiwebNavigate")
    name = client.portal.call(client.app.state.service.run,
                              lambda col: col.decks.get(did)["name"])
    assert name == "Renamed"


def test_filtered_deck_error_when_no_match(client):
    _seed(client)
    payload = {"id": 0, "name": "Empty", "reschedule": True,
               "search1": "tag:__nonexistent__", "limit1": 10, "order1": 1,
               "second": False, "search2": "", "limit2": 20, "order2": 5,
               "preview_again": 60, "preview_hard": 600, "preview_good": 0,
               "allow_empty": False}
    with client.websocket_connect("/ws?context=filtereddeck") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "filtereddeck",
                      "arg": "submit:" + json.dumps(payload)})
        m = ws.receive_json()
        seen = False
        for _ in range(10):
            if m["type"] == "call" and m["fn"] == "ankiwebFilteredDeckError":
                seen = True
                break
            if m["type"] == "call" and m["fn"] == "ankiwebNavigate":
                pytest.fail("navigated despite FilteredDeckError")
            m = ws.receive_json()
        assert seen


def test_deckbrowser_gear_dyn_opens_filtered(client):
    _seed(client)
    did = _make_filtered(client)
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "deckbrowser", "arg": f"opts:{did}"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == [f"/filtered-deck/{did}"]


def test_deckbrowser_gear_normal_opens_deck_options(client):
    did = _seed(client)
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "deckbrowser", "arg": f"opts:{did}"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == [f"/deck-options/{did}"]


def test_deckbrowser_create_filtered_entry(client):
    _seed(client)
    r = client.get("/deckbrowser")
    assert "createfiltered" in r.text
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "deckbrowser", "arg": "createfiltered"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == ["/filtered-deck"]


def test_overview_opts_dyn_opens_filtered(client):
    _seed(client)
    did = _make_filtered(client)   # add_or_update selects it as current
    with client.websocket_connect("/ws?context=overview") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "overview", "arg": "opts"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == [f"/filtered-deck/{did}"]
