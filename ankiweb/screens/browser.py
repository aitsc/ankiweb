from __future__ import annotations
import html
import re

_TAG_STRIP = re.compile(r"<[^>]+>")
_LIMIT = 500

_STYLE = (
    "<style>"
    "#browser{font-family:sans-serif;font-size:13px}"
    "#browser-top{padding:6px;border-bottom:1px solid #ccc}"
    "#search{width:60%;padding:4px}"
    "#browser-status{margin-left:10px;color:#666}"
    "#browser-main{display:flex;align-items:flex-start}"
    "#sidebar{width:200px;padding:6px;border-right:1px solid #ccc}"
    "#sidebar .side-section{font-weight:bold;margin-top:8px}"
    "#sidebar .side-item{display:block;padding:2px 4px;color:#06c;text-decoration:none}"
    "#sidebar .side-item:hover{background:#eef}"
    "#results-wrap{flex:1;overflow:auto;max-height:80vh}"
    "#results{width:100%;border-collapse:collapse}"
    "#results th,#results td{text-align:left;padding:3px 6px;border-bottom:1px solid #eee}"
    ".browser-row{cursor:pointer}.browser-row:hover{background:#eef}"
    "#detail{width:46%;padding:6px;border-left:1px solid #ccc}"
    "#detail .fldname{font-weight:bold;color:#888;font-size:11px;margin-top:6px}"
    "#results tr.selected{background:#cde}"
    ".editor-frame{width:100%;height:78vh;border:0}"
    "</style>"
)


def _sidebar_html(col) -> str:
    parts = ["<div class='side-section'>Decks</div>"]
    for d in col.decks.all_names_and_ids():
        parts.append(
            f"<a class='side-item' href='#' onclick=\"return pycmd('searchdeck:{d.id}')\">"
            f"{html.escape(d.name)}</a>")
    parts.append("<div class='side-section'>Tags</div>")
    for t in col.tags.all():
        parts.append(
            f"<a class='side-item' href='#' onclick=\"return pycmd('searchtag:{html.escape(t)}')\">"
            f"{html.escape(t)}</a>")
    return "".join(parts)


