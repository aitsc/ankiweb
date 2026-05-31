from __future__ import annotations
import asyncio
import uvicorn
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.bridge.hub import BridgeHub
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.app import create_app
from ankiweb.ankiconnect.app import create_ankiconnect_app


async def _serve() -> None:
    settings = Settings.from_env()
    ac_config = AnkiConnectConfig.load(settings.collection_path.parent / "ankiconnect.json")
    service = CollectionService(settings)
    await service.open()
    hub = BridgeHub()
    web = create_app(settings, service=service, hub=hub)
    api = create_ankiconnect_app(settings, service=service, config=ac_config, hub=hub)
    web_server = uvicorn.Server(uvicorn.Config(web, host=settings.host, port=settings.port,
                                               log_level="info"))
    api_server = uvicorn.Server(uvicorn.Config(api, host=ac_config.bind_address,
                                               port=ac_config.bind_port, log_level="info"))
    try:
        await asyncio.gather(web_server.serve(), api_server.serve())
    finally:
        await service.close()


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
