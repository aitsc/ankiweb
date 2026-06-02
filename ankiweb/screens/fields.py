from __future__ import annotations
import html
import json

from ankiweb.i18n import tr


def _field_row(field: dict, sortf: int) -> str:
    """One editable field row. data-orig carries the original `ord` so the handler can
    match renames/repositions; a freshly added row carries data-orig='new'."""
    ord_ = field["ord"]
    name = html.escape(field.get("name", ""))
    font = html.escape(field.get("font", "Arial"))
    size = int(field.get("size", 20))
    rtl = " checked" if field.get("rtl", False) else ""
    desc = html.escape(field.get("description", ""))
    sort = " checked" if ord_ == sortf else ""
    L_name = html.escape(tr.actions_name())
    L_font = html.escape(tr.fields_editing_font())
    L_size = html.escape(tr.fields_size())
    L_rtl = html.escape(tr.fields_reverse_text_direction_rtl())
    L_desc = html.escape(tr.fields_description())
    L_sort = html.escape(tr.browsing_sort_field())
    L_del = html.escape(tr.actions_delete())
    return (
        f"<tr class='field-row' data-orig='{ord_}'>"
        f"<td><label>{L_name} <input type='text' class='fld-name' value=\"{name}\" size='16'></label></td>"
        f"<td><label>{L_font} <input type='text' class='fld-font' value=\"{font}\" size='10'></label></td>"
        f"<td><label>{L_size} <input type='number' class='fld-size' value='{size}' min='1' style='width:5em;'></label></td>"
        f"<td><label><input type='checkbox' class='fld-rtl'{rtl}> {L_rtl}</label></td>"
        f"<td><label>{L_desc} <input type='text' class='fld-desc' value=\"{desc}\" size='16'></label></td>"
        f"<td><label><input type='radio' name='sortf' class='fld-sort'{sort}> {L_sort}</label></td>"
        "<td>"
        "<button type='button' onclick='moveUp(this)'>&uarr;</button> "
        "<button type='button' onclick='moveDown(this)'>&darr;</button> "
        f"<button type='button' onclick='deleteRow(this)'>{L_del}</button>"
        "</td>"
        "</tr>"
    )


def _blank_row_template() -> str:
    """The HTML for a freshly added (data-orig='new') row, used by the client addRow()."""
    return _field_row(
        {"ord": "new", "name": "", "font": "Arial", "size": 20, "rtl": False, "description": ""},
        sortf=-1,
    )


def render_fields_html(col, ntid: int) -> str:
    m = col.models.get(ntid)
    sortf = m["sortf"]
    rows = "".join(_field_row(f, sortf) for f in m["flds"])
    blank = _blank_row_template()

    L_add = html.escape(tr.fields_add_field())
    L_save = html.escape(tr.actions_save())
    L_cancel = html.escape(tr.actions_cancel())

    body = f"""
<div class='fields'>
  <h3>Fields</h3>
  <input type='hidden' id='ntid' value='{int(ntid)}'>
  <form id='ff' onsubmit='return false;'>
    <table id='fieldtbl'><tbody id='fieldrows'>{rows}</tbody></table>
    <div style='margin-top:8px;'>
      <button type='button' id='addfield' onclick='addRow()'>{L_add}</button>
    </div>
    <div style='margin-top:10px;'>
      <button type='button' id='save' onclick='saveFields()'>{L_save}</button>
      <button type='button' onclick="pycmd('cancel')">{L_cancel}</button>
    </div>
    <div id='err' style='color:#c00;margin-top:8px;'></div>
  </form>
</div>
<template id='blankrow'>{blank}</template>
<script>
function addRow() {{
  var tpl = document.getElementById('blankrow');
  var tr = tpl.content.firstElementChild.cloneNode(true);
  document.getElementById('fieldrows').appendChild(tr);
}}
function deleteRow(btn) {{
  var tr = btn.closest('tr');
  tr.parentNode.removeChild(tr);
}}
function moveUp(btn) {{
  var tr = btn.closest('tr');
  var prev = tr.previousElementSibling;
  if (prev) tr.parentNode.insertBefore(tr, prev);
}}
function moveDown(btn) {{
  var tr = btn.closest('tr');
  var next = tr.nextElementSibling;
  if (next) tr.parentNode.insertBefore(next, tr);
}}
function saveFields() {{
  document.getElementById('err').textContent = '';
  var rows = Array.prototype.slice.call(
    document.querySelectorAll('#fieldrows .field-row'));
  var sortf = 0;
  var fields = rows.map(function(tr, i) {{
    if (tr.querySelector('.fld-sort').checked) sortf = i;
    var orig = tr.getAttribute('data-orig');
    return {{
      orig: (orig === 'new') ? null : parseInt(orig),
      name: tr.querySelector('.fld-name').value,
      font: tr.querySelector('.fld-font').value,
      size: parseInt(tr.querySelector('.fld-size').value || '20'),
      rtl: tr.querySelector('.fld-rtl').checked,
      description: tr.querySelector('.fld-desc').value
    }};
  }});
  var payload = {{
    notetypeId: parseInt(document.getElementById('ntid').value),
    sortf: sortf,
    fields: fields
  }};
  pycmd('savefields:' + JSON.stringify(payload));
}}
window.ankiwebFieldsError = function(m) {{ document.getElementById('err').textContent = m; }};
</script>
"""
    return body


def make_fields_handler(service, hub):
    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "cancel":
            await hub.push_call("fields", "ankiwebNavigate", ["/deckbrowser"])
            return None
        if cmd != "savefields":
            return None
        try:
            p = json.loads(rest)
        except Exception:
            return None

        def apply(col):
            ntid = int(p["notetypeId"]); m = col.models.get(ntid)
            cur = list(m["flds"]); by_ord = {f["ord"]: f for f in cur}
            payload = p["fields"]
            kept = {f["orig"] for f in payload if f.get("orig") is not None}
            deletes = [f for f in cur if f["ord"] not in kept]
            remaining = len(cur) - len(deletes) + sum(1 for f in payload if f.get("orig") is None)
            if len(payload) == 0 or remaining < 1:
                raise Exception("a notetype needs at least one field")
            for f in deletes:
                col.models.remove_field(m, f)
            for fp in payload:
                if fp.get("orig") is not None:
                    fd = by_ord[fp["orig"]]
                    if fd["name"] != fp["name"]:
                        col.models.rename_field(m, fd, fp["name"])
            for fp in payload:
                if fp.get("orig") is None:
                    col.models.add_field(m, col.models.new_field(fp["name"]))

            def by_name(nm):
                return next(x for x in m["flds"] if x["name"] == nm)
            for i, fp in enumerate(payload):
                fd = by_name(fp["name"])
                fd["font"] = fp.get("font", "Arial")
                fd["size"] = int(fp.get("size", 20))
                fd["rtl"] = bool(fp.get("rtl", False))
                fd["description"] = fp.get("description", "")
                col.models.reposition_field(m, fd, i)
            col.models.set_sort_index(m, int(p.get("sortf", 0)))
            return col.models.update_dict(m)

        try:
            await service.run_op(apply, initiator="fields")
        except Exception as exc:
            await hub.push_call("fields", "ankiwebFieldsError", [str(exc)])
            return None
        await hub.push_call("fields", "ankiwebNavigate", ["/deckbrowser"])
        return None

    return handler
