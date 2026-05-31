from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import Response, PlainTextResponse
from ankiweb.anki_rpc.passthrough import PASSTHROUGH, camel_to_snake

BINARY = "application/binary"


def build_router(get_service) -> APIRouter:
    router = APIRouter()

    @router.post("/_anki/{method}")
    async def rpc(method: str, request: Request) -> Response:
        # CSRF/opaque-request guard (mediasrv.py:753-756)
        if request.headers.get("content-type") != BINARY:
            return PlainTextResponse("bad content type", status_code=403)
        body = await request.body()
        service = get_service()
        snake = camel_to_snake(method)

        from ankiweb.anki_rpc.handlers import CUSTOM
        try:
            if method in CUSTOM:
                out = await CUSTOM[method](service, body)
            elif snake in PASSTHROUGH:
                out = await service.backend_raw(snake, body)
            else:
                return PlainTextResponse("not found", status_code=404)
        except Exception as exc:  # mediasrv returns 500 + str(exc)
            return PlainTextResponse(str(exc), status_code=500)

        if not out:
            return Response(status_code=204)
        return Response(content=bytes(out), media_type=BINARY)

    return router
