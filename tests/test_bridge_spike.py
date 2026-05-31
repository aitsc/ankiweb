import threading
import time
import pytest
import uvicorn
from pathlib import Path
from anki.collection import Collection
from ankiweb.config import Settings
from ankiweb.app import create_app

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


@pytest.fixture
def live_server(tmp_path: Path):
    col_path = tmp_path / "collection.anki2"
    # Seed ONE card synchronously on disk BEFORE the server opens the file —
    # no event loop, no cross-loop hazard, no double-open. Close to release the lock.
    col = Collection(str(col_path))
    try:
        n = col.new_note(col.models.by_name("Basic"))
        n["Front"] = "Spike Q"
        n["Back"] = "Spike A"
        col.add_note(n, col.decks.id("Default"))
    finally:
        col.close()

    settings = Settings(collection_path=col_path, port=8123)
    app = create_app(settings)
    config = uvicorn.Config(app, host="127.0.0.1", port=8123, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start in time")
        time.sleep(0.05)

    yield "http://127.0.0.1:8123"
    server.should_exit = True
    t.join(timeout=5)


def test_reviewer_js_renders_question(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        # Surface browser-side failures so a spike regression is debuggable.
        page.on("console", lambda m: print("CONSOLE:", m.type, m.text))
        page.on("pageerror", lambda e: print("PAGEERROR:", e))
        # context=reviewer so the page's WS registers under the same context the
        # server pushes _showQuestion to (bootstrap.ts reads ?context= from the URL).
        page.goto(f"{live_server}/spike/reviewer?context=reviewer")
        page.wait_for_timeout(800)  # WS connect + bundle load + ready()
        # The real bundle copies its exports onto window via
        # `for (let t in $o) window[t] = $o[t];` at the end of the IIFE.
        assert page.evaluate("typeof window._showQuestion") == "function"
        import httpx
        httpx.post(f"{live_server}/spike/push_question")
        page.wait_for_function(
            "document.getElementById('qa').textContent.includes('Spike Q')",
            timeout=5000,
        )
        assert "Spike Q" in page.inner_text("#qa")
        browser.close()
