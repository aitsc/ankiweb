from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from ankiweb.screens.page import render_page
from ankiweb.screens.deckbrowser import render_deckbrowser_html, make_deckbrowser_handler
from ankiweb.screens.overview import render_overview_html, make_overview_handler
from ankiweb.screens.reviewer import reviewer_page_body, make_reviewer_handler


def build_screen_router(get_service) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    @router.get("/deckbrowser", response_class=HTMLResponse)
    async def deckbrowser_page():
        service = get_service()
        body = await service.run(render_deckbrowser_html)
        return HTMLResponse(render_page("deckbrowser", body, ["css/deckbrowser.css"]))

    @router.get("/overview", response_class=HTMLResponse)
    async def overview_page():
        service = get_service()
        body = await service.run(render_overview_html)
        return HTMLResponse(render_page("overview", body, ["css/overview.css"]))

    @router.get("/reviewer", response_class=HTMLResponse)
    async def reviewer_page():
        return HTMLResponse(render_page(
            "reviewer",
            reviewer_page_body(),
            ["css/reviewer.css"],
            ["js/vendor/jquery.min.js", "js/mathjax.js",
             "js/vendor/mathjax/tex-chtml-full.js", "js/reviewer.js"],
        ))

    return router


def register_screen_handlers(service, hub) -> None:
    hub.set_handler("deckbrowser", make_deckbrowser_handler(service, hub))
    hub.set_handler("overview", make_overview_handler(service, hub))

    hub.set_handler("reviewer", make_reviewer_handler(service, hub))
