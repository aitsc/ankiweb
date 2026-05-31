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


def test_gui_browse_returns_findcards_and_records(client):
    cids = _gui(client, "guiBrowse", query="deck:Default")
    assert isinstance(cids, list) and len(cids) >= 1
    assert client.app.state.hub.ui_state.last_browse_query == "deck:Default"
    assert client.app.state.hub.ui_state.matched_card_ids == cids
    assert client.app.state.hub.ui_state.browser_open is True


def test_gui_browse_no_query_returns_empty(client):
    # findCards(None) returns [] in AnkiConnect; guiBrowse with no query must too,
    # while still "opening" the Browser (so guiSelectCard works afterward).
    assert _gui(client, "guiBrowse") == []
    assert client.app.state.hub.ui_state.browser_open is True


def test_gui_browse_reorder_validation(client):
    with pytest.raises(Exception):
        _gui(client, "guiBrowse", query="", reorderCards={"order": "sideways"})
    assert isinstance(_gui(client, "guiBrowse", query="",
                            reorderCards={"columnId": "noteFld", "order": "descending"}), list)


def test_gui_select_and_selected_notes(client):
    assert _gui(client, "guiSelectedNotes") == []
    cids = _gui(client, "guiBrowse", query="deck:Default")  # "opens" the browser domain
    assert _gui(client, "guiSelectCard", card=cids[0]) is True
    nids = _gui(client, "guiSelectedNotes")
    assert len(nids) == 1 and isinstance(nids[0], int)
    assert _gui(client, "guiSelectNote", note=cids[0]) is True


def test_gui_select_card_false_without_browse(client):
    assert _gui(client, "guiSelectCard", card=12345) is False


def test_gui_play_audio(client):
    assert _gui(client, "guiPlayAudio") is False     # not reviewing
    _select_default(client)
    _drive(client, "show")
    assert _gui(client, "guiPlayAudio") is True       # reviewing -> faithful True


def test_gui_add_note_set_data_stub(client):
    res = _gui(client, "guiAddNoteSetData",
               note={"deckName": "Default", "modelName": "Basic", "fields": {"Front": "x"}})
    assert res == {"error": "Add Note dialog is not open", "code": 1}


def test_gui_edit_note_noop(client):
    assert _gui(client, "guiEditNote", note=123) is None


def test_gui_add_cards_returns_int_and_validates(client):
    res = _gui(client, "guiAddCards",
               note={"deckName": "Default", "modelName": "Basic", "fields": {"Front": "x"}})
    assert isinstance(res, int)
    assert isinstance(_gui(client, "guiAddCards"), int)   # blank dialog form
    with pytest.raises(Exception):
        _gui(client, "guiAddCards",
             note={"deckName": "No Such Deck", "modelName": "Basic", "fields": {"Front": "x"}})
    with pytest.raises(Exception):
        _gui(client, "guiAddCards",
             note={"deckName": "Default", "modelName": "No Such Model", "fields": {}})


def test_gui_import_file_refuses(client):
    with pytest.raises(Exception):
        _gui(client, "guiImportFile", path="/tmp/x.apkg")


def test_gui_exit_anki_noop(client):
    assert _gui(client, "guiExitAnki") is None
