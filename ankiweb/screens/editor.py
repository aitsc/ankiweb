from __future__ import annotations
import json


def _munge(col, html: str) -> str:
    """editor_will_munge_html equivalent: null-strip, drop bare <br>, unescape media."""
    html = (html or "").replace("\x00", "")
    if html in ("<br>", "<div><br></div>"):
        html = ""
    return col.media.escape_media_filenames(html, unescape=True)


def _build_load(col, nid: int) -> dict:
    note = col.get_note(nid)
    model = note.note_type()
    flds = model["flds"]
    return {
        "fields": [[f["name"], col.media.escape_media_filenames(note.fields[i])]
                   for i, f in enumerate(flds)],
        "fonts": [[f.get("font", "Arial"), int(f.get("size", 20)), bool(f.get("rtl", False))]
                  for f in flds],
        "io": False,
        "noteId": nid,
        "meta": {"id": model["id"], "modTime": model.get("mod", 0)},
        "tags": list(note.tags),
    }


def _save_field(col, nid: int, ord_: int, html: str):
    note = col.get_note(nid)
    if 0 <= ord_ < len(note.fields):
        note.fields[ord_] = _munge(col, html)
        return col.update_note(note, skip_undo_entry=True)
    return None


def editor_page_body(nid: int) -> str:
    return (
        f"<script>window.__ankiwebEditNid={int(nid)}</script>"
        "<script>(function(){"
        "window.setupEditor('browse');"
        "var b=window.__ankiwebBridge;"
        "b.registerCalls({ankiwebLoadNote:function(d){"
        "require('anki/ui').loaded.then(function(){"
        "window.setFields(d.fields);"
        "window.setIsImageOcclusion(d.io);"
        "window.setFonts(d.fonts);"
        "window.setNotetypeMeta(d.meta);"
        "window.setNoteId(d.noteId);"
        "window.setTags(d.tags);"
        "window.triggerChanges();"
        "});}});"
        "require('anki/ui').loaded.then(function(){"
        "window.pycmd('load:'+window.__ankiwebEditNid);"
        "});"
        "})();</script>"
    )


def make_editor_handler(service, hub):
    state = {"nid": None}

    async def handler(arg: str):
        head, _, rest = arg.partition(":")
        if head == "load":
            nid = int(rest)
            state["nid"] = nid
            data = await service.run(lambda col: _build_load(col, nid))
            await hub.push_call("editor", "ankiwebLoadNote", [data])
        elif head in ("blur", "key"):
            parts = rest.split(":", 2)
            if len(parts) == 3:
                ord_, nid, htmlval = int(parts[0]), int(parts[1]), parts[2]
                if head == "blur":
                    await service.run_op(lambda col: _save_field(col, nid, ord_, htmlval),
                                         initiator="editor")
                else:
                    await service.run(lambda col: _save_field(col, nid, ord_, htmlval))
        elif head == "saveTags":
            if state["nid"] is not None:
                tags = json.loads(rest)
                nid = state["nid"]

                def fn(col):
                    n = col.get_note(nid)
                    n.tags = list(tags)
                    return col.update_note(n, skip_undo_entry=True)
                await service.run_op(fn, initiator="editor")
        return None

    return handler
