import threading
import time
from pathlib import Path
from urllib.parse import quote
import pytest
import uvicorn
from anki.collection import Collection
from ankiweb.config import Settings
from ankiweb.app import create_app

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


@pytest.fixture
def live_server_imp(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    Collection(str(col_path)).close()
    tmp_dir = tmp_path / "import-tmp"
    tmp_dir.mkdir()
    csv = tmp_dir / "notes.csv"
    csv.write_text("front,back\nhello,world\nfoo,bar\n")
    settings = Settings(collection_path=col_path, port=8135, import_tmp_dir=tmp_dir)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8135, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8135", str(csv)
    server.should_exit = True
    t.join(timeout=5)


def test_import_csv_spa_boots(live_server_imp):
    url, csv_path = live_server_imp
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed",
                lambda r: errors.append("REQFAIL " + r.url) if ("/_app/" in r.url or "/_anki/" in r.url) else None)
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/_anki/" in r.url else None)
        page.goto(f"{url}/import-csv/{quote(csv_path, safe='')}")
        page.wait_for_function("document.querySelectorAll('select,button,table,input').length>2", timeout=10000)
        page.wait_for_function("document.body.innerText.length>30", timeout=10000)
        assert not errors, errors
        assert any("get_csv_metadata" in u.lower() or "getcsvmetadata" in u.lower() for u in posts), posts
        browser.close()