def render_browser_html(col) -> str:
    return (
        _STYLE +
        "<div id='browser'>"
        "<div id='browser-top'>"
        "<input id='search' type='text' autofocus placeholder='Search…' "
        "onkeydown=\"if(event.key==='Enter'){window.pycmd('search:'+this.value);}\">"
        "<span id='browser-status'></span>"
        "<div id='browser-actions'>"
        "<button onclick=\"ankiwebAct('suspend')\">Suspend</button>"
        "<button onclick=\"ankiwebAct('unsuspend')\">Unsuspend</button>"
        "<button onclick=\"ankiwebAct('forget')\">Forget</button>"
        "<button onclick=\"ankiwebActP('setdue','Due in days (e.g. 0, 3, 1-7):')\">Set Due</button>"
        "<button onclick=\"ankiwebActP('changedeck','Move to deck:')\">Change Deck</button>"
        "<button onclick=\"ankiwebActP('addtag','Add tag:')\">Add Tag</button>"
        "<button onclick=\"ankiwebActP('removetag','Remove tag:')\">Remove Tag</button>"
        "<button onclick=\"if(confirm('Delete selected notes?'))ankiwebAct('delete')\">Delete</button>"
        "</div></div>"
        "<div id='browser-main'>"
        f"<div id='sidebar'>{_sidebar_html(col)}</div>"
        "<div id='results-wrap'><table id='results'>"
        "<thead><tr><th>Sort Field</th><th>Deck</th><th>Due</th></tr></thead>"
        "<tbody id='results-body'></tbody></table></div>"
        "<div id='detail'></div>"
        "</div></div>"
        "<script>(function(){"
        "var b=window.__ankiwebBridge;"
        "window.__ankiwebOnOpchanges=function(){window.pycmd('refresh');};"
        "var _sel=[],_anchor=null;"
        "function _rows(){return Array.prototype.slice.call("
        "document.querySelectorAll('#results-body tr[data-cid]'));}"
        "function _hl(){_rows().forEach(function(tr){"
        "tr.classList.toggle('selected',_sel.indexOf(tr.dataset.cid)>=0);});}"
        "function _selChanged(){window.pycmd('select:'+_sel.join(','));_hl();}"
        "function _click(tr,e){var cid=tr.dataset.cid,rs=_rows();"
        "if(e.shiftKey&&_anchor!==null){"
        "var i=rs.findIndex(function(r){return r.dataset.cid===_anchor;}),"
        "j=rs.findIndex(function(r){return r.dataset.cid===cid;});"
        "if(i>=0&&j>=0){var lo=Math.min(i,j),hi=Math.max(i,j);"
        "_sel=rs.slice(lo,hi+1).map(function(r){return r.dataset.cid;});}}"
        "else if(e.ctrlKey||e.metaKey){var k=_sel.indexOf(cid);"
        "if(k>=0)_sel.splice(k,1);else _sel.push(cid);_anchor=cid;}"
        "else{_sel=[cid];_anchor=cid;}_selChanged();}"
        "window.ankiwebAct=function(v){window.pycmd(v);};"
        "window.ankiwebActP=function(v,m){var x=prompt(m);"
        "if(x!==null&&x!=='')window.pycmd(v+':'+x);};"
        "b.registerCalls({"
        "ankiwebSetRows:function(h,n){document.getElementById('results-body').innerHTML=String(h);"
        "document.getElementById('browser-status').textContent=(n||0)+' cards';"
        "_sel=[];_anchor=null;},"
        "ankiwebSetDetail:function(h){document.getElementById('detail').innerHTML=String(h);}"
        "});"
        "document.getElementById('results-body').addEventListener('click',function(e){"
        "var tr=e.target.closest('tr');if(tr&&tr.dataset.cid){_click(tr,e);}});"
        "window.addEventListener('load',function(){window.pycmd('search:');});"
        "})();</script>"
    )


def _row_data(col, cids):
    rows = []
    for cid in cids:
        try:
            card = col.get_card(cid)
        except Exception:
            continue
        note = card.note()
        model = note.note_type()
        sf = model.get("sortf", 0)
        sort = note.fields[sf] if sf < len(note.fields) else (note.fields[0] if note.fields else "")
        rows.append((cid, sort, col.decks.name(card.did), card.due))
    return rows


def _rows_html(rows) -> str:
    out = []
    for cid, sort, deck, due in rows:
        text = html.escape(_TAG_STRIP.sub("", sort))[:200]
        out.append(
            f"<tr class='browser-row' data-cid='{cid}'>"
            f"<td>{text}</td><td>{html.escape(deck)}</td><td>{due}</td></tr>")
    return "".join(out)


def _detail_html(col, cid) -> str:
    card = col.get_card(cid)
    note = card.note()
    model = note.note_type()
    flds = "".join(
        f"<div class='fld'><div class='fldname'>{html.escape(f['name'])}</div>"
        f"<div class='fldval'>{note.fields[i]}</div></div>"
        for i, f in enumerate(model["flds"]))
    tags = html.escape(" ".join(note.tags))
    return (f"<div class='detail-meta'><b>Deck:</b> {html.escape(col.decks.name(card.did))}"
            f" &nbsp; <b>Tags:</b> {tags}</div>{flds}")


