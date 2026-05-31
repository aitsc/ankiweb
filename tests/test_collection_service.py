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
