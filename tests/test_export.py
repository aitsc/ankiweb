from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "c.anki2",
                        import_tmp_dir=tmp_path / "import-tmp")
    with TestClient(create_app(settings)) as c:
        yield c


def _seed(client, n=2):
    def seed(col):
        did = col.decks.id("Default")
        for i in range(n):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = f"f{i}"; note["Back"] = f"b{i}"
            col.add_note(note, did)
        return did
    return client.portal.call(client.app.state.service.run, seed)


def test_export_route_renders_form(client):
    _seed(client)
    r = client.get("/export")
    assert r.status_code == 200
    body = r.text
    assert "Whole Collection" in body
    assert "Default" in body
    assert "value='apkg'" in body and "value='colpkg'" in body
    assert "value='notes_csv'" in body and "value='cards_csv'" in body


def _assert_download(r, ext):
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert ext in r.headers.get("content-disposition", "")
    assert len(r.content) > 0


def test_export_apkg_whole_collection(client):
    _seed(client)
    r = client.post("/export", data={"fmt": "apkg", "target": "all",
                                     "with_media": "on", "legacy": "on"})
    _assert_download(r, ".apkg")


def test_export_apkg_deck(client):
    did = _seed(client)
    r = client.post("/export", data={"fmt": "apkg", "target": str(did), "legacy": "on"})
    _assert_download(r, ".apkg")


def test_export_notes_csv(client):
    _seed(client)
    r = client.post("/export", data={"fmt": "notes_csv", "target": "all",
                                     "with_tags": "on", "with_deck": "on", "with_notetype": "on"})
    _assert_download(r, ".csv")


def test_export_cards_csv(client):
    _seed(client)
    r = client.post("/export", data={"fmt": "cards_csv", "target": "all"})
    _assert_download(r, ".csv")


def test_export_colpkg_then_collection_still_usable(client):
    _seed(client)
    r = client.post("/export", data={"fmt": "colpkg", "with_media": "on", "legacy": "on"})
    _assert_download(r, ".colpkg")
    # the reopen() guard: export_collection_package killed the live collection;
    # the service must have revived it.
    count = client.portal.call(client.app.state.service.run, lambda col: col.card_count())
    assert count == 2


def test_deckbrowser_has_export_link(client):
    _seed(client)
    r = client.get("/deckbrowser")
    assert "/export" in r.text
