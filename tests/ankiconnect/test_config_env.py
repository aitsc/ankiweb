import json
from pathlib import Path
import pytest
from ankiweb.ankiconnect.config import AnkiConnectConfig


def test_defaults_when_no_file_no_env(tmp_path, monkeypatch):
    for v in ("ANKIWEB_AC_HOST", "ANKIWEB_AC_PORT", "ANKIWEB_AC_KEY"):
        monkeypatch.delenv(v, raising=False)
    c = AnkiConnectConfig.load(tmp_path / "ankiconnect.json")
    assert c.bind_address == "127.0.0.1" and c.bind_port == 8765


def test_json_file_values(tmp_path, monkeypatch):
    for v in ("ANKIWEB_AC_HOST", "ANKIWEB_AC_PORT"):
        monkeypatch.delenv(v, raising=False)
    p = tmp_path / "ankiconnect.json"
    p.write_text(json.dumps({"webBindAddress": "0.0.0.0", "webBindPort": 9001}))
    c = AnkiConnectConfig.load(p)
    assert c.bind_address == "0.0.0.0" and c.bind_port == 9001


def test_env_overrides_json(tmp_path, monkeypatch):
    p = tmp_path / "ankiconnect.json"
    p.write_text(json.dumps({"webBindAddress": "0.0.0.0", "webBindPort": 9001, "apiKey": "j"}))
    monkeypatch.setenv("ANKIWEB_AC_HOST", "127.0.0.1")
    monkeypatch.setenv("ANKIWEB_AC_PORT", "7000")
    monkeypatch.setenv("ANKIWEB_AC_KEY", "envkey")
    c = AnkiConnectConfig.load(p)
    assert c.bind_address == "127.0.0.1" and c.bind_port == 7000 and c.api_key == "envkey"


def test_collection_parent_dir_created(tmp_path):
    # CollectionService.open() must create a missing parent dir for a custom path
    import anyio
    from ankiweb.config import Settings
    from ankiweb.collection_service import CollectionService
    nested = tmp_path / "deep" / "sub" / "c.anki2"
    assert not nested.parent.exists()
    svc = CollectionService(Settings(collection_path=nested))

    async def _run():
        await svc.open()
        await svc.close()
    anyio.run(_run)
    assert nested.exists() and nested.parent.is_dir()
