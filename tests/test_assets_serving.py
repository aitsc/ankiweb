import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    with TestClient(create_app(settings)) as c:
        yield c


def test_serves_reviewer_js(client):
    r = client.get("/_anki/js/reviewer.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")


def test_serves_bare_css_remap(client):
    # /_anki/reviewer.css -> css/reviewer.css
    r = client.get("/_anki/reviewer.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")


def test_serves_vendor_min_remap(client):
    # /_anki/jquery.min.js -> js/vendor/jquery.min.js (bare .min.js vendor remap)
    r = client.get("/_anki/jquery.min.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")


def test_sveltekit_spa_fallback(client):
    # unknown sveltekit path (non-immutable) falls back to index.html
    r = client.get("/_anki/sveltekit/graphs")
    assert r.status_code == 200
    assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()
