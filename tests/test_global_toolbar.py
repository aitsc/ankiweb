from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.screens.page import render_page


def test_render_page_includes_toolbar_by_default():
    html = render_page("deckbrowser", "<div>x</div>")
    assert "id='ankiweb-toolbar'" in html
    for label, href in [("Decks", "/deckbrowser"), ("Add", "/add"),
                        ("Browse", "/browse"), ("Stats", "/graphs")]:
        assert f"href='{href}'>{label}<" in html


def test_render_page_toolbar_can_be_disabled():
    html = render_page("editor", "<div>x</div>", toolbar=False)
    assert "ankiweb-toolbar" not in html


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _seed(client):
    def seed(col):
        did = col.decks.id("Default")
        col.decks.set_current(did)
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"; n["Back"] = "a"
        col.add_note(n, did)
        return col.find_cards("")[0]
    return client.portal.call(client.app.state.service.run, seed)


@pytest.mark.parametrize("path", ["/deckbrowser", "/overview", "/browse", "/add",
                                  "/custom-study", "/reviewer", "/export"])
def test_server_screens_have_toolbar(client, path):
    _seed(client)
    r = client.get(path)
    assert r.status_code == 200
    assert "id='ankiweb-toolbar'" in r.text


def test_edit_iframe_has_no_toolbar(client):
    nid = client.portal.call(client.app.state.service.run,
                             lambda col: col.find_notes("")[0] if col.find_notes("") else None) or _edit_seed(client)
    r = client.get(f"/edit?nid={nid}")
    assert r.status_code == 200
    assert "ankiweb-toolbar" not in r.text   # embedded editor: no global toolbar


def _edit_seed(client):
    def seed(col):
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"; n["Back"] = "a"
        col.add_note(n, col.decks.id("Default"))
        return n.id
    return client.portal.call(client.app.state.service.run, seed)
