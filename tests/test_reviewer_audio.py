import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        c.portal.call(c.app.state.service.run, _seed)
        yield c


def _seed(col):
    import os
    m = col.models.new("AudioModel")
    col.models.add_field(m, col.models.new_field("Front"))
    col.models.add_field(m, col.models.new_field("Back"))
    t = col.models.new_template("Card1")
    t["qfmt"] = "{{Front}} [sound:hello.mp3]"
    t["afmt"] = "{{FrontSide}}<hr id=answer>{{Back}} [sound:bye.mp3]"
    col.models.add_template(m, t)
    col.models.add_dict(m)
    n = col.new_note(col.models.by_name("AudioModel")); n["Front"] = "q"; n["Back"] = "a"
    col.add_note(n, col.decks.id("Default"))
    for fn in ("hello.mp3", "bye.mp3"):
        with open(os.path.join(col.media.dir(), fn), "wb") as f:
            f.write(b"\x00")


def _calls(ws, n):
    out = {}
    for _ in range(n):
        m = ws.receive_json()
        if m["type"] == "call":
            out.setdefault(m["fn"], []).append(m["args"])
    return out


def test_question_autoplays_and_renders_buttons(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        calls = _calls(ws, 3)   # _showQuestion + ankiwebSetAnswerBar + ankiwebPlayAudio
        assert "ankiwebPlayAudio" in calls
        assert calls["ankiwebPlayAudio"][0] == [["hello.mp3"]]
        q_html = calls["_showQuestion"][0][0]
        assert "[anki:play" not in q_html
        assert "play:q:0" in q_html and "replay-button" in q_html


def test_answer_autoplays_and_play_and_replay(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        _calls(ws, 3)
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "ans"})
        calls = _calls(ws, 3)   # _showAnswer + ease bar + ankiwebPlayAudio
        assert "ankiwebPlayAudio" in calls
        # answer-side AUTOPLAY is answer-only (NOT the question audio) — matches Qt _showAnswer
        assert calls["ankiwebPlayAudio"][0][0] == ["bye.mp3"]
        # per-clip replay of the answer's first sound
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "play:a:0"})
        c2 = _calls(ws, 1)
        assert c2["ankiwebPlayAudio"][0][0] == ["bye.mp3"]
        # R-key replay on the answer side prepends the question audio (replayq default True)
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "replay"})
        c3 = _calls(ws, 1)
        assert c3["ankiwebPlayAudio"][0][0] == ["hello.mp3", "bye.mp3"]
