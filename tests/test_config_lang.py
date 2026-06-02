import os
from pathlib import Path
from ankiweb.config import Settings


def test_lang_defaults_to_empty(tmp_path: Path):
    s = Settings(collection_path=tmp_path / "c.anki2")
    assert s.lang == ""


def test_from_env_reads_ankiweb_lang(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ANKIWEB_COLLECTION", str(tmp_path / "c.anki2"))
    monkeypatch.setenv("ANKIWEB_LANG", "zh-CN")
    s = Settings.from_env()
    assert s.lang == "zh-CN"


def test_from_env_lang_absent_is_empty(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ANKIWEB_COLLECTION", str(tmp_path / "c.anki2"))
    monkeypatch.delenv("ANKIWEB_LANG", raising=False)
    s = Settings.from_env()
    assert s.lang == ""
