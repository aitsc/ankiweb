import threading
import time
from pathlib import Path
import pytest
import uvicorn
from anki.collection import Collection
from ankiweb.config import Settings
from ankiweb.app import create_app

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


@pytest.fixture
def live(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    Collection(str(col_path)).close()
    settings = Settings(collection_path=col_path, port=8138, import_tmp_dir=tmp_path / "it")
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8138, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8138"
    server.should_exit = True; t.join(timeout=5)


def test_night_threads_hash_into_spa_links(live):
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page()
        page.goto(f"{live}/deckbrowser")
        # default: Stats link points at /graphs (no #night), not in night mode
        assert page.get_attribute("a[href*='/graphs']", "href") == "/graphs"
        assert not page.evaluate("document.documentElement.classList.contains('night-mode')")
        # turn night on (persisted) and reload
        page.evaluate("localStorage.setItem('ankiweb-night','1')")
        page.goto(f"{live}/deckbrowser")
        assert page.evaluate("document.documentElement.classList.contains('night-mode')")
        # the Stats link now carries #night so the graphs SPA renders dark too
        assert page.get_attribute("a[href*='/graphs']", "href") == "/graphs#night"
        browser.close()
