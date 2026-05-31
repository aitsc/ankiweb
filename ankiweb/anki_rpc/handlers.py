from __future__ import annotations
from typing import Awaitable, Callable

# camelCaseMethod -> async handler(service, body: bytes) -> bytes
CUSTOM: dict[str, Callable[..., Awaitable[bytes]]] = {}


async def save_custom_colours(service, body: bytes) -> bytes:
    # Qt reads QColorDialog palette; headless we persist whatever the client sent
    # (empty body = no-op). Stored under the same config key Anki uses.
    # The web client posts an empty body in the common case; nothing to persist.
    return b""


CUSTOM["saveCustomColours"] = save_custom_colours
