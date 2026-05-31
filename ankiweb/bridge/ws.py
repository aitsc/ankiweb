from __future__ import annotations
from fastapi import APIRouter, WebSocket, WebSocketDisconnect


def build_router(get_hub) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket, context: str = "default"):
        # BaseHTTPMiddleware host_guard does NOT cover WS upgrades — check here too.
        host = websocket.headers.get("host", "")
        if not (host.startswith(("127.0.0.1:", "localhost:", "[::1]:"))
                or host in ("127.0.0.1", "localhost", "testserver")):
            await websocket.close(code=1008)
            return
        hub = get_hub()
        await websocket.accept()
        hub.register(context, websocket)
        try:
            while True:
                msg = await websocket.receive_json()
                mtype = msg.get("type")
                if mtype == "cmd":
                    result = await hub.dispatch_cmd(context, msg.get("arg", ""))
                    if msg.get("id") is not None:
                        await websocket.send_json(
                            {"type": "result", "id": msg["id"], "value": result})
                elif mtype == "result":
                    hub.resolve(msg["id"], msg.get("value"))
                elif mtype == "ready":
                    pass  # domDone handshake; per-screen logic handles buffering
        except WebSocketDisconnect:
            pass
        finally:
            hub.unregister(context, websocket)

    return router
