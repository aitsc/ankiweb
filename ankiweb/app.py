from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = CollectionService(settings)
        await service.open()
        app.state.settings = settings
        app.state.service = service
        try:
            yield
        finally:
            await service.close()

    app = FastAPI(title="ankiweb", lifespan=lifespan)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    from ankiweb.assets import build_router as build_assets_router
    app.include_router(build_assets_router(settings.assets_dir))

    from ankiweb.assets import build_media_router
    app.include_router(build_media_router(lambda: app.state.service))

    return app
