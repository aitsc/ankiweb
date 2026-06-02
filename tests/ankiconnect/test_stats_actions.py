import time
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


def _seed_card(client):
    nid = _call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
                "fields": {"Front": "q", "Back": "a"}})
    return _call(client, "findCards", query=f"nid:{nid}")[0]


def _revlog_row(cid):
    # id, cid, usn, ease, ivl, lastIvl, factor, time, type
    return [int(time.time() * 1000), cid, -1, 3, 10, 5, 2500, 18000, 1]


def test_insert_reviews_and_latest_and_today(client):
    cid = _seed_card(client)
    assert _call(client, "getLatestReviewID", deck="Default") == 0   # no reviews yet
    row = _revlog_row(cid)
    _call(client, "insertReviews", reviews=[row])
    assert _call(client, "getLatestReviewID", deck="Default") == row[0]
    assert _call(client, "getNumCardsReviewedToday") >= 1


def test_card_reviews(client):
    cid = _seed_card(client)
    row = _revlog_row(cid)
    _call(client, "insertReviews", reviews=[row])
    rows = _call(client, "cardReviews", deck="Default", startID=0)
    assert any(r[0] == row[0] and r[1] == cid for r in rows)   # id, cid, … (9 cols)
    assert len(rows[0]) == 9


def test_get_reviews_of_cards(client):
    cid = _seed_card(client)
    row = _revlog_row(cid)
    _call(client, "insertReviews", reviews=[row])
    res = _call(client, "getReviewsOfCards", cards=[cid])
    revs = res[str(cid)]                                       # JSON int key → str
    assert revs and revs[0]["id"] == row[0] and revs[0]["ease"] == 3
    assert set(revs[0].keys()) == {"id", "usn", "ease", "ivl", "lastIvl", "factor", "time", "type"}


def test_reviewed_by_day(client):
    cid = _seed_card(client)
    _call(client, "insertReviews", reviews=[_revlog_row(cid)])
    by_day = _call(client, "getNumCardsReviewedByDay")
    assert isinstance(by_day, list) and by_day and len(by_day[0]) == 2   # [day_str, count]
    assert isinstance(by_day[0][0], str) and by_day[0][1] >= 1


def test_collection_stats_html(client):
    html = _call(client, "getCollectionStatsHTML")
    assert isinstance(html, str) and len(html) > 0


def test_deck_stats(client):
    _seed_card(client)
    res = _call(client, "getDeckStats", decks=["Default"])
    # outer keys are deck ids (str over JSON); find the Default one
    entry = next(v for v in res.values() if v["name"] == "Default")
    assert {"deck_id", "name", "new_count", "learn_count", "review_count"} <= set(entry)
