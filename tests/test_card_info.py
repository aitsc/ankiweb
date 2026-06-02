import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _add_card(client):
    def fn(col):
        n = col.new_note(col.models.by_name("Basic"))
        n["Front"] = "q"; n["Back"] = "a"
        col.add_note(n, col.decks.id("Default"))
        return n.cards()[0].id
    return client.portal.call(client.app.state.service.run, fn)


def test_card_info_serves_spa_shell_one_id(client):
    cid = _add_card(client)
    r = client.get(f"/card-info/{cid}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "_app/immutable/entry" in r.text


def test_card_info_serves_spa_shell_two_ids(client):
    cid = _add_card(client)
    r = client.get(f"/card-info/{cid}/{cid}")
    assert r.status_code == 200
    assert "_app/immutable/entry" in r.text


def test_card_stats_rpc_passthrough(client):
    # the card-info SPA fetches these; they must be reachable
    from ankiweb.anki_rpc.passthrough import PASSTHROUGH
    assert "card_stats" in PASSTHROUGH
    assert "get_review_logs" in PASSTHROUGH


def test_browser_has_card_info_entry(client):
    # the browser action toolbar offers Card Info, opening /card-info/<selected cid> in a new tab
    html = client.get("/browse").text
    assert "Card Info" in html
    assert "window.ankiwebCardInfo" in html
    assert "/card-info/" in html
