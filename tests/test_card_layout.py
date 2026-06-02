import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.collection_service import CollectionService
from ankiweb.screens.card_layout import make_card_layout_handler
from ankiweb.screens.editor import editor_links_js


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


class _Hub:
    def __init__(self):
        self.calls = []

    async def push_call(self, ctx, fn, args):
        self.calls.append((fn, args))


async def _svc(tmp_path):
    svc = CollectionService(Settings(collection_path=tmp_path / "c.anki2"))
    await svc.open()
    return svc


def _basic_id(col):
    return col.models.by_name("Basic")["id"]


def _tmpls(col, ntid):
    return col.models.get(ntid)["tmpls"]


def _tmpl_names(col, ntid):
    return [t["name"] for t in _tmpls(col, ntid)]


def _add_note(col, ntid):
    """Add a Basic note so previews / card generation have something to work with."""
    m = col.models.get(ntid)
    note = col.new_note(m)
    note.fields[0] = "front text"
    note.fields[1] = "back text"
    col.add_note(note, col.decks.id("Default"))
    return note.id


# (a) route renders the Card 1 qfmt/afmt + css textarea + Add card type + Save
def test_card_layout_route_renders(client):
    ntid = client.portal.call(
        client.app.state.service.run, lambda col: col.models.by_name("Basic")["id"])
    r = client.get(f"/card-layout/{ntid}")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="cardlayout"' in r.text
    # Basic Card 1 qfmt is "{{Front}}" and afmt references FrontSide + Back
    assert "{{Front}}" in r.text
    assert "{{Back}}" in r.text
    assert "id='css'" in r.text
    assert "Add Card Type" in r.text
    assert "Save" in r.text


# (b) edit qfmt/afmt persists
async def test_edit_qfmt_afmt_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_card_layout_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    payload = {
        "notetypeId": ntid,
        "css": ".card{}",
        "templates": [
            {"orig": 0, "name": "Card 1", "qfmt": "Q: {{Front}}", "afmt": "A: {{Back}}"},
        ],
    }
    await handler("savelayout:" + json.dumps(payload))

    def read(col):
        t = _tmpls(col, ntid)[0]
        return (t["qfmt"], t["afmt"])
    assert await svc.run(read) == ("Q: {{Front}}", "A: {{Back}}")
    assert ("ankiwebNavigate", ["/deckbrowser"]) in hub.calls
    await svc.close()


# (c) edit css persists
async def test_edit_css_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_card_layout_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    payload = {
        "notetypeId": ntid,
        "css": ".card { color: red; }",
        "templates": [
            {"orig": 0, "name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}{{Back}}"},
        ],
    }
    await handler("savelayout:" + json.dumps(payload))
    assert await svc.run(lambda col: col.models.get(ntid)["css"]) == ".card { color: red; }"
    await svc.close()


# (d) rename a template persists
async def test_rename_template_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_card_layout_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    payload = {
        "notetypeId": ntid,
        "css": "",
        "templates": [
            {"orig": 0, "name": "Renamed", "qfmt": "{{Front}}", "afmt": "{{Back}}"},
        ],
    }
    await handler("savelayout:" + json.dumps(payload))
    assert await svc.run(lambda col: _tmpl_names(col, ntid)) == ["Renamed"]
    await svc.close()


# (e) add a template persists (count up)
async def test_add_template_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_card_layout_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    before = await svc.run(lambda col: len(_tmpls(col, ntid)))
    payload = {
        "notetypeId": ntid,
        "css": "",
        "templates": [
            {"orig": 0, "name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}{{Back}}"},
            {"orig": None, "name": "Card 2", "qfmt": "{{Back}}", "afmt": "{{FrontSide}}{{Front}}"},
        ],
    }
    await handler("savelayout:" + json.dumps(payload))
    names = await svc.run(lambda col: _tmpl_names(col, ntid))
    assert names == ["Card 1", "Card 2"]
    assert len(names) == before + 1
    await svc.close()


# (f) reposition swap persists
async def test_reposition_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_card_layout_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    # first add a second template so there is something to swap
    await handler("savelayout:" + json.dumps({
        "notetypeId": ntid, "css": "",
        "templates": [
            {"orig": 0, "name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"},
            {"orig": None, "name": "Card 2", "qfmt": "{{Back}}", "afmt": "{{Front}}"},
        ],
    }))
    ords = await svc.run(lambda col: [(t["name"], t["ord"]) for t in _tmpls(col, ntid)])
    name_to_ord = dict(ords)
    # now swap them
    await handler("savelayout:" + json.dumps({
        "notetypeId": ntid, "css": "",
        "templates": [
            {"orig": name_to_ord["Card 2"], "name": "Card 2", "qfmt": "{{Back}}", "afmt": "{{Front}}"},
            {"orig": name_to_ord["Card 1"], "name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"},
        ],
    }))
    assert await svc.run(lambda col: _tmpl_names(col, ntid)) == ["Card 2", "Card 1"]
    await svc.close()


# (g) delete a template persists (count down)
async def test_delete_template_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_card_layout_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    # add a second template first
    await handler("savelayout:" + json.dumps({
        "notetypeId": ntid, "css": "",
        "templates": [
            {"orig": 0, "name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"},
            {"orig": None, "name": "Card 2", "qfmt": "{{Back}}", "afmt": "{{Front}}"},
        ],
    }))
    before = await svc.run(lambda col: len(_tmpls(col, ntid)))
    assert before == 2
    ords = await svc.run(lambda col: dict((t["name"], t["ord"]) for t in _tmpls(col, ntid)))
    # keep only Card 1
    await handler("savelayout:" + json.dumps({
        "notetypeId": ntid, "css": "",
        "templates": [
            {"orig": ords["Card 1"], "name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"},
        ],
    }))
    names = await svc.run(lambda col: _tmpl_names(col, ntid))
    assert names == ["Card 1"]
    assert len(names) == before - 1
    await svc.close()


# (h) deleting all templates -> ankiwebCardLayoutError + no navigate
async def test_delete_all_templates_errors(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_card_layout_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    before = await svc.run(lambda col: _tmpl_names(col, ntid))
    await handler("savelayout:" + json.dumps({
        "notetypeId": ntid, "css": "", "templates": [],
    }))
    fns = [c[0] for c in hub.calls]
    assert "ankiwebCardLayoutError" in fns
    assert "ankiwebNavigate" not in fns
    assert await svc.run(lambda col: _tmpl_names(col, ntid)) == before
    await svc.close()


# (i) previewlayout with an existing note -> ankiwebNavigate to /preview/<nid>
async def test_previewlayout_navigates(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_card_layout_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    nid = await svc.run(lambda col: _add_note(col, ntid))
    await handler("previewlayout")
    assert ("ankiwebNavigate", [f"/preview/{nid}"]) in hub.calls
    await svc.close()


# (j) editor_links_js() contains the cards branch + /card-layout/
def test_editor_links_js_has_cards_branch():
    js = editor_links_js()
    assert "'cards'" in js
    assert "/card-layout/" in js
