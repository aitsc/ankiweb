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


async def update_deck_configs(service, body: bytes) -> bytes:
    out = await service.backend_raw("update_deck_configs", body)
    try:
        from anki.collection_pb2 import OpChanges
        from ankiweb.collection_service import op_changes_to_flags
        op = OpChanges()
        op.ParseFromString(bytes(out))
        flags = op_changes_to_flags(op)
        if any(flags.values()):
            await service.emit(flags, "deck-options")
    except Exception:
        pass
    return out


async def _noop(service, body: bytes) -> bytes:
    return b""


CUSTOM["updateDeckConfigs"] = update_deck_configs
CUSTOM["deckOptionsReady"] = _noop
CUSTOM["deckOptionsRequireClose"] = _noop
