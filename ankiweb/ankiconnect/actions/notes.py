from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import run_emit, build_note, check_addable


@action("addNote")
async def add_note(rt, note=None):
    spec = note or {}

    def fn(col):
        n, _ = build_note(col, spec)
        ok, err = check_addable(col, n, spec.get("options"))
        if not ok:
            raise Exception(err)
        did = col.decks.id(spec.get("deckName", "Default"))
        res = col.add_note(n, did)
        return n.id, res
    return await run_emit(rt, fn)


@action("canAddNote")
async def can_add_note(rt, note=None):
    spec = note or {}

    def fn(col):
        try:
            n, _ = build_note(col, spec)
            ok, _err = check_addable(col, n, spec.get("options"))
            return ok
        except Exception:
            return False
    return await rt.service.run(fn)


@action("canAddNoteWithErrorDetail")
async def can_add_note_with_error_detail(rt, note=None):
    spec = note or {}

    def fn(col):
        try:
            n, _ = build_note(col, spec)
            ok, err = check_addable(col, n, spec.get("options"))
            return {"canAdd": ok} if ok else {"canAdd": False, "error": err}
        except Exception as exc:
            return {"canAdd": False, "error": str(exc)}
    return await rt.service.run(fn)


@action("addNotes")
async def add_notes(rt, notes=None):
    specs = notes or []

    def fn(col):
        # Faithful to AnkiConnect (__init__.py:2134): add each (addNote raises on empty/dup);
        # collect errors; if ANY failed, roll back ALL added notes and raise; else return ids.
        added_ids = []
        errs = []
        last_op = None
        for spec in specs:
            try:
                n, _ = build_note(col, spec or {})
                ok, err = check_addable(col, n, (spec or {}).get("options"))
                if not ok:
                    raise Exception(err)
                did = col.decks.id((spec or {}).get("deckName", "Default"))
                last_op = col.add_note(n, did)
                added_ids.append(n.id)
            except Exception as e:
                errs.append(str(e))
        if errs:
            if added_ids:
                col.remove_notes(added_ids)
            raise Exception(str(errs))
        return added_ids, last_op
    return await run_emit(rt, fn)


@action("canAddNotes")
async def can_add_notes(rt, notes=None):
    return [await can_add_note(rt, note=n) for n in (notes or [])]


@action("canAddNotesWithErrorDetail")
async def can_add_notes_with_error_detail(rt, notes=None):
    return [await can_add_note_with_error_detail(rt, note=n) for n in (notes or [])]


@action("findNotes")
async def find_notes(rt, query=None):
    return await rt.service.run(lambda col: list(col.find_notes(query or "")))
