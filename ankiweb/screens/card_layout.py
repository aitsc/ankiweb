from __future__ import annotations
import html
import json

from ankiweb.i18n import tr


def _tmpl_block(tmpl: dict) -> str:
    """One editable card-template block. data-orig carries the original `ord` so the handler
    can match renames/repositions; a freshly added block carries data-orig='new'."""
    ord_ = tmpl["ord"]
    name = html.escape(tmpl.get("name", ""))
    qfmt = html.escape(tmpl.get("qfmt", ""))
    afmt = html.escape(tmpl.get("afmt", ""))
    L_name = html.escape(tr.actions_name())
    L_front = html.escape(tr.card_templates_front_template())
    L_back = html.escape(tr.card_templates_back_template())
    L_del = html.escape(tr.actions_delete())
    return (
        f"<div class='tmpl-block' data-orig='{ord_}' "
        "style='border:1px solid #ccc;border-radius:6px;padding:10px;margin:10px 0;'>"
        f"<div><label>{L_name} <input type='text' class='tmpl-name' value=\"{name}\" size='24'></label> "
        "<button type='button' onclick='moveUp(this)'>&uarr;</button> "
        "<button type='button' onclick='moveDown(this)'>&darr;</button> "
        f"<button type='button' onclick='deleteBlock(this)'>{L_del}</button>"
        "</div>"
        f"<div class='tmpl-label' style='margin-top:6px;'>{L_front}</div>"
        f"<textarea class='tmpl-qfmt' rows='6' style='width:100%;'>{qfmt}</textarea>"
        f"<div class='tmpl-label' style='margin-top:6px;'>{L_back}</div>"
        f"<textarea class='tmpl-afmt' rows='6' style='width:100%;'>{afmt}</textarea>"
        "</div>"
    )


def _blank_block_template() -> str:
    """HTML for a freshly added (data-orig='new') block, used by the client addBlock()."""
    return _tmpl_block({"ord": "new", "name": "", "qfmt": "", "afmt": ""})


def render_card_layout_html(col, ntid: int) -> str:
    m = col.models.get(ntid)
    blocks = "".join(_tmpl_block(t) for t in m["tmpls"])
    blank = _blank_block_template()
    css = html.escape(m.get("css", ""))

    L_styling = html.escape(tr.card_templates_template_styling())
    L_add = html.escape(tr.card_templates_add_card_type())
    L_save = html.escape(tr.actions_save())
    L_cancel = html.escape(tr.actions_cancel())
    L_preview = html.escape(tr.actions_preview())

    body = f"""
<div class='card-layout'>
  <h3>Card Types</h3>
  <input type='hidden' id='ntid' value='{int(ntid)}'>
  <form id='clf' onsubmit='return false;'>
    <div id='tmplblocks'>{blocks}</div>
    <div style='margin-top:8px;'>
      <button type='button' id='addtmpl' onclick='addBlock()'>{L_add}</button>
    </div>
    <div style='margin-top:12px;'>
      <div class='tmpl-label'>{L_styling}</div>
      <textarea id='css' rows='8' style='width:100%;'>{css}</textarea>
    </div>
    <div style='margin-top:10px;'>
      <button type='button' id='save' onclick='saveLayout()'>{L_save}</button>
      <button type='button' onclick="pycmd('cancel')">{L_cancel}</button>
      <button type='button' id='preview' onclick="pycmd('previewlayout:'+document.getElementById('ntid').value)">{L_preview}</button>
    </div>
    <div id='err' style='color:#c00;margin-top:8px;'></div>
  </form>
</div>
<template id='blankblock'>{blank}</template>
<script>
function addBlock() {{
  var tpl = document.getElementById('blankblock');
  var block = tpl.content.firstElementChild.cloneNode(true);
  document.getElementById('tmplblocks').appendChild(block);
}}
function deleteBlock(btn) {{
  var b = btn.closest('.tmpl-block');
  b.parentNode.removeChild(b);
}}
function moveUp(btn) {{
  var b = btn.closest('.tmpl-block');
  var prev = b.previousElementSibling;
  if (prev) b.parentNode.insertBefore(b, prev);
}}
function moveDown(btn) {{
  var b = btn.closest('.tmpl-block');
  var next = b.nextElementSibling;
  if (next) b.parentNode.insertBefore(next, b);
}}
function saveLayout() {{
  document.getElementById('err').textContent = '';
  var blocks = Array.prototype.slice.call(
    document.querySelectorAll('#tmplblocks .tmpl-block'));
  var templates = blocks.map(function(b) {{
    var orig = b.getAttribute('data-orig');
    return {{
      orig: (orig === 'new') ? null : parseInt(orig),
      name: b.querySelector('.tmpl-name').value,
      qfmt: b.querySelector('.tmpl-qfmt').value,
      afmt: b.querySelector('.tmpl-afmt').value
    }};
  }});
  var payload = {{
    notetypeId: parseInt(document.getElementById('ntid').value),
    css: document.getElementById('css').value,
    templates: templates
  }};
  pycmd('savelayout:' + JSON.stringify(payload));
}}
window.ankiwebCardLayoutError = function(m) {{ document.getElementById('err').textContent = m; }};
</script>
"""
    return body


