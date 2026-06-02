import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_graphs_shell_injects_browsersearch_bridge(client):
    r = client.get("/graphs")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    # SPA still boots
    assert "_app/immutable/entry" in r.text
    # bridge present + maps browserSearch -> /browse?q=
    assert "browserSearch:" in r.text
    assert "/browse?q=" in r.text


def test_browse_q_prefills_and_searches(client):
    r = client.get("/browse?q=deck:Default")
    assert r.status_code == 200
    # input prefilled
    assert 'value="deck:Default"' in r.text
    # on-load search uses the query (JSON-encoded into the inline script)
    assert "search:" in r.text and '"deck:Default"' in r.text


def test_browse_q_empty_default(client):
    r = client.get("/browse")
    assert r.status_code == 200
    assert 'value=""' in r.text


def test_browse_q_html_escaped(client):
    # a query with quotes/brackets must not break the attribute or the inline JS
    r = client.get('/browse?q=front:"a<b>"')
    assert r.status_code == 200
    assert "&lt;b&gt;" in r.text  # escaped in the value attribute
