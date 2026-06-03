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


def test_suspend_unsuspend(client):
    _add(client, "susp")
    cid = _call(client, "findCards", query="deck:Default")[0]
    assert _call(client, "suspend", cards=[cid]) is True
    assert _call(client, "suspended", card=cid) is True
    assert _call(client, "areSuspended", cards=[cid]) == [True]
    _call(client, "unsuspend", cards=[cid])
    assert _call(client, "suspended", card=cid) is False


def test_ease_factors(client):
    _add(client, "ease")
    cid = _call(client, "findCards", query="deck:Default")[0]
    assert _call(client, "setEaseFactors", cards=[cid], easeFactors=[2500]) == [True]
    assert _call(client, "getEaseFactors", cards=[cid]) == [2500]


def test_set_due_date_and_forget(client):
    _add(client, "due")
    cid = _call(client, "findCards", query="deck:Default")[0]
    assert _call(client, "setDueDate", cards=[cid], days="3") is True
    assert _call(client, "forgetCards", cards=[cid]) is None


def test_answer_cards(client):
    _add(client, "ans")
    cid = _call(client, "findCards", query="deck:Default")[0]
    res = _call(client, "answerCards", answers=[{"cardId": cid, "ease": 3}])
    assert res == [True]


# Invalid-id leniency: match canonical AnkiConnect (return False/None, never an error envelope).
def test_set_ease_factors_invalid_id(client):
    _add(client, "easebad")
    cid = _call(client, "findCards", query="deck:Default")[0]
    # valid card -> True, missing card -> False (AnkiConnect appends False for NotFoundError)
    assert _call(client, "setEaseFactors",
                 cards=[cid, 99999], easeFactors=[2500, 2500]) == [True, False]


def test_set_specific_value_of_card_invalid_id(client):
    # missing card -> the whole call returns False (AnkiConnect returns False on NotFoundError)
    assert _call(client, "setSpecificValueOfCard", card=99999,
                 keys=["flags"], newValues=[1], warning_check=True) is False


def test_answer_cards_invalid_id(client):
    _add(client, "ansbad")
    cid = _call(client, "findCards", query="deck:Default")[0]
    res = _call(client, "answerCards",
                answers=[{"cardId": cid, "ease": 3}, {"cardId": 99999, "ease": 3}])
    assert res == [True, False]
