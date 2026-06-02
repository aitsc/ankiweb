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


def paste_handler_js() -> str:
    """A document-capture paste handler that takes over from editor.js (which prevent-defaults
    paste and fires a payload-less bridgeCommand('paste')). Inserts via the editor's pasteHTML."""
    return (
        "document.addEventListener('paste',function(e){"
        "var cd=e.clipboardData;if(!cd)return;"
        "var img=null,items=cd.items||[];"
        "for(var i=0;i<items.length;i++){if(items[i].kind==='file'&&items[i].type&&"
        "items[i].type.indexOf('image/')===0){img=items[i].getAsFile();break;}}"
        "var html=cd.getData('text/html'),text=cd.getData('text/plain');"
        "if(!img&&!html&&!text)return;"
        "e.preventDefault();e.stopImmediatePropagation();"
        "if(img){var f=new FormData();f.append('file',img,img.name||'paste.png');"
        "fetch('/upload_media',{method:'POST',body:f}).then(function(r){return r.json();})"
        ".then(function(j){window.pasteHTML('<img src=\"'+j.filename+'\">',false,false);});}"
        "else if(html){window.pasteHTML(html,false,false);}"
        "else{var s=text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')"
        ".replace(/\\n/g,'<br>');window.pasteHTML(s,false,false);}"
        "},true);"
    )


def editor_links_js() -> str:
    """Wraps the bridge so the editor toolbar's host-dependent buttons work in the browser:
    'attach' -> a file picker -> /upload_media -> pasteHTML(img/[sound:]); 'preview' ->
    open /preview/<nid> in a new tab (browse mode only). 'fields'/'cards' are added by F5/F6.
    Everything else passes through to the real bridge (blur/key/saveTags/paste...)."""
    return (
        "var _awOrig=window.pycmd;"
        "function _awAttach(){var inp=document.createElement('input');inp.type='file';"
        "inp.accept='image/*,audio/*,video/*';inp.onchange=function(){"
        "var f=inp.files&&inp.files[0];if(!f)return;var fd=new FormData();fd.append('file',f,f.name);"
        "fetch('/upload_media',{method:'POST',body:fd}).then(function(r){return r.json();})"
        ".then(function(j){if(!j.filename)return;var fn=j.filename,tag;"
        "if(/\\.(png|jpg|jpeg|gif|webp|bmp|svg|avif)$/i.test(fn))tag='<img src=\"'+fn+'\">';"
        "else tag='[sound:'+fn+']';window.pasteHTML(tag,false,false);});};inp.click();}"
        "function _awCmd(c,cb){if(typeof c==='string'){"
        "if(c==='attach'){_awAttach();return;}"
        "if(c==='preview'){var nid=window.__ankiwebEditNid;if(nid)window.open('/preview/'+nid,'_blank');return;}"
        "if(c==='fields'){if(window.__ankiwebNotetypeId)window.open('/fields/'+window.__ankiwebNotetypeId,'_blank');return;}"
        "if(c==='cards'){if(window.__ankiwebNotetypeId)window.open('/card-layout/'+window.__ankiwebNotetypeId,'_blank');return;}}"
        "return _awOrig?_awOrig.call(window,c,cb):undefined;}"
        "window.pycmd=_awCmd;window.bridgeCommand=_awCmd;"
    )


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
        "window.__ankiwebNotetypeId=d.meta.id;"
        "window.setNoteId(d.noteId);"
        "window.setTags(d.tags);"
        "window.triggerChanges();"
        "});}});"
        "require('anki/ui').loaded.then(function(){"
        "window.pycmd('load:'+window.__ankiwebEditNid);"
        "});"
        + paste_handler_js()
        + editor_links_js() +
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
