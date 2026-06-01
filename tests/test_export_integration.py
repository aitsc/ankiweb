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
def live_server_exp(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    col = Collection(str(col_path))
    try:
        did = col.decks.id("Default")
        for i in range(2):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"] = f"f{i}"; n["Back"] = f"b{i}"
            col.add_note(n, did)
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8136,
                        import_tmp_dir=tmp_path / "import-tmp")
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8136, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8136"
    server.should_exit = True
    t.join(timeout=5)


def test_export_form_downloads(live_server_exp):
    url = live_server_exp
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{url}/export")
        page.wait_for_selector("#go", timeout=10000)
        assert "Export" in page.inner_text("body")
        with page.expect_download(timeout=15000) as dl:
            page.click("#go")
        download = dl.value
        assert download.suggested_filename.endswith(".apkg")
        assert not errors, errors
        browser.close()
