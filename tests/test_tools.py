import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.collection_service import CollectionService
from ankiweb.screens.page import render_page
from ankiweb.screens.tools import render_tools_html, make_tools_handler


# ---- render tests -------------------------------------------------------

def test_render_tools_has_three_buttons_and_notetypes_link(temp_collection):
    html = render_tools_html(temp_collection)
    # three tool buttons + their result divs
    assert "pycmd('checkdb')" in html
    assert "id='res-db'" in html
    assert "pycmd('checkmedia')" in html
    assert "id='res-media'" in html
    assert "pycmd('emptycards')" in html
    assert "id='res-empty'" in html
    # Manage Note Types link
    assert "href='/notetypes'" in html
    assert "Manage Note Types" in html
    # the result dispatcher
    assert "ankiwebToolsResult" in html
    # real tr labels
    assert "Check Database" in html
    assert "Check Media" in html


# ---- handler round-trips -----------------------------------------------

class _Hub:
    def __init__(self):
        self.calls = []

    async def push_call(self, ctx, fn, args):
        self.calls.append((fn, args))


async def _svc(tmp_path):
    svc = CollectionService(Settings(collection_path=tmp_path / "c.anki2"))
    await svc.open()
    return svc


def _result_for(hub, which):
    """Return the html arg of the last ankiwebToolsResult(which, html) push, or None."""
    for fn, args in reversed(hub.calls):
        if fn == "ankiwebToolsResult" and args and args[0] == which:
            return args[1]
    return None


async def test_checkdb_pushes_report(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_tools_handler(svc, hub)
    await handler("checkdb")
    res = _result_for(hub, "db")
    assert res is not None
    # fix_integrity report mentions rebuilding/rebuilt the database
    assert "rebuilt" in res.lower() or "checked" in res.lower()
    await svc.close()


async def test_checkmedia_pushes_report(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_tools_handler(svc, hub)
    await handler("checkmedia")
    res = _result_for(hub, "media")
    assert res is not None
    assert "<pre>" in res
    await svc.close()


async def test_emptycards_roundtrip_deletes(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_tools_handler(svc, hub)

    # Seed a Cloze note with NO cloze deletion -> produces an empty card.
    def seed(col):
        did = col.decks.id("Default")
        m = col.models.by_name("Cloze")
        n = col.new_note(m)
        n["Text"] = "no cloze here"
        col.add_note(n, did)
        return col.card_count()
    before = await svc.run(seed)

    # report should find > 0 empty cards and stash their ids
    await handler("emptycards")
    res = _result_for(hub, "empty")
    assert res is not None
    assert "emptycards_delete" in res  # delete button present => ids stashed

    rep = await svc.run(lambda col: col.get_empty_cards())
    total = sum(len(n.card_ids) for n in rep.notes)
    assert total > 0

    # delete actually reduces the card count
    await handler("emptycards_delete")
    after = await svc.run(lambda col: col.card_count())
    assert after < before
    await svc.close()


async def test_deleteunused_no_files_is_noop(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_tools_handler(svc, hub)
    # No unused files stashed: must not crash and must push a fresh media result.
    await handler("deleteunused")
    assert _result_for(hub, "media") is not None
    await svc.close()


# ---- toolbar ------------------------------------------------------------

def test_toolbar_has_tools_link():
    html = render_page("deckbrowser", "x")
    assert "href='/tools'>Tools<" in html


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_tools_route_renders(client):
    r = client.get("/tools")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="tools"' in r.text
    assert "pycmd('checkdb')" in r.text
    assert "pycmd('checkmedia')" in r.text
    assert "pycmd('emptycards')" in r.text
    assert "href='/notetypes'" in r.text
