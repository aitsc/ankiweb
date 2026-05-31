import base64
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.ankiconnect.app import create_ankiconnect_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_ankiconnect_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _call(client, action, **params):
    r = client.post("/", json={"action": action, "version": 6, "params": params})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None, body["error"]
    return body["result"]


def test_store_and_retrieve_media_base64(client):
    data = base64.b64encode(b"hello-bytes").decode()
    fname = _call(client, "storeMediaFile", filename="hi.txt", data=data)
    assert fname == "hi.txt"
    assert _call(client, "retrieveMediaFile", filename="hi.txt") == data
    assert "hi.txt" in _call(client, "getMediaFilesNames", pattern="*.txt")
    assert isinstance(_call(client, "getMediaDirPath"), str)
    assert _call(client, "deleteMediaFile", filename="hi.txt") is None
    assert _call(client, "retrieveMediaFile", filename="hi.txt") is False


def test_store_media_from_path(client, tmp_path):
    p = tmp_path / "src.txt"
    p.write_bytes(b"frompath")
    fname = _call(client, "storeMediaFile", filename="p.txt", path=str(p))
    assert fname == "p.txt"
    assert base64.b64decode(_call(client, "retrieveMediaFile", filename="p.txt")) == b"frompath"


def test_add_note_with_picture_field(client):
    data = base64.b64encode(b"\x89PNG-fake").decode()
    nid = _call(client, "addNote", note={
        "deckName": "Default", "modelName": "Basic",
        "fields": {"Front": "q", "Back": ""},
        "picture": [{"filename": "img.png", "data": data, "fields": ["Back"]}],
    })
    info = _call(client, "notesInfo", notes=[nid])[0]
    assert '<img src="img.png">' in info["fields"]["Back"]["value"]


def test_store_media_skip_hash_short_circuits(client):
    import hashlib
    raw = b"skip-me"
    data = base64.b64encode(raw).decode()
    h = hashlib.md5(raw).hexdigest()
    # matching skipHash -> returns None and writes nothing
    assert _call(client, "storeMediaFile", filename="sk.txt", data=data, skipHash=h) is None
    assert "sk.txt" not in _call(client, "getMediaFilesNames", pattern="*.txt")


def test_add_note_picture_single_object_and_unknown_field(client):
    # picture may be a single object (not a list); a target field absent from the
    # model is ignored rather than fabricated.
    data = base64.b64encode(b"\x89PNG").decode()
    nid = _call(client, "addNote", note={
        "deckName": "Default", "modelName": "Basic",
        "fields": {"Front": "q", "Back": ""},
        "picture": {"filename": "one.png", "data": data, "fields": ["Back", "Nope"]},
    })
    info = _call(client, "notesInfo", notes=[nid])[0]
    assert '<img src="one.png">' in info["fields"]["Back"]["value"]
    assert "Nope" not in info["fields"]


def test_notes_info_missing_id_appends_empty(client):
    # B2 parity fix: a missing id yields {} (positional), not an error
    res = _call(client, "notesInfo", notes=[999999999])
    assert res == [{}]
