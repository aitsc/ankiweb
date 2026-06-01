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

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f1f0000000049454e44ae426082")
OCCL = "{{c1::image-occlusion:rect:left=.1:top=.1:width=.2:height=.2}}"


@pytest.fixture
def live_io(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    tmp_dir = tmp_path / "import-tmp"
    io_dir = tmp_dir / "io"
    io_dir.mkdir(parents=True)
    img = io_dir / "pic.png"
    img.write_bytes(PNG)
    col = Collection(str(col_path))
    try:
        import anki.image_occlusion_pb2 as iopb
        col.add_image_occlusion_notetype()
        nt = col.models.by_name("Image Occlusion")
        col.add_image_occlusion_note(notetype_id=nt["id"], image_path=str(img),
                                     occlusions=OCCL, header="H", back_extra="B", tags=[])
        nid = col.find_notes('note:"Image Occlusion"')[0]
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8137, import_tmp_dir=tmp_dir)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8137, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8137", str(img), nid
    server.should_exit = True
    t.join(timeout=5)


def _boot(url, expect_method):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed",
                lambda r: errors.append("REQFAIL " + r.url) if ("/_app/" in r.url or "/_anki/" in r.url) else None)
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/_anki/" in r.url else None)
        page.goto(url)
        page.wait_for_selector("canvas", timeout=15000)   # MaskEditor's <canvas>
        page.wait_for_function("document.body.innerText.length>0 || document.querySelector('canvas')", timeout=10000)
        assert not errors, errors
        # The SPA POSTs camelCase RPC names (e.g. getImageForOcclusion); strip underscores for comparison
        assert any(expect_method.lower().replace("_", "") in u.lower() for u in posts), (expect_method, posts)
        browser.close()


def test_io_add_mode_boots(live_io):
    base, img_path, _nid = live_io
    _boot(f"{base}/image-occlusion/{quote(img_path, safe='')}", "get_image_for_occlusion")


def test_io_edit_mode_boots(live_io):
    base, _img, nid = live_io
    _boot(f"{base}/image-occlusion/{nid}", "get_image_occlusion_note")
