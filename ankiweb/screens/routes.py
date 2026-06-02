from __future__ import annotations
import os
import tempfile
from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask

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
from ankiweb.screens.about import render_about_html
from ankiweb.screens.filtered_deck import render_filtered_deck_html, make_filtered_deck_handler
from ankiweb.screens.export import render_export_html
from ankiweb.screens.preferences import render_preferences_html, make_preferences_handler
from ankiweb.screens.preview import render_preview_html
from ankiweb.screens.fields import render_fields_html, make_fields_handler
from ankiweb.screens.card_layout import render_card_layout_html, make_card_layout_handler


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

    @router.get("/filtered-deck", response_class=HTMLResponse)
    async def filtered_deck_new_page():
        service = get_service()
        body = await service.run(lambda col: render_filtered_deck_html(col, 0))
        return HTMLResponse(render_page("filtereddeck", body))

    @router.get("/filtered-deck/{deck_id}", response_class=HTMLResponse)
    async def filtered_deck_edit_page(deck_id: int):
        service = get_service()
        body = await service.run(lambda col: render_filtered_deck_html(col, deck_id))
        return HTMLResponse(render_page("filtereddeck", body))

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
    async def browse_page(q: str = ""):
        service = get_service()
        body = await service.run(lambda col: render_browser_html(col, q))
        return HTMLResponse(render_page("browser", body))

    @router.get("/preferences", response_class=HTMLResponse)
    async def preferences_page():
        service = get_service()
        body = await service.run(render_preferences_html)
        return HTMLResponse(render_page("preferences", body))

    @router.get("/fields/{ntid}", response_class=HTMLResponse)
    async def fields_page(ntid: int):
        service = get_service()
        body = await service.run(lambda col: render_fields_html(col, ntid))
        return HTMLResponse(render_page("fields", body))

    @router.get("/card-layout/{ntid}", response_class=HTMLResponse)
    async def card_layout_page(ntid: int):
        service = get_service()
        body = await service.run(lambda col: render_card_layout_html(col, ntid))
        return HTMLResponse(render_page("cardlayout", body))

    @router.get("/about", response_class=HTMLResponse)
    async def about_page():
        # AGPL §13 Corresponding-Source offer (settings carries the source URL).
        return HTMLResponse(render_page("about", render_about_html(get_service().settings)))

    @router.get("/edit", response_class=HTMLResponse)
    async def edit_page(nid: int):
        # No global toolbar: /edit is embedded as the Browser's detail iframe.
        return HTMLResponse(render_page(
            "editor", editor_page_body(nid),
            ["css/editor.css", "css/editable.css"],
            ["js/mathjax.js", "js/editor.js"], toolbar=False))

    @router.get("/preview/{nid}", response_class=HTMLResponse)
    async def preview_page(nid: int):
        service = get_service()
        body = await service.run(lambda col: render_preview_html(col, nid))
        return HTMLResponse(render_page("preview", body))

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

    @router.get("/export", response_class=HTMLResponse)
    async def export_page():
        service = get_service()
        body = await service.run(render_export_html)
        return HTMLResponse(render_page("export", body))

    @router.post("/export")
    async def export_post(
        target: str = Form("all"),
        fmt: str = Form("apkg"),
        with_scheduling: bool = Form(False),
        with_media: bool = Form(False),
        with_deck_configs: bool = Form(False),
        legacy: bool = Form(False),
        with_html: bool = Form(False),
        with_tags: bool = Form(False),
        with_deck: bool = Form(False),
        with_notetype: bool = Form(False),
        with_guid: bool = Form(False),
    ):
        import anki.import_export_pb2 as ie
        service = get_service()

        def make_limit():
            lim = ie.ExportLimit()
            if target == "all":
                lim.whole_collection.SetInParent()
            else:
                lim.deck_id = int(target)
            return lim

        suffix = {"apkg": ".apkg", "colpkg": ".colpkg",
                  "notes_csv": ".csv", "cards_csv": ".csv"}.get(fmt, ".apkg")
        fd, out = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            if fmt == "apkg":
                opts = ie.ExportAnkiPackageOptions(
                    with_scheduling=with_scheduling, with_media=with_media,
                    with_deck_configs=with_deck_configs, legacy=legacy)
                lim = make_limit()
                await service.run(lambda col: col.export_anki_package(
                    out_path=out, options=opts, limit=lim))
                filename, media = "export.apkg", "application/octet-stream"
            elif fmt == "colpkg":
                await service.run(lambda col: col.export_collection_package(
                    out, with_media, legacy))
                await service.reopen()  # export_collection_package closed the collection
                filename, media = "collection.colpkg", "application/octet-stream"
            elif fmt == "notes_csv":
                lim = make_limit()
                await service.run(lambda col: col.export_note_csv(
                    out_path=out, limit=lim, with_html=with_html, with_tags=with_tags,
                    with_deck=with_deck, with_notetype=with_notetype, with_guid=with_guid))
                filename, media = "notes.csv", "text/csv"
            elif fmt == "cards_csv":
                lim = make_limit()
                await service.run(lambda col: col.export_card_csv(
                    out_path=out, limit=lim, with_html=with_html))
                filename, media = "cards.csv", "text/csv"
            else:
                os.remove(out)
                return HTMLResponse("unknown export format", status_code=400)
        except Exception as exc:
            try:
                os.remove(out)
            except OSError:
                pass
            body = await service.run(render_export_html)
            return HTMLResponse(render_page(
                "export", f"<div style='color:#c00'>Export failed: {exc}</div>" + body))
        return FileResponse(out, media_type=media, filename=filename,
                            background=BackgroundTask(os.remove, out))

    @router.post("/image-occlusion/upload")
    async def image_occlusion_upload(file: UploadFile):
        from fastapi.responses import JSONResponse
        from ankiweb import import_tmp
        service = get_service()
        import_tmp.io_gc(service.settings)
        name = (file.filename or "").lower()
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".avif"):
            return JSONResponse({"error": f"unsupported image type: {ext or '(none)'}"}, status_code=400)
        dest = import_tmp.io_allocate(service.settings, ext)
        dest.write_bytes(await file.read())
        await service.run(lambda col: col.add_image_occlusion_notetype())  # idempotent ensure
        return {"path": str(dest)}

    @router.post("/import/upload")
    async def import_upload(file: UploadFile):
        from fastapi.responses import JSONResponse
        from ankiweb import import_tmp
        service = get_service()
        import_tmp.gc(service.settings)  # lazy TTL sweep
        name = (file.filename or "").lower()
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        routes = {".csv": "import-csv", ".tsv": "import-csv", ".txt": "import-csv",
                  ".apkg": "import-anki-package", ".zip": "import-anki-package"}
        route = routes.get(ext)
        if route is None:
            return JSONResponse({"error": f"unsupported file type: {ext or '(none)'}"}, status_code=400)
        dest = import_tmp.allocate(service.settings, ext)
        dest.write_bytes(await file.read())
        return {"route": route, "path": str(dest)}

    return router


def register_screen_handlers(service, hub) -> None:
    hub.set_handler("deckbrowser", make_deckbrowser_handler(service, hub))
    hub.set_handler("overview", make_overview_handler(service, hub))
    hub.set_handler("customstudy", make_custom_study_handler(service, hub))
    hub.set_handler("filtereddeck", make_filtered_deck_handler(service, hub))
    hub.set_handler("preferences", make_preferences_handler(service, hub))
    hub.set_handler("fields", make_fields_handler(service, hub))
    hub.set_handler("cardlayout", make_card_layout_handler(service, hub))

    hub.set_handler("reviewer", make_reviewer_handler(service, hub))
    hub.set_handler("browser", make_browser_handler(service, hub))
    hub.set_handler("editor", make_editor_handler(service, hub))
    hub.set_handler("add", make_add_handler(service, hub))
