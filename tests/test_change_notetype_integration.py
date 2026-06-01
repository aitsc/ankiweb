import threading
import time
import pytest
import uvicorn
from pathlib import Path
from anki.collection import Collection
from ankiweb.config import Settings
from ankiweb.app import create_app

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


@pytest.fixture
def live_server_cnt(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    col = Collection(str(col_path))
    try:
        old = col.models.by_name("Basic")["id"]
        n = col.new_note(col.models.get(old))
        n["Front"] = "x"
        n["Back"] = "y"
        col.add_note(n, col.decks.id("Default"))
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8132)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8132, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8132", old
    server.should_exit = True
    t.join(timeout=5)


def test_change_notetype_spa_boots(live_server_cnt):
    url, old = live_server_cnt
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed",
                lambda r: errors.append("REQFAIL " + r.url) if ("/_app/" in r.url or "/_anki/" in r.url) else None)
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/_anki/" in r.url else None)
        page.goto(f"{url}/change-notetype/{old}")
        # The change-notetype SPA uses Svelte custom dropdowns (role="combobox") for field/template
        # mapping rather than native <select> elements; there are typically 5 comboboxes + 1 Save
        # button rendered once the info loads (no native <select> or <table> in this SPA).
        page.wait_for_function("document.querySelectorAll('[role=\"combobox\"],button').length>1", timeout=10000)
        page.wait_for_function("document.body.innerText.length>20", timeout=10000)
        assert not errors, errors
        assert any("get_change_notetype_info" in u.lower() or "getchangenotetypeinfo" in u.lower()
                   for u in posts), posts
        browser.close()
