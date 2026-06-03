import pytest
from pathlib import Path
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


def test_deck_names_has_default(client):
    assert "Default" in _call(client, "deckNames")


def test_create_and_list_deck(client):
    did = _call(client, "createDeck", deck="French")
    assert isinstance(did, int)
    assert "French" in _call(client, "deckNames")
    assert _call(client, "deckNamesAndIds")["French"] == did


def test_deck_name_from_id(client):
    did = _call(client, "createDeck", deck="Spanish")
    assert _call(client, "deckNameFromId", deckId=did) == "Spanish"


def test_delete_decks(client):
    _call(client, "createDeck", deck="Temp")
    assert _call(client, "deleteDecks", decks=["Temp"], cardsToo=True) is None
    assert "Temp" not in _call(client, "deckNames")


def test_delete_decks_requires_cards_too(client):
    _call(client, "createDeck", deck="Temp2")
    r = client.post("/", json={"action": "deleteDecks", "version": 6,
                               "params": {"decks": ["Temp2"]}})
    assert r.json()["error"] is not None  # cardsToo must be true


def test_get_deck_config(client):
    cfg = _call(client, "getDeckConfig", deck="Default")
    assert isinstance(cfg, dict) and "id" in cfg


def test_clone_and_remove_deck_config(client):
    new_id = _call(client, "cloneDeckConfigId", name="MyPreset")
    assert isinstance(new_id, int)
    assert _call(client, "removeDeckConfigId", configId=new_id) is True


def test_get_deck_stats(client):
    stats = _call(client, "getDeckStats", decks=["Default"])
    entry = list(stats.values())[0]
    assert entry["name"] == "Default"
    assert "new_count" in entry and "total_in_deck" in entry


def test_remove_unknown_or_default_config_returns_false(client):
    assert _call(client, "removeDeckConfigId", configId=999999) is False
    assert _call(client, "removeDeckConfigId", configId=1) is False


def test_get_deck_config_missing_deck_does_not_create(client):
    assert _call(client, "getDeckConfig", deck="NoSuchDeck") is False


def test_get_decks_groups_by_deck(client):
    _call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
                                    "fields": {"Front": "gd", "Back": "A"}})
    cid = _call(client, "findCards", query="deck:Default")[0]
    assert _call(client, "getDecks", cards=[cid]) == {"Default": [cid]}


def test_get_decks_invalid_id(client):
    _call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
                                    "fields": {"Front": "gdbad", "Back": "A"}})
    cid = _call(client, "findCards", query="deck:Default")[0]
    # missing card id buckets under "Default" (faithful to AnkiConnect), never an error envelope
    assert _call(client, "getDecks", cards=[cid, 99999]) == {"Default": [cid, 99999]}
    assert "NoSuchDeck" not in _call(client, "deckNames")  # a read query must not create it
