from __future__ import annotations
from ankiweb.collection_service import op_changes_to_flags

_EMPTY, _DUPLICATE = 1, 2  # note.fields_check() int states


async def run_emit(rt, fn):
    """Run fn(col) -> (value, op_with_changes | None); broadcast its OpChanges flags on the
    bus (so an open web UI refreshes); return value. Tolerates a None op (no-op actions)."""
    value, op = await rt.service.run(fn)
    if op is None:
        return value
    changes = getattr(op, "changes", op)
    flags = op_changes_to_flags(changes)
    if any(flags.values()):
        await rt.service.emit(flags, "ankiconnect")
    return value


def build_note(col, spec):
    """Build (not add) an anki Note from an AnkiConnect note spec. Case-insensitive field
    matching. Media fields (audio/video/picture) deferred to B3."""
    spec = spec or {}
    model = col.models.by_name(spec.get("modelName", ""))
    if model is None:
        raise Exception("model was not found: " + str(spec.get("modelName")))
    note = col.new_note(model)
    by_lower = {f["name"].lower(): f["name"] for f in model["flds"]}
    for key, val in (spec.get("fields") or {}).items():
        real = by_lower.get(str(key).lower())
        if real is not None:
            note[real] = val
    for tag in spec.get("tags") or []:
        note.add_tag(tag)
    return note, model


def check_addable(col, note, options):
    options = options or {}
    fc = note.fields_check()
    if fc == _EMPTY:
        return False, "cannot create note because it is empty"
    if fc == _DUPLICATE and not options.get("allowDuplicate", False):
        return False, "cannot create note because it is a duplicate"
    return True, None
