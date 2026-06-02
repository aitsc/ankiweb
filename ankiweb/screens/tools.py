from __future__ import annotations
import html

from ankiweb.i18n import tr


def render_tools_html(col) -> str:
    """Server-rendered Tools page: Check Database, Check Media, Empty Cards (each a
    button + an empty result <div> filled by the WS handler via ankiwebToolsResult),
    plus a link to Manage Note Types. Mirrors the E4/E5 server-rendered screens."""
    L_checkdb = html.escape(tr.database_check_title())          # "Check Database"
    L_checkmedia = html.escape(tr.media_check_check_media_action())  # "Check Media"
    L_emptycards = html.escape(tr.qt_misc_empty_cards())        # "Empty Cards..."
    L_notetypes = html.escape(tr.qt_misc_manage_note_types())   # "Manage Note Types"

    return f"""
<div class='tools'>
  <h3>Tools</h3>
  <section style='margin-bottom:16px;'>
    <button type='button' onclick="pycmd('checkdb')">{L_checkdb}</button>
    <div id='res-db'></div>
  </section>
  <section style='margin-bottom:16px;'>
    <button type='button' onclick="pycmd('checkmedia')">{L_checkmedia}</button>
    <div id='res-media'></div>
  </section>
  <section style='margin-bottom:16px;'>
    <button type='button' onclick="pycmd('emptycards')">{L_emptycards}</button>
    <div id='res-empty'></div>
  </section>
  <p><a href='/notetypes'>{L_notetypes}</a></p>
</div>
<script>
window.ankiwebToolsResult=function(which,html){{var m={{db:'res-db',media:'res-media',empty:'res-empty'}};var d=document.getElementById(m[which]);if(d)d.innerHTML=html;}};
</script>
"""


def _media_result_html(mc) -> str:
    """Build the Check Media result fragment: the report, a Delete-unused button when
    there are unused files, and short escaped previews of the unused/missing names."""
    parts = ["<pre>" + html.escape(mc.report) + "</pre>"]
    unused = list(mc.unused)
    missing = list(mc.missing)
    if unused:
        L_del = html.escape(tr.media_check_delete_unused())
        parts.append(
            f"<button type='button' onclick=\"pycmd('deleteunused')\">"
            f"{L_del} ({len(unused)})</button>")
        preview = ", ".join(html.escape(n) for n in unused[:10])
        more = "" if len(unused) <= 10 else f" (+{len(unused) - 10})"
        parts.append(f"<div class='unused-list'>{preview}{more}</div>")
    if missing:
        preview = ", ".join(html.escape(n) for n in missing[:10])
        more = "" if len(missing) <= 10 else f" (+{len(missing) - 10})"
        parts.append(f"<div class='missing-list'>{preview}{more}</div>")
    return "".join(parts)


def make_tools_handler(service, hub):
    """WS handler for the Tools page. A per-handler `state` dict stashes the last
    check's results so the matching delete acts on that report rather than recomputing
    and deleting blindly."""
    state: dict = {}

    async def _push_media(mc):
        state["unused"] = list(mc.unused)
        await hub.push_call("tools", "ankiwebToolsResult", ["media", _media_result_html(mc)])

    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")

        if cmd == "checkdb":
            report, ok = await service.run(lambda col: col.fix_integrity())
            await hub.push_call(
                "tools", "ankiwebToolsResult",
                ["db", "<pre>" + html.escape(report) + "</pre>"])
            return None

        if cmd == "checkmedia":
            mc = await service.run(lambda col: col.media.check())
            await _push_media(mc)
            return None

        if cmd == "deleteunused":
            un = state.get("unused") or []
            if un:
                await service.run(
                    lambda col: (col.media.trash_files(un), col.media.empty_trash()))
            state["unused"] = []
            # Re-run the check so the displayed count reflects the deletion.
            mc = await service.run(lambda col: col.media.check())
            await _push_media(mc)
            return None

        if cmd == "emptycards":
            rep = await service.run(lambda col: col.get_empty_cards())
            cids = [cid for n in rep.notes for cid in n.card_ids]
            state["empty"] = cids
            parts = ["<pre>" + html.escape(rep.report) + "</pre>"]
            if cids:
                L_del = html.escape(tr.empty_cards_delete_button())
                parts.append(
                    f"<button type='button' onclick=\"pycmd('emptycards_delete')\">"
                    f"{L_del} ({len(cids)})</button>")
            await hub.push_call("tools", "ankiwebToolsResult", ["empty", "".join(parts)])
            return None

        if cmd == "emptycards_delete":
            cids = state.get("empty") or []
            if cids:
                await service.run_op(
                    lambda col: col.remove_cards_and_orphaned_notes(cids),
                    initiator="tools")
            n = len(cids)
            state["empty"] = []
            await hub.push_call(
                "tools", "ankiwebToolsResult",
                ["empty", f"<p>Deleted {n} empty cards</p>"])
            return None

        return None

    return handler
