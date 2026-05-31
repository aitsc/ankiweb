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
    m = col.models.new("TypeM")
    col.models.add_field(m, col.models.new_field("Front"))
    col.models.add_field(m, col.models.new_field("Back"))
    t = col.models.new_template("Card1")
    t["qfmt"] = "{{Front}}\n\n{{type:Back}}"
    t["afmt"] = "{{FrontSide}}<hr id=answer>{{Back}}"
    col.models.add_template(m, t)
    col.models.add_dict(m)
    n = col.new_note(col.models.by_name("TypeM")); n["Front"] = "capital?"; n["Back"] = "Paris"
    col.add_note(n, col.decks.id("Default"))


def test_type_answer_ws_roundtrip(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        for _ in range(2):
            ws.receive_json()                      # drain _showQuestion + ankiwebSetAnswerBar
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "typed:Paros"})
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "ans"})
        diff = None
        for _ in range(6):
            m = ws.receive_json()
            if m["type"] == "call" and m["fn"] == "_showAnswer":
                diff = m["args"][0]
                break
        assert diff is not None and ("typeBad" in diff or "typeMissed" in diff)
