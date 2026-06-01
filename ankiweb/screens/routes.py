from __future__ import annotations
from fastapi import APIRouter, UploadFile
from fastapi.responses import HTMLResponse

_MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
             "image/webp": ".webp", "image/svg+xml": ".svg", "image/bmp": ".bmp"}
from ankiweb.screens.page import render_page
from ankiweb.screens.deckbrowser import render_deckbrowser_html, make_deckbrowser_handler
from ankiweb.screens.overview import render_overview_html, make_overview_handler
from ankiweb.screens.reviewer import reviewer_page_body, make_reviewer_handler
from ankiweb.screens.browser import render_browser_html, make_browser_handler
from ankiweb.screens.editor import editor_page_body, make_editor_handler
from ankiweb.screens.add import render_add_html, make_add_handler
from ankiweb.screens.custom_study import render_custom_study_html, make_custom_study_handler


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

    @router.get("/custom-study", response_class=HTMLResponse)
    async def custom_study_page():
        service = get_service()
        body = await service.run(render_custom_study_html)
        return HTMLResponse(render_page("customstudy", body))

    @router.get("/reviewer", response_class=HTMLResponse)
    async def reviewer_page():
        return HTMLResponse(render_page(
            "reviewer",
            reviewer_page_body(),
            ["css/reviewer.css"],
            ["js/vendor/jquery.min.js", "js/mathjax.js",
             "js/vendor/mathjax/tex-chtml-full.js", "js/reviewer.js"],
        ))

    @router.get("/browse", response_class=HTMLResponse)
    async def browse_page():
        service = get_service()
        body = await service.run(render_browser_html)
        return HTMLResponse(render_page("browser", body))

    @router.get("/edit", response_class=HTMLResponse)
    async def edit_page(nid: int):
        return HTMLResponse(render_page(
            "editor", editor_page_body(nid),
            ["css/editor.css", "css/editable.css"],
            ["js/mathjax.js", "js/editor.js"]))

    @router.get("/add", response_class=HTMLResponse)
    async def add_page():
        service = get_service()
        body = await service.run(render_add_html)
        return HTMLResponse(render_page(
            "add", body, ["css/editor.css", "css/editable.css"],
            ["js/mathjax.js", "js/editor.js"]))

    @router.post("/upload_media")
    async def upload_media(file: UploadFile):
        data = await file.read()
        base = (file.filename or "paste").rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or "paste"
        if "." not in base:
            base += _MIME_EXT.get(file.content_type or "", ".png")
        fname = await get_service().run(lambda col: col.media.write_data(base, data))
        return {"filename": fname}

    return router


def register_screen_handlers(service, hub) -> None:
    hub.set_handler("deckbrowser", make_deckbrowser_handler(service, hub))
    hub.set_handler("overview", make_overview_handler(service, hub))
    hub.set_handler("customstudy", make_custom_study_handler(service, hub))

    hub.set_handler("reviewer", make_reviewer_handler(service, hub))
    hub.set_handler("browser", make_browser_handler(service, hub))
    hub.set_handler("editor", make_editor_handler(service, hub))
    hub.set_handler("add", make_add_handler(service, hub))
