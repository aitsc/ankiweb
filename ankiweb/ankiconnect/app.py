from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.bridge.hub import BridgeHub
from ankiweb.ankiconnect.runtime import Runtime
from ankiweb.ankiconnect.cors import allow_origin
from ankiweb.ankiconnect.dispatch import dispatch_one
from ankiweb.ankiconnect.rest import build_actions_router
import ankiweb.ankiconnect.actions  # noqa: F401 — registers actions


def create_ankiconnect_app(
    settings: Settings | None = None,
    service: CollectionService | None = None,
    config: AnkiConnectConfig | None = None,
    hub=None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    config = config or AnkiConnectConfig()
    owns_service = service is None
    hub = hub if hub is not None else BridgeHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = service
        if owns_service:
            svc = CollectionService(settings)
            await svc.open()
        app.state.service = svc
        app.state.config = config
        app.state.hub = hub
        try:
            yield
        finally:
            if owns_service:
                await svc.close()

    app = FastAPI(title="ankiweb-ankiconnect", lifespan=lifespan)

    def _cors_headers(origin):
        allowed, header = allow_origin(origin, config.cors_origin_list)
        return allowed, {"Access-Control-Allow-Origin": header,
                         "Access-Control-Allow-Headers": "*"}

    @app.options("/")
    async def preflight(request: Request):
        _, headers = _cors_headers(request.headers.get("origin"))
        if request.headers.get("access-control-request-private-network") == "true":
            headers["Access-Control-Allow-Private-Network"] = "true"
        return Response(status_code=200, headers=headers)

    @app.get("/")
    async def probe():
        return JSONResponse({"apiVersion": "AnkiConnect v.6"})

    @app.post("/")
    async def rpc(request: Request):
        origin = request.headers.get("origin")
        allowed, headers = _cors_headers(origin)
        try:
            req = await request.json()
        except Exception:
            req = {}
        if not req:  # empty body → liveness probe
            return JSONResponse({"apiVersion": "AnkiConnect v.6"}, headers=headers)
        action_name = req.get("action") or ""
        if not allowed and action_name != "requestPermission":
            return JSONResponse({"result": None, "error": "origin not allowed"},
                                status_code=403, headers=headers)
        rt = Runtime(service=app.state.service, config=app.state.config, hub=app.state.hub)
        if action_name == "requestPermission":  # inject CORS result + origin
            req.setdefault("params", {})
            req["params"]["allowed"] = allowed
            req["params"]["origin"] = origin
        reply = await dispatch_one(rt, req)
        return JSONResponse(reply, headers=headers)

    # Additive typed surface for /docs (one POST /actions/<name> per action). The canonical
    # POST / above is the source of truth; these routes call the same dispatch_one.
    app.include_router(build_actions_router())

    return app
