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


async def _emit_import_changes(service, out: bytes) -> None:
    try:
        import anki.import_export_pb2 as ie
        from ankiweb.collection_service import op_changes_to_flags
        resp = ie.ImportResponse()
        resp.ParseFromString(bytes(out))
        flags = op_changes_to_flags(resp.changes)
        if any(flags.values()):
            await service.emit(flags, "import")
    except Exception:
        pass


async def get_csv_metadata(service, body: bytes, hub) -> bytes:
    import anki.import_export_pb2 as ie
    from ankiweb import import_tmp
    req = ie.CsvMetadataRequest()
    req.ParseFromString(bytes(body))
    if req.path and not import_tmp.is_within(service.settings, req.path):
        raise ValueError("import path not allowed")
    return await service.backend_raw("get_csv_metadata", body)


async def import_csv(service, body: bytes, hub) -> bytes:
    import anki.import_export_pb2 as ie
    from ankiweb import import_tmp
    req = ie.ImportCsvRequest()
    req.ParseFromString(bytes(body))
    if not import_tmp.is_within(service.settings, req.path):
        raise ValueError("import path not allowed")
    out = await service.backend_raw("import_csv", body)
    await _emit_import_changes(service, out)
    return out


async def import_anki_package(service, body: bytes, hub) -> bytes:
    import anki.import_export_pb2 as ie
    from ankiweb import import_tmp
    req = ie.ImportAnkiPackageRequest()
    req.ParseFromString(bytes(body))
    if not import_tmp.is_within(service.settings, req.package_path):
        raise ValueError("import path not allowed")
    out = await service.backend_raw("import_anki_package", body)
    await _emit_import_changes(service, out)
    return out


CUSTOM["getCsvMetadata"] = get_csv_metadata
CUSTOM["importCsv"] = import_csv
CUSTOM["importAnkiPackage"] = import_anki_package
CUSTOM["importDone"] = _noop


async def _emit_opchanges(service, out: bytes) -> None:
    """Parse a raw OpChanges reply and broadcast its flags (image-occlusion writes)."""
    try:
        from anki.collection_pb2 import OpChanges
        from ankiweb.collection_service import op_changes_to_flags
        op = OpChanges()
        op.ParseFromString(bytes(out))
        flags = op_changes_to_flags(op)
        if any(flags.values()):
            await service.emit(flags, "image-occlusion")
    except Exception:
        pass


async def get_image_for_occlusion(service, body: bytes, hub) -> bytes:
    import os
    import anki.image_occlusion_pb2 as iopb
    from ankiweb import import_tmp
    req = iopb.GetImageForOcclusionRequest()
    req.ParseFromString(bytes(body))
    if req.path and not import_tmp.is_within(service.settings, req.path):
        raise ValueError("image path not allowed")
    # touch-on-read: keep an in-progress drawing session's temp image fresh vs the GC
    try:
        if req.path and os.path.isfile(req.path):
            os.utime(req.path, None)
    except OSError:
        pass
    return await service.backend_raw("get_image_for_occlusion", body)


async def add_image_occlusion_note(service, body: bytes, hub) -> bytes:
    import anki.image_occlusion_pb2 as iopb
    from ankiweb import import_tmp
    req = iopb.AddImageOcclusionNoteRequest()
    req.ParseFromString(bytes(body))
    if not import_tmp.is_within(service.settings, req.image_path):
        raise ValueError("image path not allowed")
    out = await service.backend_raw("add_image_occlusion_note", body)
    await _emit_opchanges(service, out)
    return out


async def update_image_occlusion_note(service, body: bytes, hub) -> bytes:
    out = await service.backend_raw("update_image_occlusion_note", body)
    await _emit_opchanges(service, out)
    return out


CUSTOM["getImageForOcclusion"] = get_image_for_occlusion
CUSTOM["addImageOcclusionNote"] = add_image_occlusion_note
CUSTOM["updateImageOcclusionNote"] = update_image_occlusion_note
