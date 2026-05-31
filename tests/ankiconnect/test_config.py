import json
from pathlib import Path
from ankiweb.ankiconnect.config import AnkiConnectConfig


def test_defaults_when_no_file(tmp_path: Path):
    cfg = AnkiConnectConfig.load(tmp_path / "missing.json")
    assert cfg.api_key is None
    assert cfg.cors_origin_list == ["http://localhost"]
    assert cfg.bind_port == 8765
    assert cfg.ignore_origin_list == []


def test_loads_overrides(tmp_path: Path):
    p = tmp_path / "ac.json"
    p.write_text(json.dumps({"apiKey": "secret", "webCorsOriginList": ["*"], "webBindPort": 9000}))
    cfg = AnkiConnectConfig.load(p)
    assert cfg.api_key == "secret"
    assert cfg.cors_origin_list == ["*"]
    assert cfg.bind_port == 9000