def make_card_layout_handler(service, hub):
    state = {"ntid": None}

    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "cancel":
            await hub.push_call("cardlayout", "ankiwebNavigate", ["/deckbrowser"])
            return None
        if cmd == "previewlayout":
            # rest carries the ntid (the page knows it via #ntid); fall back to the most
            # recent notetype the page reported so a bare 'previewlayout' still works.
            ntid = None
            if rest:
                try:
                    ntid = int(rest)
                except ValueError:
                    ntid = None
            if ntid is None:
                ntid = state["ntid"]

            def find_nid(col):
                if ntid is not None:
                    return (col.models.nids(ntid) or [None])[0]
                # no ntid context: pick the first notetype that has notes
                for m in col.models.all():
                    nids = col.models.nids(m["id"])
                    if nids:
                        return nids[0]
                return None

            nid = await service.run(find_nid)
            if nid is not None:
                await hub.push_call("cardlayout", "ankiwebNavigate", ["/preview/" + str(nid)])
            else:
                await hub.push_call(
                    "cardlayout", "ankiwebCardLayoutError",
                    ["Add a note of this type first to preview."])
            return None
        if cmd != "savelayout":
            return None
        try:
            p = json.loads(rest)
        except Exception:
            return None
        state["ntid"] = int(p["notetypeId"])

        def apply(col):
            ntid = int(p["notetypeId"]); m = col.models.get(ntid)
            cur = list(m["tmpls"]); by_ord = {t["ord"]: t for t in cur}
            payload = p["templates"]
            kept = {t["orig"] for t in payload if t.get("orig") is not None}
            deletes = [t for t in cur if t["ord"] not in kept]
            remaining = len(cur) - len(deletes) + sum(1 for t in payload if t.get("orig") is None)
            if len(payload) == 0 or remaining < 1:
                raise Exception("a notetype needs at least one card type")
            for t in deletes:
                col.models.remove_template(m, t)
            for tp in payload:
                if tp.get("orig") is not None:
                    td = by_ord[tp["orig"]]
                    td["name"] = tp["name"]
                    td["qfmt"] = tp.get("qfmt", "")
                    td["afmt"] = tp.get("afmt", "")
            for tp in payload:
                if tp.get("orig") is None:
                    nt = col.models.new_template(tp["name"])
                    nt["qfmt"] = tp.get("qfmt", "")
                    nt["afmt"] = tp.get("afmt", "")
                    col.models.add_template(m, nt)

            def by_name(nm):
                return next(x for x in m["tmpls"] if x["name"] == nm)
            for i, tp in enumerate(payload):
                col.models.reposition_template(m, by_name(tp["name"]), i)
            m["css"] = p.get("css", "")
            return col.models.update_dict(m)

        try:
            await service.run_op(apply, initiator="cardlayout")
        except Exception as exc:
            await hub.push_call("cardlayout", "ankiwebCardLayoutError", [str(exc)])
            return None
        await hub.push_call("cardlayout", "ankiwebNavigate", ["/deckbrowser"])
        return None

    return handler
