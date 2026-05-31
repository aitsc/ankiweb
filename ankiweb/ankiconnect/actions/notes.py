from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import run_emit, build_note, check_addable
from ankiweb.ankiconnect.actions.media import attach_media


@action("addNote")
async def add_note(rt, note=None):
    spec = note or {}

    def fn(col):
        attach_media(col, spec)
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
                spec = spec or {}
                attach_media(col, spec)
                n, _ = build_note(col, spec)
                ok, err = check_addable(col, n, spec.get("options"))
                if not ok:
                    raise Exception(err)
                did = col.decks.id(spec.get("deckName", "Default"))
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


from ankiweb.ankiconnect.actions._helpers import note_to_info  # noqa: E402


@action("notesInfo")
async def notes_info(rt, notes=None, query=None):
    def fn(col):
        ids = list(notes) if notes is not None else list(col.find_notes(query or ""))
        out = []
        for nid in ids:
            try:
                out.append(note_to_info(col, col.get_note(nid)))
            except Exception:
                out.append({})
        return out
    return await rt.service.run(fn)


@action("updateNoteFields")
async def update_note_fields(rt, note=None):
    spec = note or {}

    def fn(col):
        n = col.get_note(spec["id"])
        for name, val in (spec.get("fields") or {}).items():
            if name in n:  # case-sensitive (AnkiConnect updateNoteFields is case-sensitive)
                n[name] = val
        return None, col.update_note(n, skip_undo_entry=True)
    await run_emit(rt, fn)
    return None


@action("updateNoteTags")
async def update_note_tags(rt, note=None, tags=None):
    tags = tags or []

    def fn(col):
        n = col.get_note(note)
        n.tags = list(tags)
        return None, col.update_note(n)
    await run_emit(rt, fn)
    return None


@action("getNoteTags")
async def get_note_tags(rt, note=None):
    return await rt.service.run(lambda col: list(col.get_note(note).tags))


@action("updateNote")
async def update_note(rt, note=None):
    spec = note or {}
    if "fields" not in spec and "tags" not in spec:
        raise Exception('Must provide a "fields" or "tags" property.')
    if "fields" in spec:
        await update_note_fields(rt, note=spec)
    if "tags" in spec:
        await update_note_tags(rt, note=spec["id"], tags=spec["tags"])
    return None


@action("updateNoteModel")
async def update_note_model(rt, note=None):
    # Reassign a note's notetype + fields/tags. Minimal: change mid, rebuild fields by name.
    spec = note or {}

    def fn(col):
        n = col.get_note(spec["id"])
        model = col.models.by_name(spec.get("modelName", ""))
        if model is None:
            raise Exception("model was not found: " + str(spec.get("modelName")))
        n.mid = model["id"]
        n.fields = [""] * len(model["flds"])
        by_lower = {f["name"].lower(): i for i, f in enumerate(model["flds"])}
        for name, val in (spec.get("fields") or {}).items():
            idx = by_lower.get(str(name).lower())
            if idx is not None:
                n.fields[idx] = val
        if "tags" in spec:
            n.tags = list(spec["tags"])
        return None, col.update_note(n)
    await run_emit(rt, fn)
    return None


@action("addTags")
async def add_tags(rt, notes=None, tags=None, add=True):
    notes = notes or []

    def fn(col):
        return None, col.tags.bulk_add(notes, tags or "")
    await run_emit(rt, fn)
    return None


@action("removeTags")
async def remove_tags(rt, notes=None, tags=None):
    notes = notes or []

    def fn(col):
        return None, col.tags.bulk_remove(notes, tags or "")
    await run_emit(rt, fn)
    return None


@action("getTags")
async def get_tags(rt):
    return await rt.service.run(lambda col: col.tags.all())


@action("clearUnusedTags")
async def clear_unused_tags(rt):
    def fn(col):
        return None, col.tags.clear_unused_tags()
    await run_emit(rt, fn)
    return None


@action("replaceTags")
async def replace_tags(rt, notes=None, tag_to_replace=None, replace_with_tag=None):
    notes = notes or []

    def fn(col):
        for nid in notes:
            n = col.get_note(nid)
            if tag_to_replace in n.tags:
                n.tags = [replace_with_tag if t == tag_to_replace else t for t in n.tags]
                col.update_note(n)
        return None
    await rt.service.run(fn)
    return None


@action("replaceTagsInAllNotes")
async def replace_tags_in_all_notes(rt, tag_to_replace=None, replace_with_tag=None):
    def fn(col):
        return None, col.tags.rename(tag_to_replace, replace_with_tag)
    await run_emit(rt, fn)
    return None


@action("notesModTime")
async def notes_mod_time(rt, notes=None):
    notes = notes or []

    def fn(col):
        out = []
        for nid in notes:
            try:
                out.append({"noteId": nid, "mod": col.get_note(nid).mod})
            except Exception:
                out.append({})
        return out
    return await rt.service.run(fn)


@action("deleteNotes")
async def delete_notes(rt, notes=None):
    notes = notes or []

    def fn(col):
        return None, col.remove_notes(notes)
    await run_emit(rt, fn)
    return None


@action("removeEmptyNotes")
async def remove_empty_notes(rt):
    def fn(col):
        report = col.get_empty_cards()
        # use the backend's own "all this note's cards are empty" flag
        nids = [e.note_id for e in report.notes if e.will_delete_note]
        if nids:
            return None, col.remove_notes(nids)
        return None, None  # run_emit tolerates a None op
    await run_emit(rt, fn)
    return None


@action("cardsToNotes")
async def cards_to_notes(rt, cards=None):
    cards = cards or []

    def fn(col):
        seen = []
        for cid in cards:
            nid = col.get_card(cid).nid
            if nid not in seen:
                seen.append(nid)
        return seen
    return await rt.service.run(fn)
