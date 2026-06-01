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
def live_server_add(tmp_path: Path):
    col_path = tmp_path / "add.anki2"
    Collection(str(col_path)).close()           # empty collection
    settings = Settings(collection_path=col_path, port=8129)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8129, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8129"
    server.should_exit = True; t.join(timeout=5)


def test_add_note_via_ui(live_server_add):
    url = live_server_add
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR:", e))
        page.goto(f"{url}/add")
        page.wait_for_function("document.querySelector('.note-editor')!==null", timeout=8000)
        page.wait_for_function(
            "document.querySelectorAll('.field-container').length>=2", timeout=8000)
        page.evaluate("window.focusField(0)")
        page.keyboard.type("FrontText")
        page.evaluate("window.focusField(1)")
        page.keyboard.type("BackText")
        page.click("#add-btn")
        page.wait_for_function(
            "document.getElementById('add-toast').textContent.includes('Added')", timeout=8000)
        browser.close()
