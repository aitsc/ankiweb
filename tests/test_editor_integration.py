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
def live_server_edit(tmp_path: Path):
    col_path = tmp_path / "edit.anki2"
    col = Collection(str(col_path))
    try:
        n = col.new_note(col.models.by_name("Basic"))
        n["Front"] = "CapitalFrance"; n["Back"] = "Paris"
        col.add_note(n, col.decks.id("Default"))
        nid = n.id
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8128)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8128, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8128", nid
    server.should_exit = True; t.join(timeout=5)


def test_editor_mounts_and_loads(live_server_edit):
    url, nid = live_server_edit
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{url}/edit?nid={nid}")
        page.wait_for_function("document.querySelector('.note-editor')!==null", timeout=8000)
        page.wait_for_function(
            "(function(){"
            "var t='';"
            "function walk(r){"
            "for(var el of r.querySelectorAll('*')){"
            "if(el.shadowRoot){walk(el.shadowRoot);}"
            "}"
            "t+=r.textContent||'';"
            "}"
            "walk(document);"
            "return t.indexOf('CapitalFrance')>=0;"
            "})()",
            timeout=8000)
        assert not errors, errors
        browser.close()


def test_browse_single_select_embeds_editor(live_server_edit):
    url, nid = live_server_edit
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page()
        page.goto(f"{url}/browse")
        page.wait_for_function(
            "document.getElementById('results-body').children.length>=1", timeout=6000)
        page.locator(".browser-row").first.click()           # single-select -> embed editor
        page.wait_for_selector("#detail iframe.editor-frame", timeout=6000)
        # the editor mounts INSIDE the iframe (reach into contentDocument)
        page.wait_for_function(
            "() => { const f=document.querySelector('#detail iframe.editor-frame'); "
            "return f && f.contentDocument && "
            "f.contentDocument.querySelector('.note-editor')!==null; }",
            timeout=8000)
        browser.close()


def test_reviewer_e_opens_editor(live_server_edit):
    url, nid = live_server_edit
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page()
        page.goto(f"{url}/reviewer")
        page.wait_for_function(
            "document.getElementById('qa').textContent.includes('CapitalFrance')", timeout=8000)
        page.keyboard.press("e")
        page.wait_for_url("**/edit?nid=*", timeout=6000)
        browser.close()
