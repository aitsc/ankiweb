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
def live_server_fd(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    col = Collection(str(col_path))
    try:
        did = col.decks.id("Default")
        col.decks.set_current(did)
        for i in range(4):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"] = f"f{i}"; n["Back"] = f"b{i}"
            col.add_note(n, did)
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8134)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8134, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8134"
    server.should_exit = True
    t.join(timeout=5)


def test_filtered_deck_form_builds_and_navigates(live_server_fd):
    url = live_server_fd
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{url}/filtered-deck")
        page.wait_for_selector("#go", timeout=10000)
        assert "Filtered Deck" in page.inner_text("body")
        page.fill("#search1", "deck:Default")
        page.click("#go")
        page.wait_for_url("**/overview", timeout=10000)
        assert not errors, errors
        browser.close()
