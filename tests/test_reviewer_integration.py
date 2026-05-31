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
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "CapitalFrance"; n["Back"] = "Paris"
        col.add_note(n, col.decks.id("Default"))
        col.decks.set_current(col.decks.id("Default"))
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8125)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8125, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8125"
    server.should_exit = True; t.join(timeout=5)


def test_study_one_card(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR:", e))
        page.goto(f"{live_server}/reviewer")
        # real reviewer.js renders the question into #qa
        page.wait_for_function("document.getElementById('qa').textContent.includes('CapitalFrance')",
                               timeout=6000)
        # Show Answer
        page.click("#ansbut")
        page.wait_for_function("document.getElementById('qa').textContent.includes('Paris')",
                               timeout=6000)
        # four ease buttons appear with interval labels
        page.wait_for_selector(".ease[data-ease='4']")
        assert page.locator(".ease").count() == 4
        # rate Easy (ease4) → the lone new card graduates to review (multi-day) →
        # today's queue empties → reviewer navigates to /overview (Congrats).
        # (Good/ease3 would leave the card in the learning queue, re-fetched as the
        # same card → it would never finish.)
        page.click(".ease[data-ease='4']")
        page.wait_for_url("**/overview", timeout=6000)
        assert "Congratulations" in page.inner_text("body")
        browser.close()
