from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings, host_allowed
from ankiweb.app import create_app


def test_host_allowed_unit():
    # localhost always allowed
    assert host_allowed("127.0.0.1:8000", ())
    assert host_allowed("localhost:8000", ())
    assert host_allowed("testserver", ())
    # a LAN host is rejected by default
    assert not host_allowed("192.168.1.50:8000", ())
    # explicit allow, with or without port
    assert host_allowed("192.168.1.50:8000", ("192.168.1.50:8000",))
    assert host_allowed("192.168.1.50:8000", ("192.168.1.50",))   # bare host matches :port
    assert not host_allowed("192.168.1.99:8000", ("192.168.1.50",))
    # wildcard disables the check
    assert host_allowed("anything.example.com", ("*",))


def _client(tmp_path, allowed):
    s = Settings(collection_path=tmp_path / "c.anki2", allowed_hosts=allowed)
    return TestClient(create_app(s))


def test_lan_host_forbidden_by_default(tmp_path: Path):
    with _client(tmp_path, ()) as c:
        r = c.get("/healthz", headers={"host": "192.168.1.50:8000"})
        assert r.status_code == 403
        assert "forbidden host" in r.text


def test_lan_host_allowed_when_configured(tmp_path: Path):
    with _client(tmp_path, ("192.168.1.50:8000",)) as c:
        r = c.get("/healthz", headers={"host": "192.168.1.50:8000"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}


def test_ws_lan_host_allowed_when_configured(tmp_path: Path):
    with _client(tmp_path, ("192.168.1.50:8000",)) as c:
        # WS upgrade carries the same Host header; configured → accepted
        with c.websocket_connect("/ws?context=deckbrowser",
                                 headers={"host": "192.168.1.50:8000"}) as ws:
            ws.send_json({"type": "cmd", "id": 1, "ctx": "deckbrowser", "arg": "noop:"})
            m = ws.receive_json()
            while m.get("type") != "result":
                m = ws.receive_json()
            assert m["id"] == 1


def test_ws_lan_host_rejected_by_default(tmp_path: Path):
    import websockets  # noqa
    from starlette.websockets import WebSocketDisconnect as WSD
    with _client(tmp_path, ()) as c:
        with pytest.raises(Exception):
            with c.websocket_connect("/ws?context=deckbrowser",
                                     headers={"host": "192.168.1.50:8000"}) as ws:
                ws.receive_json()
