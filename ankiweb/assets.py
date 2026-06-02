from __future__ import annotations
from pathlib import Path
from typing import Callable
from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

# Injected into the served SvelteKit shell so the SPA's bridgeCommand("browserSearch:<q>")
# (e.g. graphs count-links) opens ankiweb's browser instead of being a no-op. The SPA has no
# pycmd host otherwise; this defines a minimal one before the app modules load. Other bridge
# commands are intentionally ignored (same as before).
_SPA_BRIDGE = (
    "<script>window.pycmd=window.bridgeCommand=function(c){try{"
    "if(typeof c==='string'&&c.indexOf('browserSearch:')===0){"
    "location.href='/browse?q='+encodeURIComponent(c.slice(14));}}catch(e){}};</script>"
)

# subset of mediasrv _mime_for_path (mediasrv.py:171-210)
MIME = {
    ".css": "text/css", ".js": "application/javascript", ".mjs": "application/javascript",
    ".html": "text/html", ".svg": "image/svg+xml", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".ico": "image/x-icon", ".json": "application/json", ".woff": "font/woff",
    ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf", ".map": "application/json",
    ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".oga": "audio/ogg",
    ".opus": "audio/opus", ".wav": "audio/wav", ".flac": "audio/flac",
    ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
}
SVELTEKIT_PAGES = {"graphs", "congrats", "card-info", "change-notetype", "deck-options",
                   "import-anki-package", "import-csv", "import-page", "image-occlusion"}


# vendored binary assets that are content-stable across the pinned anki version: cache hard.
# (fonts are the big one — MathJax CHTML lazy-loads ~dozens of woff glyph files per render.)
_STATIC_ASSET_EXTS = {"woff", "woff2", "ttf", "otf", "eot",
                      "svg", "png", "jpg", "jpeg", "gif", "webp", "ico"}


def _mime(path: str) -> str:
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return MIME.get(ext, "application/octet-stream")


def _resolve(rel: str) -> str:
    """Replicate mediasrv _extract_internal_request rewrites for the _anki/ namespace."""
    first = rel.split("/", 1)[0]
    if first in SVELTEKIT_PAGES:
        return f"sveltekit/{rel}"
    if rel.startswith("_app/"):
        return f"sveltekit/{rel}"
    if "/" not in rel:  # bare file at /_anki/<file>
        if rel.endswith(".css"):
            return f"css/{rel}"
        if rel.endswith(".js"):
            stem = rel[:-3].removesuffix(".min")  # jquery.min -> jquery
            if stem in ("jquery", "jquery-ui", "plot"):
                return f"js/vendor/{rel}"
            return f"js/{rel}"
    return rel


def build_router(assets_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/_anki/{path:path}")
    def serve(path: str, request: Request) -> Response:
        rel = _resolve(path)
        target = (assets_dir / rel).resolve()
        try:
            target.relative_to(assets_dir.resolve())
        except ValueError:
            return PlainTextResponse("forbidden", status_code=403)

        if not target.is_file():
            # SvelteKit SPA fallback for non-immutable sveltekit paths
            if rel.startswith("sveltekit/") and "immutable" not in rel:
                fallback = assets_dir / "sveltekit" / "index.html"
                if fallback.is_file():
                    return FileResponse(fallback, media_type="text/html")
            return PlainTextResponse("not found", status_code=404)

        headers = {}
        ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
        if "immutable" in rel:
            headers["Cache-Control"] = "max-age=31536000"
        elif ext in _STATIC_ASSET_EXTS:
            # Vendored, version-pinned, content-stable binaries (esp. MathJax's lazily-loaded
            # CHTML glyph fonts). Without a cache header the browser re-downloads them FULLY on
            # every card render -> slow card switches. They never change at runtime.
            headers["Cache-Control"] = "max-age=31536000"
        elif rel.endswith(".css"):
            headers["Cache-Control"] = "max-age=10"
        elif rel.endswith(".js"):
            # js can change on an anki version re-vendor -> revalidate via etag (304), don't pin
            headers["Cache-Control"] = "max-age=0"
        return FileResponse(target, media_type=_mime(rel), headers=headers)

    return router


def build_sveltekit_router(assets_dir: Path) -> APIRouter:
    """Serve the vendored SvelteKit SPA at ROOT paths (its index.html imports /_app/...
    and client-routes by location.pathname). E2/E3 add more page routes here."""
    router = APIRouter()
    index = assets_dir / "sveltekit" / "index.html"

    def _shell_with_bridge() -> str:
        html = index.read_text(encoding="utf-8")
        return html.replace("<head>", "<head>" + _SPA_BRIDGE, 1)

    @router.get("/graphs")
    def graphs_page() -> Response:
        # served with the browserSearch bridge so the stats count-links open /browse
        return HTMLResponse(_shell_with_bridge())

    @router.get("/deck-options/{deck_id}")
    def deck_options_page(deck_id: str) -> Response:
        return FileResponse(index, media_type="text/html")

    @router.get("/change-notetype/{ids:path}")
    def change_notetype_page(ids: str) -> Response:
        return FileResponse(index, media_type="text/html")

    @router.get("/card-info/{ids:path}")
    def card_info_page(ids: str) -> Response:
        # SvelteKit route nodes: /card-info/[cardId] and /card-info/[cardId]/[previousId].
        # Bundle is vendored; card_stats / get_review_logs are already PASSTHROUGH RPCs.
        return FileResponse(index, media_type="text/html")

    @router.get("/import-csv/{path:path}")
    def import_csv_page(path: str) -> Response:
        return FileResponse(index, media_type="text/html")

    @router.get("/import-anki-package/{path:path}")
    def import_anki_package_page(path: str) -> Response:
        return FileResponse(index, media_type="text/html")

    @router.get("/image-occlusion/{path:path}")
    def image_occlusion_page(path: str) -> Response:
        return FileResponse(index, media_type="text/html")

    @router.get("/_app/{path:path}")
    def app_asset(path: str) -> Response:
        rel = _resolve("_app/" + path)
        target = (assets_dir / rel).resolve()
        try:
            target.relative_to(assets_dir.resolve())
        except ValueError:
            return PlainTextResponse("forbidden", status_code=403)
        if not target.is_file():
            return PlainTextResponse("not found", status_code=404)
        headers = {"Cache-Control": "max-age=31536000"} if "immutable" in rel else {}
        return FileResponse(target, media_type=_mime(rel), headers=headers)

    @router.get("/favicon.ico")
    def favicon() -> Response:
        f = assets_dir / "imgs" / "favicon.ico"
        if f.is_file():
            return FileResponse(f, media_type="image/x-icon")
        return Response(status_code=204)

    return router


def build_media_router(get_service: Callable) -> APIRouter:
    router = APIRouter()

    @router.get("/{path:path}")
    async def serve_media(path: str) -> Response:
        service = get_service()  # lazy: service is created in lifespan, not import time
        media_dir = Path(await service.run(lambda col: col.media.dir())).resolve()
        target = (media_dir / path).resolve()
        try:
            target.relative_to(media_dir)
        except ValueError:
            return PlainTextResponse("forbidden", status_code=403)
        if not target.is_file():
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(target, media_type=_mime(path))

    return router
