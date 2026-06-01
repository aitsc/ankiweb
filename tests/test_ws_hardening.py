from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _result_id(ws):
    m = ws.receive_json()
    while m.get("type") != "result":
        m = ws.receive_json()
    return m["id"]


def test_bad_json_then_valid_cmd_survives(client):
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_text("this is not json{{{")          # malformed → must be skipped, not fatal
        ws.send_json({"type": "cmd", "id": 1, "ctx": "deckbrowser", "arg": "noop:"})
        assert _result_id(ws) == 1


def test_non_object_frame_skipped(client):
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json([1, 2, 3])                        # JSON array, not an object
        ws.send_json({"type": "cmd", "id": 2, "ctx": "deckbrowser", "arg": "noop:"})
        assert _result_id(ws) == 2


def test_result_frame_missing_id_skipped(client):
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "result", "value": "x"})  # no 'id' → must not KeyError/drop
        ws.send_json({"type": "cmd", "id": 3, "ctx": "deckbrowser", "arg": "noop:"})
        assert _result_id(ws) == 3