def make_browser_handler(service, hub):
    """Bridge handler for the 'browser' context."""
    async def _do_search(query: str):
        def run(col):
            try:
                cids = list(col.find_cards(query or ""))
            except Exception:
                return None, ""
            return cids, _rows_html(_row_data(col, cids[:_LIMIT]))
        cids, rows_html = await service.run(run)
        if cids is None:
            await hub.push_call("browser", "ankiwebSetRows",
                                ["<tr><td colspan='3'>invalid search</td></tr>", 0])
            return
        hub.ui_state.browser_open = True
        hub.ui_state.last_browse_query = query
        hub.ui_state.matched_card_ids = cids
        await hub.push_call("browser", "ankiwebSetRows", [rows_html, len(cids)])

    async def _reload():
        await _do_search(hub.ui_state.last_browse_query or "")
        await hub.push_call("browser", "ankiwebSetDetail", [""])

    def _nids(col, cids):
        out = []
        for c in cids:
            try:
                nid = col.get_card(c).nid
            except Exception:
                continue
            if nid not in out:
                out.append(nid)
        return out

    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "search":
            await _do_search(rest)
        elif cmd == "searchdeck":
            name = await service.run(lambda col: col.decks.name(int(rest)))
            await _do_search(f'deck:"{name}"')
        elif cmd == "searchtag":
            await _do_search(f'tag:"{rest}"')
        elif cmd == "refresh":
            await _do_search(hub.ui_state.last_browse_query or "")
        elif cmd in ("select", "open"):
            cids = [int(c) for c in rest.split(",") if c] if cmd == "select" else [int(rest)]

            def _resolve(col):
                ns = _nids(col, cids)
                is_io = bool(
                    len(cids) == 1 and ns
                    and col.models.get(col.get_note(ns[0]).mid).get("originalStockKind") == 6)
                return ns, is_io

            nids, is_io = await service.run(_resolve)
            hub.ui_state.selected_card_ids = cids
            hub.ui_state.selected_note_ids = nids
            if len(cids) == 1 and nids:
                src = f"/image-occlusion/{nids[0]}" if is_io else f"/edit?nid={nids[0]}"
                detail = f"<iframe class='editor-frame' src='{src}'></iframe>"
            else:
                detail = ""
            await hub.push_call("browser", "ankiwebSetDetail", [detail])
        elif cmd in ("suspend", "unsuspend", "forget", "delete"):
            cids = list(hub.ui_state.selected_card_ids or [])
            if cids:
                if cmd == "suspend":
                    await service.run_op(lambda col: col.sched.suspend_cards(cids),
                                         initiator="browser")
                elif cmd == "unsuspend":
                    await service.run_op(lambda col: col.sched.unsuspend_cards(cids),
                                         initiator="browser")
                elif cmd == "forget":
                    await service.run_op(lambda col: col.sched.schedule_cards_as_new(cids),
                                         initiator="browser")
                else:
                    await service.run_op(lambda col: col.remove_notes(_nids(col, cids)),
                                         initiator="browser")
                hub.ui_state.selected_card_ids = []
                hub.ui_state.selected_note_ids = []
                await _reload()
        elif cmd == "setdue":
            cids = list(hub.ui_state.selected_card_ids or [])
            if cids and rest:
                await service.run_op(lambda col: col.sched.set_due_date(cids, rest),
                                     initiator="browser")
                await _reload()
        elif cmd == "changedeck":
            cids = list(hub.ui_state.selected_card_ids or [])
            if cids and rest:
                await service.run_op(lambda col: col.set_deck(cids, col.decks.id(rest)),
                                     initiator="browser")
                await _reload()
        elif cmd == "changenotetype":
            cids = list(hub.ui_state.selected_card_ids or [])
            nids = list(hub.ui_state.selected_note_ids or [])
            if not nids and cids:
                nids = await service.run(lambda col: _nids(col, cids))
            if nids:
                try:
                    old = await service.run(
                        lambda col: col.models.get_single_notetype_of_notes(nids))
                except Exception:
                    return None
                await hub.push_call("browser", "ankiwebNavigate",
                                    ["/change-notetype/" + str(old)])
        elif cmd in ("addtag", "removetag"):
            cids = list(hub.ui_state.selected_card_ids or [])
            if cids and rest:
                def tag(col):
                    nids = _nids(col, cids)
                    if cmd == "addtag":
                        return col.tags.bulk_add(nids, rest)
                    return col.tags.bulk_remove(nids, rest)
                await service.run_op(tag, initiator="browser")
                await _reload()
        return None

    return handler
