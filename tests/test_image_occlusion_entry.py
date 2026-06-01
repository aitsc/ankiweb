import io
import os
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f1f0000000049454e44ae426082")
OCCL = "{{c1::image-occlusion:rect:left=.1:top=.1:width=.2:height=.2}}"
BIN = {"content-type": "application/binary"}


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "c.anki2",
                        import_tmp_dir=tmp_path / "import-tmp")
    with TestClient(create_app(settings)) as c:
        yield c


def test_upload_image_returns_io_path(client):
    files = {"file": ("photo.png", io.BytesIO(PNG), "image/png")}
    r = client.post("/image-occlusion/upload", files=files)
    assert r.status_code == 200
    p = Path(r.json()["path"])
    assert p.exists() and p.read_bytes() == PNG
    assert p.parent.name == "io"                       # the dedicated subdir
    assert not p.name[:1].isdigit() or p.is_absolute()  # absolute => add-mode classification
    assert p.is_absolute()
    from ankiweb import import_tmp
    assert import_tmp.is_within(client.app.state.service.settings, str(p))


def test_upload_non_image_400(client):
    files = {"file": ("notes.csv", io.BytesIO(b"a,b"), "text/csv")}
    r = client.post("/image-occlusion/upload", files=files)
    assert r.status_code == 400


def test_upload_ensures_io_notetype(client):
    files = {"file": ("photo.png", io.BytesIO(PNG), "image/png")}
    client.post("/image-occlusion/upload", files=files)
    exists = client.portal.call(client.app.state.service.run,
                                lambda col: col.models.by_name("Image Occlusion") is not None)
    assert exists


def test_io_temp_survives_import_gc(client):
    from ankiweb import import_tmp
    s = client.app.state.service.settings
    p = import_tmp.io_allocate(s, ".png")
    p.write_bytes(PNG)
    old = time.time() - 7200
    os.utime(p, (old, old))
    import_tmp.gc(s, ttl_seconds=3600)   # the IMPORT gc (non-recursive) must NOT reap io/
    assert p.exists()


def test_image_persists_after_temp_deleted(client):
    import anki.image_occlusion_pb2 as iopb
    from ankiweb import import_tmp
    svc = client.app.state.service
    p = import_tmp.io_allocate(svc.settings, ".png")
    p.write_bytes(PNG)
    req = iopb.AddImageOcclusionNoteRequest(
        notetype_id=0, image_path=str(p), occlusions=OCCL, header="H", back_extra="B", tags=[])
    r = client.post("/_anki/addImageOcclusionNote", content=req.SerializeToString(), headers=BIN)
    assert r.status_code == 200
    os.remove(p)                                          # temp gone
    media = client.portal.call(svc.run, lambda col: os.listdir(col.media.dir()))
    assert any(f.endswith(".png") for f in media)          # note's image survives in media


def test_browser_routes_io_note_to_io_editor(client):
    import anki.image_occlusion_pb2 as iopb
    from ankiweb import import_tmp
    svc = client.app.state.service
    p = import_tmp.io_allocate(svc.settings, ".png")
    p.write_bytes(PNG)
    client.post("/_anki/addImageOcclusionNote", headers=BIN, content=iopb.AddImageOcclusionNoteRequest(
        notetype_id=0, image_path=str(p), occlusions=OCCL, header="H", back_extra="B", tags=[]).SerializeToString())

    def seed_normal(col):
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"; n["Back"] = "a"
        col.add_note(n, col.decks.id("Default"))
        return col.find_cards('note:"Image Occlusion"')[0], col.find_cards("note:Basic")[0]
    io_cid, normal_cid = client.portal.call(svc.run, seed_normal)

    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{io_cid}"})
        m = ws.receive_json()
        while not (m["type"] == "call" and m["fn"] == "ankiwebSetDetail"):
            m = ws.receive_json()
        assert "/image-occlusion/" in m["args"][0]
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{normal_cid}"})
        m = ws.receive_json()
        while not (m["type"] == "call" and m["fn"] == "ankiwebSetDetail"):
            m = ws.receive_json()
        assert "/edit?nid=" in m["args"][0]


def test_deckbrowser_has_image_occlusion_button(client):
    r = client.get("/deckbrowser")
    assert "ankiwebImageOcclusion" in r.text
