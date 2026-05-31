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
        from ankiweb.bridge.hub import BridgeHub
        hub = BridgeHub()
        app.state.hub = hub
        service.subscribe(lambda flags, initiator:
                          hub.broadcast_opchanges(flags, initiator))
        try:
            yield
        finally:
            await service.close()

    app = FastAPI(title="ankiweb", lifespan=lifespan)

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import PlainTextResponse as _PTR

    async def host_guard(request, call_next):
        host = request.headers.get("host", "")
        if not (host.startswith("127.0.0.1:") or host.startswith("localhost:")
                or host.startswith("[::1]:") or host in ("127.0.0.1", "localhost")
                or host == "testserver"):
            return _PTR("forbidden host", status_code=403)
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=host_guard)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    from ankiweb.assets import build_router as build_assets_router
    app.include_router(build_assets_router(settings.assets_dir))

    from ankiweb.anki_rpc import build_router as build_rpc_router
    app.include_router(build_rpc_router(lambda: app.state.service))

    from ankiweb.bridge.ws import build_router as build_ws_router
    app.include_router(build_ws_router(lambda: app.state.hub))

    from fastapi.staticfiles import StaticFiles
    static_dir = settings.shell_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/shell/static", StaticFiles(directory=str(static_dir), check_dir=False), name="shell")

    from ankiweb.assets import build_media_router
    app.include_router(build_media_router(lambda: app.state.service))

    return app
