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
    "#detail{width:280px;padding:6px;border-left:1px solid #ccc}"
    "#detail .fldname{font-weight:bold;color:#888;font-size:11px;margin-top:6px}"
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
        "<span id='browser-status'></span></div>"
        "<div id='browser-main'>"
        f"<div id='sidebar'>{_sidebar_html(col)}</div>"
        "<div id='results-wrap'><table id='results'>"
        "<thead><tr><th>Sort Field</th><th>Deck</th><th>Due</th></tr></thead>"
        "<tbody id='results-body'></tbody></table></div>"
        "<div id='detail'></div>"
        "</div></div>"
        "<script>(function(){"
        "var b=window.__ankiwebBridge;"
        "b.registerCalls({"
        "ankiwebSetRows:function(h,n){"
        "document.getElementById('results-body').innerHTML=String(h);"
        "document.getElementById('browser-status').textContent=(n||0)+' cards';},"
        "ankiwebSetDetail:function(h){document.getElementById('detail').innerHTML=String(h);}"
        "});"
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
            f"<tr class='browser-row' onclick=\"window.pycmd('open:{cid}')\">"
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

    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "search":
            await _do_search(rest)
        elif cmd == "searchdeck":
            name = await service.run(lambda col: col.decks.name(int(rest)))
            await _do_search(f'deck:"{name}"')
        elif cmd == "searchtag":
            await _do_search(f'tag:"{rest}"')
        elif cmd == "open":
            cid = int(rest)

            def fetch(col):
                return _detail_html(col, cid), col.get_card(cid).nid
            detail, nid = await service.run(fetch)
            hub.ui_state.selected_card_ids = [cid]
            hub.ui_state.selected_note_ids = [nid]
            await hub.push_call("browser", "ankiwebSetDetail", [detail])
        return None

    return handler
