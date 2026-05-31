import functools
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.bridge.ui_state import UiState
from ankiweb.bridge.hub import BridgeHub


def test_ui_state_defaults_and_review_active():
    s = UiState()
    assert s.current_screen is None and s.current_card_id is None and s.side is None
    assert s.browser_open is False
    assert s.matched_card_ids == [] and s.selected_note_ids == []
    assert s.review_active is False
    s.current_screen = "reviewer"
    assert s.review_active is False           # needs a card too
    s.current_card_id = 123
    assert s.review_active is True
    s.current_screen = "deckbrowser"
    assert s.review_active is False           # not on reviewer


def test_hub_has_ui_state():
    assert isinstance(BridgeHub().ui_state, UiState)


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        c.portal.call(c.app.state.service.run, _seed)
        yield c


def _seed(col):
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"; n["Back"] = "a"
    col.add_note(n, col.decks.id("Default"))


def test_dispatch_cmd_sets_current_screen(client):
    hub = client.app.state.hub
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(hub.dispatch_cmd, "deckbrowser", f"open:{did}")
    assert hub.ui_state.current_screen == "deckbrowser"


def test_reviewer_show_updates_ui_state(client):
    hub = client.app.state.hub
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    client.portal.call(hub.dispatch_cmd, "reviewer", "show")
    assert hub.ui_state.current_screen == "reviewer"
    assert hub.ui_state.current_card_id is not None
    assert hub.ui_state.side == "question"
    client.portal.call(hub.dispatch_cmd, "reviewer", "ans")
    assert hub.ui_state.side == "answer"


def test_reviewer_finish_clears_ui_state(client):
    hub = client.app.state.hub
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    client.portal.call(hub.dispatch_cmd, "reviewer", "show")
    client.portal.call(hub.dispatch_cmd, "reviewer", "ans")
    client.portal.call(hub.dispatch_cmd, "reviewer", "ease4")  # graduates the only card -> finished
    assert hub.ui_state.current_card_id is None
    assert hub.ui_state.side is None


def test_ws_connect_sets_current_screen(client):
    hub = client.app.state.hub
    with client.websocket_connect("/ws?context=overview"):
        assert hub.ui_state.current_screen == "overview"
