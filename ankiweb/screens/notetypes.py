from __future__ import annotations
import copy
import html

from ankiweb.i18n import tr


def _heading() -> str:
    """Prefer the desktop "Manage Note Types" string; fall back to a keyless heading.
    (qt_misc_manage_note_types exists; notetypes_notetypes does not.)"""
    try:
        return tr.qt_misc_manage_note_types()
    except Exception:
        return "Note Types"


def render_notetypes_html(col) -> str:
    H = html.escape(_heading())
    L_rename = html.escape(tr.actions_rename())
    L_delete = html.escape(tr.actions_delete())
    L_add = html.escape(tr.actions_add())
    L_name = html.escape(tr.actions_name())
    L_fields = html.escape(tr.notetypes_fields())
    L_cards = html.escape(tr.notetypes_cards())

    rows = []
    options = []
    for nt in col.models.all_names_and_ids():
        ntid = int(nt.id)
        name = html.escape(nt.name)
        count = len(col.models.nids(ntid))
        rows.append(
            f"<tr class='nt-row' data-id='{ntid}' data-name=\"{name}\">"
            f"<td class='nt-name'>{name}</td>"
            f"<td class='nt-count'>{count} notes</td>"
            f"<td><a href='/fields/{ntid}'>{L_fields}</a></td>"
            f"<td><a href='/card-layout/{ntid}'>{L_cards}</a></td>"
            f"<td><button type='button' onclick='ntRename({ntid})'>{L_rename}</button></td>"
            f"<td><button type='button' onclick='ntDelete({ntid}, {count})'>{L_delete}</button></td>"
            "</tr>"
        )
        options.append(f"<option value='{ntid}'>{name}</option>")

    rows_html = "".join(rows)
    options_html = "".join(options)

    body = f"""
<div class='notetypes'>
  <h3>{H}</h3>
  <table id='nttbl' border='1' cellpadding='6' cellspacing='0'>
    <tbody id='ntrows'>{rows_html}</tbody>
  </table>
  <div id='ntadd' style='margin-top:16px;'>
    <h4>{L_add}</h4>
    <label>{L_name}
      <input type='text' id='ntnewname' size='24'>
    </label>
    <select id='ntbase'>{options_html}</select>
    <button type='button' onclick='ntAdd()'>{L_add}</button>
  </div>
  <div id='err' style='color:#c00;margin-top:8px;'></div>
</div>
<script>
function ntRename(id) {{
  document.getElementById('err').textContent = '';
  var row = document.querySelector(".nt-row[data-id='" + id + "']");
  var cur = row ? row.getAttribute('data-name') : '';
  var name = window.prompt("New name:", cur);
  if (name) pycmd('rename:' + id + ':' + name);
}}
function ntDelete(id, count) {{
  document.getElementById('err').textContent = '';
  var msg = "Delete this note type and its " + count + " note(s)?";
  if (window.confirm(msg)) pycmd('delete:' + id);
}}
function ntAdd() {{
  document.getElementById('err').textContent = '';
  var name = document.getElementById('ntnewname').value;
  var base = document.getElementById('ntbase').value;
  if (name && base) pycmd('add:' + base + ':' + name);
}}
window.ankiwebNotetypesError = function(m) {{
  var e = document.getElementById('err');
  if (e) e.textContent = m; else alert(m);
}};
</script>
"""
    return body


def make_notetypes_handler(service, hub):
    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")

        if cmd == "rename":
            sid, _, newname = rest.partition(":")
            if not newname:
                await hub.push_call("notetypes", "ankiwebNotetypesError",
                                    ["A name is required."])
                return None

            def do_rename(col):
                m = col.models.get(int(sid))
                m["name"] = newname
                return col.models.update_dict(m)

            try:
                await service.run_op(do_rename, initiator="notetypes")
            except Exception as exc:
                await hub.push_call("notetypes", "ankiwebNotetypesError", [str(exc)])
                return None
            await hub.push_call("notetypes", "ankiwebReload", [])
            return None

        if cmd == "delete":
            try:
                ntid = int(rest)
            except ValueError:
                return None

            # Guard: never delete the only note type.
            if await service.run(lambda col: len(col.models.all_names_and_ids())) <= 1:
                await hub.push_call("notetypes", "ankiwebNotetypesError",
                                    ["Cannot delete the only note type"])
                return None

            def do_delete(col):
                return col.models.remove(ntid)

            try:
                await service.run_op(do_delete, initiator="notetypes")
            except Exception as exc:
                await hub.push_call("notetypes", "ankiwebNotetypesError", [str(exc)])
                return None
            await hub.push_call("notetypes", "ankiwebReload", [])
            return None

        if cmd == "add":
            sbase, _, newname = rest.partition(":")
            if not newname:
                await hub.push_call("notetypes", "ankiwebNotetypesError",
                                    ["A name is required."])
                return None

            def do_add(col):
                # Deep-clone the base notetype into a fresh, usable one (id=0 lets the
                # backend assign a new id while keeping flds/tmpls/css so cards generate).
                base = col.models.get(int(sbase))
                nt = copy.deepcopy(base)
                nt["name"] = newname
                nt["id"] = 0
                return col.models.add_dict(nt)

            try:
                await service.run_op(do_add, initiator="notetypes")
            except Exception as exc:
                await hub.push_call("notetypes", "ankiwebNotetypesError", [str(exc)])
                return None
            await hub.push_call("notetypes", "ankiwebReload", [])
            return None

        return None

    return handler
