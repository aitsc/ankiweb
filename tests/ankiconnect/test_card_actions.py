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


def _add(client, front="Q"):
    return _call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
                                          "fields": {"Front": front, "Back": "A"}})


def test_find_cards(client):
    _add(client)
    cards = _call(client, "findCards", query="deck:Default")
    assert len(cards) == 1 and isinstance(cards[0], int)


def test_cards_info_shape(client):
    _add(client, "cinfo")
    cid = _call(client, "findCards", query="deck:Default")[0]
    info = _call(client, "cardsInfo", cards=[cid])[0]
    assert info["cardId"] == cid
    assert info["deckName"] == "Default"
    assert info["modelName"] == "Basic"
    assert "question" in info and "answer" in info and "fields" in info
    assert info["queue"] == 0 and info["type"] == 0   # new card
    assert isinstance(info["nextReviews"], list)


def test_cards_mod_time(client):
    _add(client)
    cid = _call(client, "findCards", query="deck:Default")[0]
    res = _call(client, "cardsModTime", cards=[cid])
    assert res[0]["cardId"] == cid and isinstance(res[0]["mod"], int)
