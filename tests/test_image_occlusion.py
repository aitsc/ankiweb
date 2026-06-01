import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app

# a minimal valid 1x1 PNG
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


def _img_in_tmp(client, name="pic.png"):
    from ankiweb import import_tmp
    p = import_tmp.dir(client.app.state.service.settings) / name
    p.write_bytes(PNG)
    return str(p)


def test_route_serves_shell_for_path_and_noteid(client):
    for seg in ("123", "%2Ftmp%2Ffoo.png"):
        r = client.get(f"/image-occlusion/{seg}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert "_app/immutable/entry" in r.text


def test_membership():
    from ankiweb.anki_rpc.passthrough import PASSTHROUGH
    from ankiweb.anki_rpc.handlers import CUSTOM
    assert "get_image_occlusion_note" in PASSTHROUGH
    assert "get_image_occlusion_fields" in PASSTHROUGH
    for m in ("getImageForOcclusion", "addImageOcclusionNote", "updateImageOcclusionNote"):
        assert m in CUSTOM


def test_get_image_for_occlusion_confinement(client):
    import anki.image_occlusion_pb2 as iopb
    p = _img_in_tmp(client)
    ok = client.post("/_anki/getImageForOcclusion",
                     content=iopb.GetImageForOcclusionRequest(path=p).SerializeToString(), headers=BIN)
    assert ok.status_code == 200
    bad = client.post("/_anki/getImageForOcclusion",
                      content=iopb.GetImageForOcclusionRequest(path="/etc/hostname").SerializeToString(), headers=BIN)
    assert bad.status_code == 500


def test_get_image_for_occlusion_touches_mtime(client):
    import anki.image_occlusion_pb2 as iopb
    p = _img_in_tmp(client, "touch.png")
    old = 100000.0
    os.utime(p, (old, old))
    client.post("/_anki/getImageForOcclusion",
                content=iopb.GetImageForOcclusionRequest(path=p).SerializeToString(), headers=BIN)
    assert os.path.getmtime(p) > old + 1000  # bumped toward now


def test_add_image_occlusion_note_round_trip(client):
    import anki.image_occlusion_pb2 as iopb
    svc = client.app.state.service
    p = _img_in_tmp(client, "add.png")
    before = client.portal.call(svc.run, lambda col: col.note_count())
    req = iopb.AddImageOcclusionNoteRequest(
        notetype_id=0, image_path=p, occlusions=OCCL, header="H", back_extra="B", tags=["io"])
    r = client.post("/_anki/addImageOcclusionNote", content=req.SerializeToString(), headers=BIN)
    assert r.status_code == 200
    after = client.portal.call(svc.run, lambda col: col.note_count())
    assert after == before + 1
    media = client.portal.call(svc.run, lambda col: os.listdir(col.media.dir()))
    assert any(f.endswith(".png") for f in media)


def test_add_rejects_path_outside_tmp(client):
    import anki.image_occlusion_pb2 as iopb
    req = iopb.AddImageOcclusionNoteRequest(
        notetype_id=0, image_path="/etc/passwd", occlusions=OCCL, header="", back_extra="", tags=[])
    r = client.post("/_anki/addImageOcclusionNote", content=req.SerializeToString(), headers=BIN)
    assert r.status_code == 500


def test_update_image_occlusion_note_round_trip(client):
    import anki.image_occlusion_pb2 as iopb
    svc = client.app.state.service
    p = _img_in_tmp(client, "upd.png")
    add = iopb.AddImageOcclusionNoteRequest(
        notetype_id=0, image_path=p, occlusions=OCCL, header="H1", back_extra="B", tags=[])
    client.post("/_anki/addImageOcclusionNote", content=add.SerializeToString(), headers=BIN)
    nid = client.portal.call(svc.run, lambda col: col.find_notes('note:"Image Occlusion"')[0])
    upd = iopb.UpdateImageOcclusionNoteRequest(
        note_id=nid, occlusions=OCCL, header="H2", back_extra="B", tags=[])
    r = client.post("/_anki/updateImageOcclusionNote", content=upd.SerializeToString(), headers=BIN)
    assert r.status_code == 200
    hdr = client.portal.call(svc.run, lambda col: col.get_image_occlusion_note(note_id=nid).note.header)
    assert hdr == "H2"
