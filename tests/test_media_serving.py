import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    with TestClient(create_app(settings)) as c:
        yield c


def test_serves_media_file(client):
    # Write a media file via the backend, then fetch it. Drive the coroutine on the
    # app's own loop via TestClient's blocking portal (NOT asyncio.get_event_loop(),
    # which would create a foreign loop on py3.12 and clash with the service's loop).
    fname = client.portal.call(
        client.app.state.service.run,
        lambda col: col.media.write_data("hi.txt", b"hello"),
    )
    r = client.get(f"/{fname}")
    assert r.status_code == 200
    assert r.content == b"hello"


def test_media_traversal_blocked(client):
    # httpx/TestClient normalizes "/../.." in the URL before sending, so use a
    # percent-encoded traversal that survives normalization and reaches the guard.
    r = client.get("/%2e%2e/%2e%2e/etc/passwd")
    assert r.status_code == 403


def test_media_audio_mime(client):
    import os
    mdir = client.portal.call(client.app.state.service.run, lambda col: col.media.dir())
    for fname, mime in [("a.mp3", "audio/mpeg"), ("b.ogg", "audio/ogg"),
                        ("c.wav", "audio/wav"), ("d.m4a", "audio/mp4"),
                        ("e.webm", "video/webm")]:
        with open(os.path.join(mdir, fname), "wb") as f:
            f.write(b"\x00\x01\x02")
        r = client.get("/" + fname)
        assert r.status_code == 200, fname
        assert r.headers["content-type"].split(";")[0] == mime, (fname, r.headers["content-type"])
