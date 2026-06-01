import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.ankiconnect.app import create_ankiconnect_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_ankiconnect_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _call(client, action, **params):
    r = client.post("/", json={"action": action, "version": 6, "params": params})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None, body["error"]
    return body["result"]


def test_export_package_unknown_deck_returns_false(client, tmp_path):
    out = str(tmp_path / "x.apkg")
    assert _call(client, "exportPackage", deck="NoSuchDeck", path=out) is False
    assert not os.path.exists(out)


def test_export_package_writes_file(client, tmp_path):
    for i in range(2):
        _call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
              "fields": {"Front": f"f{i}", "Back": f"b{i}"}})
    out = str(tmp_path / "deck.apkg")
    assert _call(client, "exportPackage", deck="Default", path=out, includeSched=False) is True
    assert os.path.exists(out) and os.path.getsize(out) > 0


def test_export_then_reimport_restores_notes(client, tmp_path):
    nids = [_call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
                  "fields": {"Front": f"f{i}", "Back": f"b{i}"}}) for i in range(2)]
    out = str(tmp_path / "deck.apkg")
    assert _call(client, "exportPackage", deck="Default", path=out) is True
    # delete the notes, then re-import the package to restore them
    _call(client, "deleteNotes", notes=nids)
    assert _call(client, "findNotes", query="front:f0") == []
    assert _call(client, "importPackage", path=out) is True
    assert len(_call(client, "findNotes", query="front:f0")) == 1
