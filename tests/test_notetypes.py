import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.collection_service import CollectionService
from ankiweb.screens.notetypes import make_notetypes_handler


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


def _cloze_id(col):
    return col.models.by_name("Cloze")["id"]


def _fns(hub):
    return [c[0] for c in hub.calls]


# (a) /notetypes renders Basic + Cloze rows with /fields/ and /card-layout/ links + Add form
def test_notetypes_route_renders(client):
    r = client.get("/notetypes")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="notetypes"' in r.text
    basicId, clozeId = client.portal.call(
        client.app.state.service.run,
        lambda col: (col.models.by_name("Basic")["id"], col.models.by_name("Cloze")["id"]),
    )
    assert "Basic" in r.text and "Cloze" in r.text
    assert f"/fields/{basicId}" in r.text
    assert f"/card-layout/{basicId}" in r.text
    assert f"/fields/{clozeId}" in r.text
    assert f"/card-layout/{clozeId}" in r.text
    # Add form: a text input + a select to clone + an Add button
    assert "<select" in r.text
    # rename/delete controls
    assert "rename:" in r.text
    assert "delete:" in r.text
    assert "add:" in r.text


# (b) RENAME: rename:{basicId}:MyBasic -> name persists, pushes ankiwebReload
async def test_rename_persists(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_notetypes_handler(svc, hub)
    basicId = await svc.run(_basic_id)
    await handler(f"rename:{basicId}:MyBasic")
    assert await svc.run(lambda col: col.models.get(basicId)["name"]) == "MyBasic"
    assert "ankiwebReload" in _fns(hub)


# (c) ADD: add:{basicId}:Cloned -> new notetype exists AND adding a note generates a card
async def test_add_clones_usable_notetype(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_notetypes_handler(svc, hub)
    basicId = await svc.run(_basic_id)
    await handler(f"add:{basicId}:Cloned")
    assert "ankiwebReload" in _fns(hub)

    def check(col):
        m2 = col.models.by_name("Cloned")
        assert m2 is not None
        n = col.new_note(m2)
        n.fields[0] = "x"
        did = col.decks.id("Default")
        col.add_note(n, did)
        return n.cards()

    cards = await svc.run(check)
    assert cards  # non-empty -> the clone is usable
    await svc.close()


# (d) DELETE: clone an extra type, delete:{thatId} removes it
async def test_delete_removes_notetype(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_notetypes_handler(svc, hub)
    basicId = await svc.run(_basic_id)
    await handler(f"add:{basicId}:Temp")
    tempId = await svc.run(lambda col: col.models.by_name("Temp")["id"])
    await handler(f"delete:{tempId}")
    assert await svc.run(lambda col: col.models.by_name("Temp")) is None
    assert "ankiwebReload" in _fns(hub)
    await svc.close()


# (e) delete REFUSED when only one notetype remains -> ankiwebNotetypesError, no removal
async def test_delete_refused_when_only_one(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_notetypes_handler(svc, hub)

    # Reduce the collection down to a single notetype.
    def reduce_to_one(col):
        ids = [x.id for x in col.models.all_names_and_ids()]
        keep = col.models.by_name("Basic")["id"]
        for i in ids:
            if i != keep:
                col.models.remove(i)
        return keep

    keep = await svc.run(reduce_to_one)
    assert await svc.run(lambda col: len(col.models.all_names_and_ids())) == 1

    await handler(f"delete:{keep}")
    assert "ankiwebNotetypesError" in _fns(hub)
    assert "ankiwebReload" not in _fns(hub)
    # still present
    assert await svc.run(lambda col: col.models.get(keep)) is not None
    await svc.close()


# (f) the page lists the note counts
async def test_page_lists_note_counts(tmp_path: Path):
    svc = await _svc(tmp_path)

    def add_two_basic(col):
        did = col.decks.id("Default")
        for i in range(2):
            n = col.new_note(col.models.by_name("Basic"))
            n.fields[0] = f"q{i}"
            col.add_note(n, did)

    await svc.run(add_two_basic)
    from ankiweb.screens.notetypes import render_notetypes_html
    html = await svc.run(render_notetypes_html)
    assert "2 notes" in html or ">2<" in html
    await svc.close()
