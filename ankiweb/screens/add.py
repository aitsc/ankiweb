from __future__ import annotations
import html
import json
from ankiweb.screens.editor import _munge, paste_handler_js
from ankiweb.ankiconnect.actions._helpers import check_addable
from ankiweb.collection_service import op_changes_to_flags

_STYLE = (
    "<style>"
    "#add-chrome{position:fixed;top:0;left:0;right:0;height:38px;display:flex;gap:8px;"
    "align-items:center;padding:4px 8px;background:#f4f4f4;border-bottom:1px solid #ccc;z-index:1000}"
    "body{padding-top:44px}"
    "#add-toast{color:#080;margin-left:8px}"
    "</style>"
)


def _empty_load(col, ntid: int) -> dict:
    model = col.models.get(ntid)
    flds = model["flds"]
    return {
        "fields": [[f["name"], ""] for f in flds],
        "fonts": [[f.get("font", "Arial"), int(f.get("size", 20)), bool(f.get("rtl", False))]
                  for f in flds],
        "io": False,
        "noteId": 0,
        "meta": {"id": model["id"], "modTime": model.get("mod", 0)},
        "tags": [],
    }


def add_page_body(deck_opts: str, nt_opts: str) -> str:
    return (
        _STYLE +
        "<div id='add-chrome'>"
        "<label>Deck <select id='add-deck' "
        "onchange=\"window.pycmd('setdeck:'+this.value)\">" + deck_opts + "</select></label>"
        "<label>Type <select id='add-notetype' "
        "onchange=\"window.pycmd('setnotetype:'+this.value)\">" + nt_opts + "</select></label>"
        "<button id='add-btn' onclick='ankiwebAddNote()'>Add Note</button>"
        "<a href='/deckbrowser'>Close</a><span id='add-toast'></span>"
        "</div>"
        "<script>(function(){"
        "window.setupEditor('add');"
        "var b=window.__ankiwebBridge;"
        "function readAllFields(){"
        "var cs=Array.prototype.slice.call(document.querySelectorAll('.field-container'));"
        "cs.sort(function(a,b){return Number(a.dataset.index)-Number(b.dataset.index);});"
        "return cs.map(function(fc){var h=fc.querySelector('.rich-text-editable');"
        "if(!h||!h.shadowRoot)return '';"
        "var e=h.shadowRoot.querySelector('[contenteditable]');return e?e.innerHTML:'';});}"
        "window.ankiwebAddNote=function(){window.pycmd('addnote:'+JSON.stringify(readAllFields()));};"
        "b.registerCalls({"
        "ankiwebLoadNote:function(d){require('anki/ui').loaded.then(function(){"
        "window.setFields(d.fields);window.setIsImageOcclusion(d.io);window.setFonts(d.fonts);"
        "window.setNotetypeMeta(d.meta);window.setNoteId(d.noteId);window.setTags(d.tags);"
        "window.triggerChanges();});},"
        "ankiwebToast:function(m){var t=document.getElementById('add-toast');if(t){"
        "t.textContent=String(m);setTimeout(function(){t.textContent='';},2000);}}"
        "});"
        "require('anki/ui').loaded.then(function(){window.pycmd('addReady');});"
        + paste_handler_js() +
        "})();</script>"
    )


def render_add_html(col) -> str:
    cur_nt = col.models.current()["id"]
    cur_did = col.decks.get_current_id()
    decks = "".join(
        f"<option value='{d.id}'{' selected' if d.id == cur_did else ''}>{html.escape(d.name)}</option>"
        for d in col.decks.all_names_and_ids())
    nts = "".join(
        f"<option value='{m.id}'{' selected' if m.id == cur_nt else ''}>{html.escape(m.name)}</option>"
        for m in col.models.all_names_and_ids())
    return add_page_body(decks, nts)


def make_add_handler(service, hub):
    state = {"notetype_id": None, "deck_id": None, "tags": []}

    async def handler(arg: str):
        head, _, rest = arg.partition(":")
        if head == "addReady":
            def init(col):
                ntid = col.models.current()["id"]
                did = col.decks.get_current_id()
                return ntid, did, _empty_load(col, ntid)
            ntid, did, data = await service.run(init)
            state.update(notetype_id=ntid, deck_id=did, tags=[])
            await hub.push_call("add", "ankiwebLoadNote", [data])
        elif head == "setnotetype":
            ntid = int(rest)
            state["notetype_id"] = ntid
            state["tags"] = []
            data = await service.run(lambda col: _empty_load(col, ntid))
            await hub.push_call("add", "ankiwebLoadNote", [data])
        elif head == "setdeck":
            state["deck_id"] = int(rest)
        elif head == "saveTags":
            state["tags"] = json.loads(rest)
        elif head == "addnote":
            fields = json.loads(rest)
            ntid, did, tags = state["notetype_id"], state["deck_id"], list(state["tags"])

            def add(col):
                model = col.models.get(ntid)
                note = col.new_note(model)
                for i, h in enumerate(fields):
                    if i < len(note.fields):
                        note.fields[i] = _munge(col, h)
                note.tags = tags
                ok, err = check_addable(col, note, None)
                if not ok:
                    return (None, err), None
                op = col.add_note(note, did)
                return (note.id, None), op
            (nid, err), op = await service.run(add)
            if op is not None:
                flags = op_changes_to_flags(getattr(op, "changes", op))
                if any(flags.values()):
                    await service.emit(flags, "add")
            if err:
                await hub.push_call("add", "ankiwebToast", [err])
            else:
                data = await service.run(lambda col: _empty_load(col, ntid))
                await hub.push_call("add", "ankiwebLoadNote", [data])
                await hub.push_call("add", "ankiwebToast", ["Added"])
        return None

    return handler
