from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.bridge.hub import BridgeHub
from ankiweb.assets import build_router as build_assets_router, build_media_router, build_sveltekit_router
from ankiweb.anki_rpc import build_router as build_rpc_router
from ankiweb.bridge.ws import build_router as build_ws_router
from ankiweb.screens.routes import build_screen_router, register_screen_handlers

_ALLOWED_HOST_PREFIXES = ("127.0.0.1:", "localhost:", "[::1]:")
_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "testserver")


def create_app(settings: Settings | None = None, service: CollectionService | None = None,
               hub: BridgeHub | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    owns = service is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = service
        if owns:
            svc = CollectionService(settings)
            await svc.open()
        h = hub if hub is not None else BridgeHub()
        svc.subscribe(lambda flags, initiator: h.broadcast_opchanges(flags, initiator))
        app.state.settings = settings
        app.state.service = svc
        app.state.hub = h
        register_screen_handlers(svc, h)
        try:
            yield
        finally:
            if owns:
                await svc.close()

    app = FastAPI(title="ankiweb", lifespan=lifespan)

    async def host_guard(request, call_next):
        host = request.headers.get("host", "")
        if not (host.startswith(_ALLOWED_HOST_PREFIXES) or host in _ALLOWED_HOSTS):
            return PlainTextResponse("forbidden host", status_code=403)
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=host_guard)

    # --- specific routes FIRST, media catch-all LAST (Starlette matches in order) ---
    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    static_dir = settings.shell_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/shell/static", StaticFiles(directory=str(static_dir), check_dir=False), name="shell")

    app.include_router(build_assets_router(settings.assets_dir))       # GET  /_anki/{path}
    app.include_router(build_rpc_router(lambda: app.state.service, lambda: app.state.hub))    # POST /_anki/{method}
    app.include_router(build_ws_router(lambda: app.state.hub))         # WS   /ws
    app.include_router(build_screen_router(lambda: app.state.service))  # GET / and /deckbrowser
    app.include_router(build_sveltekit_router(settings.assets_dir))     # GET  /graphs, /_app/{path}, /favicon.ico
    app.include_router(build_media_router(lambda: app.state.service))  # GET  /{path} — LAST

    return app
