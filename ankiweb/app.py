from __future__ import annotations
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="ankiweb")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app
