from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.notifier import NotifyConfig


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c, tmp_path


def test_extras_menu_links_to_notify(client):
    c, _ = client
    html = c.get("/deckbrowser").text
    assert "Extras" in html and "/notify" in html


def test_notify_page_renders(client):
    c, _ = client
    r = c.get("/notify")
    assert r.status_code == 200
    assert "Push notifications" in r.text and "POST URL" in r.text


def test_notify_save_persists_config(client):
    c, tmp_path = client
    r = c.post("/notify", data={"action": "save", "enabled": "on",
                                "url": "http://hook.example/anki", "token": "sek",
                                "poll_sec": "20", "retry_sec": "8"},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/notify"
    # persisted to notify.json next to the collection
    cfg = NotifyConfig.load(tmp_path / "notify.json")
    assert cfg.enabled and cfg.url == "http://hook.example/anki"
    assert cfg.token == "sek" and cfg.poll_sec == 20 and cfg.retry_sec == 8
    # and reflected back in the form on next GET
    assert "http://hook.example/anki" in c.get("/notify").text


def test_notify_unchecked_enabled_is_false(client):
    c, tmp_path = client
    c.post("/notify", data={"action": "save", "url": "http://x", "poll_sec": "5",
                            "retry_sec": "5"})  # no 'enabled' field -> unchecked
    assert NotifyConfig.load(tmp_path / "notify.json").enabled is False


def test_notify_rejects_non_latin1_token(client):  # fix #5
    c, tmp_path = client
    r = c.post("/notify", data={"action": "save", "enabled": "on", "url": "http://x",
                                "token": "secret你", "poll_sec": "5", "retry_sec": "5"},
               follow_redirects=False)
    assert r.status_code == 400
    assert "latin-1" in r.text or "ASCII" in r.text
    assert "http://x" in r.text  # the submitted URL is preserved on the error page
    # nothing was persisted (no notify.json written)
    assert not (tmp_path / "notify.json").exists()


def test_notify_resync_sets_flag(client):
    c, _ = client
    c.post("/notify", data={"action": "resync", "enabled": "on", "url": "http://x",
                            "poll_sec": "5", "retry_sec": "5"})
    # the route should have flipped the runner's resync flag on app.state.notifier
    state = c.app.state.notifier
    assert state.resync_pending is True
    assert state.config.url == "http://x"
