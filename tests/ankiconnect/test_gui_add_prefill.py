import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.ankiconnect.runtime import Runtime
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.ankiconnect.registry import ACTIONS
import ankiweb.ankiconnect.actions  # noqa: F401


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


async def _run(rt, name, params):
    return await ACTIONS[name](rt, **params)


def _gui(client, action, **params):
    rt = Runtime(service=client.app.state.service, config=AnkiConnectConfig(),
                 hub=client.app.state.hub)
    return client.portal.call(_run, rt, action, params)


def _drain(ws, fn):
    m = ws.receive_json()
    while not (m["type"] == "call" and m["fn"] == fn):
        m = ws.receive_json()
    return m


def test_set_data_errors_when_add_not_open(client):
    res = _gui(client, "guiAddNoteSetData",
               note={"modelName": "Basic", "fields": {"Front": "x"}})
    assert res == {"error": "Add Note dialog is not open", "code": 1}


def test_set_data_prefills_open_add(client):
    with client.websocket_connect("/ws?context=add") as ws:
        res = _gui(client, "guiAddNoteSetData",
                   note={"modelName": "Basic", "fields": {"Front": "PF", "Back": "PB"}})
        assert res is None
        m = _drain(ws, "ankiwebLoadNote")
        fields = dict(m["args"][0]["fields"])
        assert fields["Front"] == "PF" and fields["Back"] == "PB"


def test_gui_add_cards_prefills_open_add(client):
    with client.websocket_connect("/ws?context=add") as ws:
        nid = _gui(client, "guiAddCards",
                   note={"deckName": "Default", "modelName": "Basic",
                         "fields": {"Front": "A", "Back": "B"}, "tags": ["t1"]})
        assert isinstance(nid, int)
        m = _drain(ws, "ankiwebLoadNote")
        d = m["args"][0]
        assert dict(d["fields"])["Front"] == "A"
        assert d["tags"] == ["t1"]
