from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from ankiweb.screens.page import render_page
from ankiweb.screens.deckbrowser import render_deckbrowser_html, make_deckbrowser_handler


def build_screen_router(get_service) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    @router.get("/deckbrowser", response_class=HTMLResponse)
    async def deckbrowser_page():
        service = get_service()
        body = await service.run(render_deckbrowser_html)
        return HTMLResponse(render_page("deckbrowser", body, ["css/deckbrowser.css"]))

    return router


def register_screen_handlers(service, hub) -> None:
    hub.set_handler("deckbrowser", make_deckbrowser_handler(service, hub))
