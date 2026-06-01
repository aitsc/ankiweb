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
def live_server_browse(tmp_path: Path):
    col_path = tmp_path / "browse.anki2"
    col = Collection(str(col_path))
    try:
        for q in ("dogword", "catword"):
            n = col.new_note(col.models.by_name("Basic")); n["Front"] = q; n["Back"] = q.upper()
            col.add_note(n, col.decks.id("Default"))
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8127)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8127, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8127"
    server.should_exit = True; t.join(timeout=5)


def test_browse_search_and_open(live_server_browse):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{live_server_browse}/browse")
        # initial empty search loads all rows
        page.wait_for_function(
            "document.getElementById('results-body').children.length>=2", timeout=6000)
        # narrow the search
        page.fill("#search", "dogword")
        page.keyboard.press("Enter")
        page.wait_for_function(
            "document.getElementById('results-body').children.length===1", timeout=6000)
        assert "dogword" in page.inner_text("#results-body")
        # click the row -> detail pane shows the field value
        page.click(".browser-row")
        page.wait_for_function(
            "document.getElementById('detail').textContent.includes('DOGWORD')", timeout=6000)
        browser.close()
