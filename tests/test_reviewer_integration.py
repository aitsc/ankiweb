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


@pytest.fixture
def live_server_audio(tmp_path: Path):
    import os
    col_path = tmp_path / "audio.anki2"
    col = Collection(str(col_path))
    try:
        m = col.models.new("AudioM")
        col.models.add_field(m, col.models.new_field("Front"))
        t = col.models.new_template("C"); t["qfmt"] = "{{Front}} [sound:hello.mp3]"; t["afmt"] = "{{Front}}"
        col.models.add_template(m, t); col.models.add_dict(m)
        did = col.decks.id("Default")
        n = col.new_note(col.models.by_name("AudioM")); n["Front"] = "Q"
        col.add_note(n, did); col.decks.set_current(did)
        with open(os.path.join(col.media.dir(), "hello.mp3"), "wb") as f:
            f.write(b"\x00")
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8126)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8126, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8126"
    server.should_exit = True; t.join(timeout=5)


def test_audio_autoplays_on_question(live_server_audio):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.add_init_script(
            "window.__played=[];"
            "HTMLMediaElement.prototype.play=function(){window.__played.push(this.src);"
            "return Promise.resolve();};")
        page.goto(f"{live_server_audio}/reviewer")
        page.wait_for_function("document.getElementById('qa').textContent.length>0", timeout=6000)
        page.wait_for_function("window.__played.length>0", timeout=6000)
        assert any(s.endswith("/hello.mp3") for s in page.evaluate("window.__played"))
        browser.close()
