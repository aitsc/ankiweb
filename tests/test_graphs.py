from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app

_APP = Path("ankiweb/web_assets/sveltekit/_app")


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_graphs_serves_spa_shell(client):
    r = client.get("/graphs")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "_app/immutable/entry" in r.text


def test_app_asset_served_as_js_module_with_cache(client):
    entry = next(_APP.glob("immutable/entry/start.*.mjs"))
    rel = entry.relative_to(_APP).as_posix()
    r = client.get(f"/_app/{rel}")
    assert r.status_code == 200
    assert r.headers["content-type"] in ("application/javascript", "text/javascript")
    assert "max-age=31536000" in r.headers.get("cache-control", "")


def test_app_asset_css_served(client):
    css = next(_APP.glob("immutable/assets/*.css"))
    rel = css.relative_to(_APP).as_posix()
    r = client.get(f"/_app/{rel}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/css")


def test_app_asset_traversal_blocked(client):
    r = client.get("/_app/../../../etc/passwd")
    assert r.status_code in (403, 404)


def test_favicon(client):
    r = client.get("/favicon.ico")
    assert r.status_code in (200, 204)


def test_graphs_rpc_passthrough(client):
    r = client.post("/_anki/get_graph_preferences", content=b"",
                    headers={"content-type": "application/binary"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/binary")


def test_deckbrowser_has_stats_link(client):
    assert "/graphs" in client.get("/deckbrowser").text
