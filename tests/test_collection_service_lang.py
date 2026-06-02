from pathlib import Path
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService


async def test_open_localizes_collection_zh(tmp_path: Path):
    svc = CollectionService(Settings(collection_path=tmp_path / "c.anki2", lang="zh-CN"))
    await svc.open()
    try:
        add = await svc.run(lambda col: col.tr.actions_add())
        assert add == "添加"
        # The frontend bundle is served from the same localized backend.
        bundle = await svc.backend_raw("i18n_resources", b"")
        assert len(bundle) > 0
    finally:
        await svc.close()


async def test_open_defaults_to_english(tmp_path: Path):
    svc = CollectionService(Settings(collection_path=tmp_path / "c.anki2"))  # lang=""
    await svc.open()
    try:
        add = await svc.run(lambda col: col.tr.actions_add())
        assert add == "Add"
    finally:
        await svc.close()
