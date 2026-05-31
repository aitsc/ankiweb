import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    with TestClient(create_app(settings)) as c:
        yield c


def test_cmd_with_callback_roundtrip(client):
    # register a handler for ctx "t" that echoes the arg uppercased
    async def handler(arg: str):
        return arg.upper()
    client.app.state.hub.set_handler("t", handler)

    with client.websocket_connect("/ws?context=t") as ws:
        ws.send_json({"type": "cmd", "id": 7, "ctx": "t", "arg": "hello"})
        reply = ws.receive_json()
        assert reply == {"type": "result", "id": 7, "value": "HELLO"}


def test_opchanges_broadcast_reaches_socket(client):
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        # Drive the broadcast on the app's own loop via the TestClient portal.
        client.portal.call(
            client.app.state.hub.broadcast_opchanges, {"study_queues": True}, "init1")
        msg = ws.receive_json()
        assert msg["type"] == "opchanges"
        assert msg["flags"] == {"study_queues": True}
        assert msg["initiator"] == "init1"
