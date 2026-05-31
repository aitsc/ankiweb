import functools
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.ankiconnect.runtime import Runtime
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.ankiconnect.registry import ACTIONS
import ankiweb.ankiconnect.actions  # noqa: F401 — registers all actions


@pytest.fixture
def client(tmp_path: Path):
    # The WEB app constructs hub + service + registers screen handlers in its lifespan,
    # so gui* reviewer-control actions (which reuse hub.dispatch_cmd) work end-to-end.
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        c.portal.call(c.app.state.service.run, _seed)
        yield c


def _seed(col):
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"; n["Back"] = "a"
    col.add_note(n, col.decks.id("Default"))


def _rt(client):
    return Runtime(service=client.app.state.service, config=AnkiConnectConfig(),
                   hub=client.app.state.hub)


async def _run(rt, name, params):
    return await ACTIONS[name](rt, **params)


def _gui(client, action, **params):
    return client.portal.call(_run, _rt(client), action, params)


def _drive(client, arg):
    client.portal.call(client.app.state.hub.dispatch_cmd, "reviewer", arg)


def _select_default(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))


def test_review_active_false_when_idle(client):
    assert _gui(client, "guiReviewActive") is False


def test_gui_current_card_raises_when_idle(client):
    with pytest.raises(Exception):
        _gui(client, "guiCurrentCard")


def test_reviewer_flow(client):
    _select_default(client)
    _drive(client, "show")                       # loads the seeded card
    assert _gui(client, "guiReviewActive") is True
    cur = _gui(client, "guiCurrentCard")
    assert cur["cardId"] and cur["question"] and "Back" in cur["fields"]
    assert cur["buttons"] == [1, 2, 3, 4]
    assert len(cur["nextReviews"]) == 4
    assert cur["modelName"] == "Basic" and cur["deckName"] == "Default"
    assert cur["template"]  # active template name
    assert _gui(client, "guiStartCardTimer") is True
    assert _gui(client, "guiShowQuestion") is True
    assert _gui(client, "guiShowAnswer") is True
    assert _gui(client, "guiAnswerCard", ease=3) is True


def test_gui_answer_card_requires_answer_side(client):
    _select_default(client)
    _drive(client, "show")                       # side == 'question'
    assert _gui(client, "guiAnswerCard", ease=3) is False  # answer not shown yet
    assert _gui(client, "guiAnswerCard", ease=9) is False  # out of range


def test_gui_undo(client):
    def add(col):
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "u"
        return col.add_note(n, col.decks.id("Default"))
    client.portal.call(client.app.state.service.run_op, add, "test")
    assert _gui(client, "guiUndo") is True
    # undoing again with nothing to undo still returns True (no-op)
    assert _gui(client, "guiUndo") is True


def test_gui_check_database(client):
    assert _gui(client, "guiCheckDatabase") is True


def test_gui_deck_overview_and_review(client):
    assert _gui(client, "guiDeckOverview", name="Default") is True
    assert _gui(client, "guiDeckOverview", name="No Such Deck") is False
    assert _gui(client, "guiDeckReview", name="Default") is True
    assert _gui(client, "guiDeckReview", name="No Such Deck") is False


def test_gui_deck_browser_pushes_navigate(client):
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        # ws connect set current_screen='deckbrowser'; guiDeckBrowser pushes navigate to it
        assert _gui(client, "guiDeckBrowser") is None
        m = ws.receive_json()
        while m["type"] != "call":
            m = ws.receive_json()
        assert m["fn"] == "ankiwebNavigate" and m["args"] == ["/deckbrowser"]
