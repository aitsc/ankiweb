import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_settings_has_import_tmp_dir(tmp_path):
    s = Settings(collection_path=tmp_path / "c.anki2")
    assert isinstance(s.import_tmp_dir, Path)


def test_service_exposes_settings(client):
    assert client.app.state.service.settings.import_tmp_dir is not None


def test_upload_csv_returns_route_and_temp_path(client):
    files = {"file": ("notes.csv", io.BytesIO(b"front,back\na,b\n"), "text/csv")}
    r = client.post("/import/upload", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "import-csv"
    p = Path(body["path"])
    assert p.exists() and p.read_bytes() == b"front,back\na,b\n"
    # the temp file is inside the managed import dir
    from ankiweb import import_tmp
    assert import_tmp.is_within(client.app.state.service.settings, str(p))


def test_upload_apkg_routes_to_anki_package(client):
    files = {"file": ("deck.apkg", io.BytesIO(b"PK\x03\x04stub"), "application/octet-stream")}
    r = client.post("/import/upload", files=files)
    assert r.status_code == 200
    assert r.json()["route"] == "import-anki-package"


def test_upload_unknown_extension_400(client):
    files = {"file": ("note.xyz", io.BytesIO(b"x"), "application/octet-stream")}
    r = client.post("/import/upload", files=files)
    assert r.status_code == 400


def test_import_csv_route_serves_spa_shell(client):
    r = client.get("/import-csv/%2Ftmp%2Ffake.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "_app/immutable/entry" in r.text


def test_import_anki_package_route_serves_spa_shell(client):
    r = client.get("/import-anki-package/%2Ftmp%2Ffake.apkg")
    assert r.status_code == 200
    assert "_app/immutable/entry" in r.text


def test_gc_removes_old_files(client, tmp_path):
    import os, time
    from ankiweb import import_tmp
    s = client.app.state.service.settings
    p = import_tmp.allocate(s, ".csv")
    p.write_bytes(b"x")
    old = time.time() - 7200
    os.utime(p, (old, old))
    import_tmp.gc(s, ttl_seconds=3600)
    assert not p.exists()
