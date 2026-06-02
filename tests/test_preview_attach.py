import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.screens.preview import render_preview_html


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _add(client, front="FRONTQ", back="BACKA"):
    def fn(col):
        n = col.new_note(col.models.by_name("Basic"))
        n["Front"] = front; n["Back"] = back
        col.add_note(n, col.decks.id("Default"))
        return n.id
    return client.portal.call(client.app.state.service.run, fn)


# ---- F4: Preview ----

def test_preview_renders_question_and_answer(client):
    nid = _add(client)
    r = client.get(f"/preview/{nid}")
    assert r.status_code == 200
    assert "FRONTQ" in r.text and "BACKA" in r.text
    assert "Front" in r.text and "Back" in r.text


def test_preview_includes_card_css(temp_collection):
    # render_output().question_and_style embeds the card CSS (<style> block)
    n = temp_collection.new_note(temp_collection.models.by_name("Basic"))
    n["Front"] = "x"; n["Back"] = "y"
    temp_collection.add_note(n, temp_collection.decks.id("Default"))
    html = render_preview_html(temp_collection, n.id)
    assert "<style" in html  # card styling present


def test_preview_strips_av_refs(temp_collection):
    n = temp_collection.new_note(temp_collection.models.by_name("Basic"))
    n["Front"] = "hi [sound:a.mp3]"; n["Back"] = "b"
    temp_collection.add_note(n, temp_collection.decks.id("Default"))
    html = render_preview_html(temp_collection, n.id)
    assert "anki:play" not in html  # the [anki:play:..] ref was stripped


# ---- F3 + editor-links glue ----

def test_editor_injects_links_interceptor(client):
    nid = _add(client)
    html = client.get(f"/edit?nid={nid}").text
    # the interceptor wraps the bridge and handles attach + preview
    assert "_awCmd" in html and "/upload_media" in html
    assert "/preview/" in html and "_awAttach" in html


def test_add_injects_links_interceptor(client):
    html = client.get("/add").text
    assert "_awCmd" in html and "/upload_media" in html
