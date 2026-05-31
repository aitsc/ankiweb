import asyncio
import pytest
from pathlib import Path
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService


@pytest.fixture
async def service(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    svc = CollectionService(settings)
    await svc.open()
    yield svc
    await svc.close()


async def test_run_executes_on_collection(service):
    count = await service.run(lambda col: col.note_count())
    assert count == 0


async def test_run_serializes_access(service):
    # Many concurrent ops must not corrupt python-side state.
    async def add(i):
        def fn(col):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"] = str(i)
            col.add_note(n, col.decks.id("Default"))
        await service.run(fn)
    await asyncio.gather(*[add(i) for i in range(20)])
    total = await service.run(lambda col: col.note_count())
    assert total == 20


async def test_backend_raw_passthrough(service):
    # i18n_resources accepts an empty request and returns non-empty JSON bytes.
    out = await service.backend_raw("i18n_resources", b"")
    assert isinstance(out, (bytes, bytearray))
    assert len(out) > 0


async def test_opchanges_bus_notifies_subscribers(service):
    seen = []
    service.subscribe(lambda changes, initiator: seen.append((changes, initiator)))
    await service.emit(changes={"note": True}, initiator="t1")
    assert seen == [({"note": True}, "t1")]


def test_op_changes_to_flags():
    from ankiweb.collection_service import op_changes_to_flags
    from anki.collection import Collection
    import tempfile, os
    col = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))
    try:
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "x"
        res = col.add_note(n, col.decks.id("Default"))  # OpChangesWithCount
        flags = op_changes_to_flags(res.changes)
        assert flags["note"] is True
        assert flags["card"] is True
        assert isinstance(flags.get("study_queues"), bool)
    finally:
        col.close()


async def test_run_op_emits_flags(service):
    seen = []
    service.subscribe(lambda flags, initiator: seen.append((flags, initiator)))

    def add(col):
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "y"
        return col.add_note(n, col.decks.id("Default"))

    res = await service.run_op(add, initiator="deckbrowser")
    assert res.count == 1                      # OpChangesWithCount passthrough return
    assert len(seen) == 1
    flags, initiator = seen[0]
    assert initiator == "deckbrowser"
    assert flags["note"] is True
