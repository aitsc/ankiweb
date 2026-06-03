from __future__ import annotations
import asyncio
import uvicorn
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.bridge.hub import BridgeHub
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.app import create_app
from ankiweb.ankiconnect.app import create_ankiconnect_app
from ankiweb.notifier import NotifierState, DeckNotifier, snapshot


async def _serve() -> None:
    settings = Settings.from_env()
    ac_config = AnkiConnectConfig.load(settings.collection_path.parent / "ankiconnect.json")
    service = CollectionService(settings)
    await service.open()
    hub = BridgeHub()
    notifier_state = NotifierState(settings.collection_path.parent / "notify.json")
    web = create_app(settings, service=service, hub=hub, notifier=notifier_state)
    api = create_ankiconnect_app(settings, service=service, config=ac_config, hub=hub)
    web_server = uvicorn.Server(uvicorn.Config(web, host=settings.host, port=settings.port,
                                               log_level="info"))
    api_server = uvicorn.Server(uvicorn.Config(api, host=ac_config.bind_address,
                                               port=ac_config.bind_port, log_level="info"))
    # Background deck-learnability push notifier (idle unless configured via the Extras menu).
    notifier = DeckNotifier(notifier_state, fetch=lambda: service.run(snapshot))
    notifier_task = asyncio.create_task(notifier.run())
    try:
        await asyncio.gather(web_server.serve(), api_server.serve())
    finally:
        notifier_task.cancel()
        try:
            await notifier_task
        except asyncio.CancelledError:
            pass
        await service.close()


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
