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
def live_server(tmp_path: Path):
    col_path = tmp_path / "collection.anki2"
    col = Collection(str(col_path))
    try:
        for i in range(3):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"] = f"Q{i}"
            col.add_note(n, col.decks.id("Default"))
    finally:
        col.close()

    settings = Settings(collection_path=col_path, port=8124)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8124, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8124"
    server.should_exit = True
    t.join(timeout=5)


def test_browse_then_open_deck(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR:", e))
        page.goto(f"{live_server}/")
        # deck browser shows the Default deck with a new-count of 3
        page.wait_for_selector("tr.deck")
        assert "Default" in page.inner_text("body")
        assert "3" in page.inner_text("tr.deck")
        # click the deck name → server sets current + pushes navigate → lands on /overview
        page.click("a.deck")
        page.wait_for_url("**/overview", timeout=5000)
        assert "Study Now" in page.inner_text("body")
        browser.close()
