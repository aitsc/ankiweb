import inspect
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.app import create_app
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.ankiconnect.runtime import Runtime
from ankiweb.ankiconnect.actions.decks import create_deck
from ankiweb.screens.deckbrowser import render_deckbrowser_html


async def test_both_layers_share_one_service(tmp_path: Path):
    # Prove the API action layer and the web renderer operate on the SAME collection,
    # all on ONE event loop (the test's). NOTE: do NOT use two TestClients sharing one
    # service — each TestClient runs on its own loop and the service's asyncio.Lock would
    # bind to the first and raise on the second. The production dual-server path is fine
    # because both uvicorn servers run in one asyncio.gather loop (see __main__.py).
    settings = Settings(collection_path=tmp_path / "c.anki2")
    service = CollectionService(settings)
    await service.open()
    try:
        rt = Runtime(service=service, config=AnkiConnectConfig())
        did = await create_deck(rt, deck="Shared")          # AnkiConnect action layer
        assert isinstance(did, int)
        html = await service.run(render_deckbrowser_html)    # web UI renderer, same service
        assert "Shared" in html
    finally:
        await service.close()


def test_create_app_accepts_injection_kwargs():
    params = inspect.signature(create_app).parameters
    assert "service" in params and "hub" in params


def test_create_app_standalone_still_opens_own_service(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as w:
        assert w.get("/healthz").json() == {"ok": True}
