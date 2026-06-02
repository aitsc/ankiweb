import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.collection_service import CollectionService
from ankiweb.screens.fields import make_fields_handler
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


def _field_names(col, ntid):
    return [f["name"] for f in col.models.get(ntid)["flds"]]


# (a) route renders Front + Back + "Add Field" + "Save"
def test_fields_route_renders(client):
    ntid = client.portal.call(
        client.app.state.service.run, lambda col: col.models.by_name("Basic")["id"])
    r = client.get(f"/fields/{ntid}")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="fields"' in r.text
    assert "Front" in r.text and "Back" in r.text
    assert "Add Field" in r.text
    assert "Save" in r.text


# (b) rename Front -> Q persists
async def test_rename_field_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_fields_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    payload = {
        "notetypeId": ntid, "sortf": 0,
        "fields": [
            {"orig": 0, "name": "Q", "font": "Arial", "size": 20, "rtl": False, "description": ""},
            {"orig": 1, "name": "Back", "font": "Arial", "size": 20, "rtl": False, "description": ""},
        ],
    }
    await handler("savefields:" + json.dumps(payload))
    assert await svc.run(lambda col: _field_names(col, ntid)) == ["Q", "Back"]
    assert ("ankiwebNavigate", ["/deckbrowser"]) in hub.calls
    await svc.close()


# (c) add a field persists
async def test_add_field_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_fields_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    payload = {
        "notetypeId": ntid, "sortf": 0,
        "fields": [
            {"orig": 0, "name": "Front", "font": "Arial", "size": 20, "rtl": False, "description": ""},
            {"orig": 1, "name": "Back", "font": "Arial", "size": 20, "rtl": False, "description": ""},
            {"orig": None, "name": "Extra", "font": "Arial", "size": 20, "rtl": False, "description": ""},
        ],
    }
    await handler("savefields:" + json.dumps(payload))
    assert await svc.run(lambda col: _field_names(col, ntid)) == ["Front", "Back", "Extra"]
    assert ("ankiwebNavigate", ["/deckbrowser"]) in hub.calls
    await svc.close()


# (d) delete a field persists (count drops)
async def test_delete_field_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_fields_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    before = await svc.run(lambda col: len(col.models.get(ntid)["flds"]))
    payload = {
        "notetypeId": ntid, "sortf": 0,
        "fields": [
            {"orig": 0, "name": "Front", "font": "Arial", "size": 20, "rtl": False, "description": ""},
        ],
    }
    await handler("savefields:" + json.dumps(payload))
    after = await svc.run(lambda col: _field_names(col, ntid))
    assert after == ["Front"]
    assert len(after) == before - 1
    assert ("ankiwebNavigate", ["/deckbrowser"]) in hub.calls
    await svc.close()


# (e) reposition swap persists new order
async def test_reposition_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_fields_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    payload = {
        "notetypeId": ntid, "sortf": 0,
        "fields": [
            {"orig": 1, "name": "Back", "font": "Arial", "size": 20, "rtl": False, "description": ""},
            {"orig": 0, "name": "Front", "font": "Arial", "size": 20, "rtl": False, "description": ""},
        ],
    }
    await handler("savefields:" + json.dumps(payload))
    assert await svc.run(lambda col: _field_names(col, ntid)) == ["Back", "Front"]
    await svc.close()


# (f) sortf change persists
async def test_sortf_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_fields_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    payload = {
        "notetypeId": ntid, "sortf": 1,
        "fields": [
            {"orig": 0, "name": "Front", "font": "Arial", "size": 20, "rtl": False, "description": ""},
            {"orig": 1, "name": "Back", "font": "Arial", "size": 20, "rtl": False, "description": ""},
        ],
    }
    await handler("savefields:" + json.dumps(payload))
    assert await svc.run(lambda col: col.models.get(ntid)["sortf"]) == 1
    await svc.close()


# (g) font/size/rtl/description persist
async def test_field_attrs_persist(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_fields_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    payload = {
        "notetypeId": ntid, "sortf": 0,
        "fields": [
            {"orig": 0, "name": "Front", "font": "Times", "size": 30, "rtl": True, "description": "hello"},
            {"orig": 1, "name": "Back", "font": "Arial", "size": 20, "rtl": False, "description": ""},
        ],
    }
    await handler("savefields:" + json.dumps(payload))

    def read(col):
        f = col.models.get(ntid)["flds"][0]
        return (f["font"], int(f["size"]), bool(f["rtl"]), f.get("description", ""))
    assert await svc.run(read) == ("Times", 30, True, "hello")
    await svc.close()


# (h) deleting ALL fields -> ankiwebFieldsError pushed + NO ankiwebNavigate
async def test_delete_all_fields_errors(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_fields_handler(svc, hub)
    ntid = await svc.run(_basic_id)
    before = await svc.run(lambda col: _field_names(col, ntid))
    payload = {"notetypeId": ntid, "sortf": 0, "fields": []}
    await handler("savefields:" + json.dumps(payload))
    fns = [c[0] for c in hub.calls]
    assert "ankiwebFieldsError" in fns
    assert "ankiwebNavigate" not in fns
    # unchanged
    assert await svc.run(lambda col: _field_names(col, ntid)) == before
    await svc.close()


# (i) editor.py editor_links_js() string contains 'fields' branch and /fields/
def test_editor_links_js_has_fields_branch():
    js = editor_links_js()
    assert "'fields'" in js
    assert "/fields/" in js
