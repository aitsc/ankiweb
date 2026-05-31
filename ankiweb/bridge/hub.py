from __future__ import annotations
import asyncio
from typing import Any, Awaitable, Callable
from ankiweb.bridge.ui_state import UiState


class BridgeHub:
    """Tracks WebSocket connections per UI context and pushes messages to them."""

    def __init__(self) -> None:
        self._conns: dict[str, list] = {}
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        # ctx -> async handler(arg:str) -> json-serializable result
        self._handlers: dict[str, Callable[[str], Awaitable[Any]]] = {}
        self.ui_state = UiState()

    def register(self, ctx: str, ws) -> None:
        self._conns.setdefault(ctx, []).append(ws)

    def unregister(self, ctx: str, ws) -> None:
        if ctx in self._conns and ws in self._conns[ctx]:
            self._conns[ctx].remove(ws)

    def set_handler(self, ctx: str, handler: Callable[[str], Awaitable[Any]]) -> None:
        self._handlers[ctx] = handler

    async def _send_all(self, ctx: str, msg: dict) -> None:
        for ws in list(self._conns.get(ctx, [])):
            await ws.send_json(msg)

    async def push_call(self, ctx: str, fn: str, args: list) -> None:
        await self._send_all(ctx, {"type": "call", "id": None, "fn": fn, "args": args})

    async def push_eval(self, ctx: str, js: str) -> None:
        await self._send_all(ctx, {"type": "eval", "id": None, "js": js})

    async def broadcast_opchanges(self, flags: dict, initiator) -> None:
        msg = {"type": "opchanges", "flags": flags, "initiator": initiator}
        for ctx in list(self._conns):
            await self._send_all(ctx, msg)

    # --- request/response (evalWithCallback / cmd callback) ---
    def _alloc(self) -> tuple[int, asyncio.Future]:
        self._next_id += 1
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[self._next_id] = fut
        return self._next_id, fut

    def resolve(self, msg_id: int, value: Any) -> None:
        fut = self._pending.pop(msg_id, None)
        if fut and not fut.done():
            fut.set_result(value)

    async def eval_with_callback(self, ctx: str, js: str) -> Any:
        msg_id, fut = self._alloc()
        await self._send_all(ctx, {"type": "eval", "id": msg_id, "js": js})
        return await fut

    async def dispatch_cmd(self, ctx: str, arg: str) -> Any:
        self.ui_state.current_screen = ctx
        handler = self._handlers.get(ctx)
        if handler is None:
            return None
        return await handler(arg)
