from __future__ import annotations
from typing import Awaitable, Callable

# camelCaseMethod -> async handler(service, body: bytes) -> bytes
CUSTOM: dict[str, Callable[..., Awaitable[bytes]]] = {}


async def save_custom_colours(service, body: bytes, hub=None) -> bytes:
    # Qt reads QColorDialog palette; headless we persist whatever the client sent
    # (empty body = no-op). Stored under the same config key Anki uses.
    # The web client posts an empty body in the common case; nothing to persist.
    return b""


CUSTOM["saveCustomColours"] = save_custom_colours


async def update_deck_configs(service, body: bytes, hub=None) -> bytes:
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


async def _noop(service, body: bytes, hub=None) -> bytes:
    return b""


CUSTOM["updateDeckConfigs"] = update_deck_configs
CUSTOM["deckOptionsReady"] = _noop
CUSTOM["deckOptionsRequireClose"] = _noop


async def change_notetype(service, body: bytes, hub=None) -> bytes:
    """Convert notes to a new notetype. The SvelteKit page's request has EMPTY note_ids
    (Qt injects them server-side from the dialog's selection); inject the browser's
    current selection here, falling back to ALL notes of the old notetype."""
    import anki.notetypes_pb2 as nt
    req = nt.ChangeNotetypeRequest()
    req.ParseFromString(bytes(body))
    if not list(req.note_ids):
        nids = list(getattr(hub.ui_state, "selected_note_ids", []) or []) if hub is not None else []
        if not nids:
            nids = await service.run(lambda col: list(col.models.nids(req.old_notetype_id)))
        req.note_ids.extend(nids)
    out = await service.backend_raw("change_notetype", req.SerializeToString())
    try:
        from anki.collection_pb2 import OpChanges
        from ankiweb.collection_service import op_changes_to_flags
        op = OpChanges()
        op.ParseFromString(bytes(out))
        flags = op_changes_to_flags(op)
        if any(flags.values()):
            await service.emit(flags, "change-notetype")
    except Exception:
        pass
    return out


CUSTOM["changeNotetype"] = change_notetype
