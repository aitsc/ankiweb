from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2", import_tmp_dir=tmp_path / "import-tmp"))) as c:
        yield c


def test_passthrough_and_custom_registered():
    from ankiweb.anki_rpc.passthrough import PASSTHROUGH
    from ankiweb.anki_rpc.handlers import CUSTOM
    for m in ("get_deck_names", "get_field_names", "get_import_anki_package_presets"):
        assert m in PASSTHROUGH, m
    for m in ("getCsvMetadata", "importCsv", "importAnkiPackage", "importDone"):
        assert m in CUSTOM, m


def test_import_done_is_noop_204(client):
    r = client.post("/_anki/importDone", content=b"",
                    headers={"content-type": "application/binary"})
    assert r.status_code == 204


def _write_csv_in_tmp(client, text=b"front,back\nhello,world\nfoo,bar\n"):
    from ankiweb import import_tmp
    p = import_tmp.allocate(client.app.state.service.settings, ".csv")
    p.write_bytes(text)
    return str(p)


def test_get_csv_metadata_rejects_path_outside_tmp(client):
    import anki.import_export_pb2 as ie
    req = ie.CsvMetadataRequest(path="/etc/hostname")
    r = client.post("/_anki/getCsvMetadata", content=req.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 500   # rejected before the backend (path not allowed)


def test_get_csv_metadata_accepts_path_in_tmp(client):
    import anki.import_export_pb2 as ie
    path = _write_csv_in_tmp(client)
    req = ie.CsvMetadataRequest(path=path)
    r = client.post("/_anki/getCsvMetadata", content=req.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 200


def test_import_csv_round_trip_imports_notes(client):
    import anki.import_export_pb2 as ie
    svc = client.app.state.service
    path = _write_csv_in_tmp(client)
    before = client.portal.call(svc.run, lambda col: col.note_count())
    meta = client.portal.call(svc.run, lambda col: col.get_csv_metadata(path=path, delimiter=None))
    del meta.preview[:]
    req = ie.ImportCsvRequest(path=path, metadata=meta)
    r = client.post("/_anki/importCsv", content=req.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 200
    after = client.portal.call(svc.run, lambda col: col.note_count())
    assert after > before


def test_import_csv_rejects_path_outside_tmp(client):
    import anki.import_export_pb2 as ie
    req = ie.ImportCsvRequest(path="/etc/passwd", metadata=ie.CsvMetadata())
    r = client.post("/_anki/importCsv", content=req.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 500
