from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_deckbrowser_has_add_and_browse_entry_points(client):
    r = client.get("/deckbrowser")
    assert r.status_code == 200
    assert "href='/add'" in r.text or 'href="/add"' in r.text
    assert "href='/browse'" in r.text or 'href="/browse"' in r.text


def test_add_and_browse_pages_open(client):
    # the pages the nav links to actually render (functionality exists from Sub-project D)
    assert client.get("/add").status_code == 200
    assert client.get("/browse").status_code == 200
