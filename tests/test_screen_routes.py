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


def test_reviewer_route_serves_real_page(client):
    r = client.get("/reviewer")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="reviewer"' in r.text
    assert "/_anki/js/reviewer.js" in r.text          # real reviewer bundle loaded
    assert "/_anki/css/reviewer.css" in r.text
    assert "id='qa'" in r.text or 'id="qa"' in r.text


def test_reviewer_show_pushes_question(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        msgs = {}
        for _ in range(2):  # expect _showQuestion + ankiwebSetAnswerBar (order not guaranteed)
            m = ws.receive_json()
            if m["type"] == "call":
                msgs[m["fn"]] = m["args"]
        assert "_showQuestion" in msgs
        assert "ankiwebSetAnswerBar" in msgs
        assert "Show Answer" in msgs["ankiwebSetAnswerBar"][0]


def test_reviewer_ease_answers_and_shows_next(client):
    # The client fixture already seeds exactly ONE Basic card (do NOT seed again).
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        ws.receive_json(); ws.receive_json()   # drain the two pushes from show
        # answer Easy (ease4): a new card graduates to review → today's queue empties
        # → reviewer navigates to /overview. (Good/ease3 would leave it in learning.)
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "ease4"})
        nav = None
        for _ in range(5):  # tolerate an intervening opchanges broadcast frame
            m = ws.receive_json()
            if m["type"] == "call" and m["fn"] == "ankiwebNavigate":
                nav = m["args"]; break
        assert nav == ["/overview"]


def test_reviewer_ans_before_show_does_not_crash_socket(client):
    # Sending 'ans' with no in-flight card must NOT drop the socket; a subsequent
    # 'show' must still work (proves the handler guarded session.card is None).
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "ans"})
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        # the socket survived 'ans' → 'show' produces the question pushes
        got_question = False
        for _ in range(3):
            m = ws.receive_json()
            if m["type"] == "call" and m["fn"] == "_showQuestion":
                got_question = True; break
        assert got_question
