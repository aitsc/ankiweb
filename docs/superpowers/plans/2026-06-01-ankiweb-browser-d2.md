# ankiweb Plan D2 — Browser Selection + Bulk Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-select (click / ctrl-click / shift-range) to the D1 Browser table and a toolbar of bulk actions — Suspend, Unsuspend, Forget, Set Due, Change Deck, Delete, Add Tag, Remove Tag — each a thin wrapper over the existing collection ops, broadcasting so other screens refresh. Selection is mirrored into `hub.ui_state` so the B4 `guiSelectCard`/`guiSelectedNotes` become faithful.

**Architecture:** Pure extension of D1's `ankiweb/screens/browser.py`. The results rows gain `data-cid` and a delegated click handler that maintains a client-side selection (`_sel`) with ctrl-toggle / shift-range, highlights selected rows, and sends `select:<cid,cid,…>` to the server (which mirrors it into `ui_state` and pushes the single-selection detail). A toolbar issues action commands (`suspend`/`unsuspend`/`forget`/`delete`/`setdue:<spec>`/`changedeck:<name>`/`addtag:<t>`/`removetag:<t>`); the handler runs the op via `service.run_op` (broadcasts) on `ui_state.selected_card_ids` (card ops) or their notes (note ops), then reloads the current search. No new screen/route — same `browser` context.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, D1's browser screen + the B2/B3 op layer, pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is D2 of Sub-project D.** Spec: `docs/superpowers/specs/2026-06-01-ankiweb-browser-editor-design.md`. Builds on D1 (`browser.py`). Next: D3 (editor reuse), D4 (add/edit + gui* wiring).

**Grounded anki 25.9.4 facts (verified live):** all action ops return OpChanges or an OpChanges* wrapper, and `CollectionService.run_op` already unwraps via `getattr(result, "changes", result)` + broadcasts: `col.sched.suspend_cards(ids)→OpChangesWithCount`, `unsuspend_cards(ids)→OpChanges`, `schedule_cards_as_new(card_ids)→OpChanges`, `set_due_date(card_ids, days:str)→OpChanges`, `col.set_deck(card_ids, deck_id:int)→OpChangesWithCount` (sets `browser_table`/`card`/`study_queues` flags), `col.remove_notes(note_ids)→OpChangesWithCount`, `col.tags.bulk_add(note_ids, tags:str)`/`bulk_remove(...)→OpChangesWithCount`. `col.decks.id(name)` get-or-creates the deck (matches AnkiConnect `changeDeck`). A suspended card has `card.queue == -1` (QUEUE_TYPE_SUSPENDED). `run_op` broadcasts to ALL connected contexts (so the test's browser WS receives an `{type:opchanges}` frame before the reload pushes — drain past it).

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/screens/browser.py` (modify) | rows gain `data-cid`; inline script gains selection + toolbar JS; handler gains `select:` + the action verbs + a `_reload` helper |
| `tests/test_browser.py` (append) | WS tests: select→suspend, delete, changedeck, addtag/removetag, setdue |
| `tests/test_browser_integration.py` (append) | Playwright multi-select + action |

---

## Task 1: Selection + bulk-action handlers

**Files:** Modify `ankiweb/screens/browser.py`; Test: `tests/test_browser.py` (append).

- [ ] **Step 1: Write the failing tests (append to `tests/test_browser.py`)**
```python
def _run(client, fn):
    return client.portal.call(client.app.state.service.run, fn)


def test_select_then_suspend(client):
    hub = client.app.state.hub
    cids = _run(client, lambda col: list(col.find_cards("")))
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser",
                      "arg": "select:" + ",".join(str(c) for c in cids)})
        _drain_call(ws, "ankiwebSetDetail")          # 2 selected -> empty detail
        assert hub.ui_state.selected_card_ids == cids
        assert len(hub.ui_state.selected_note_ids) == 2
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "suspend"})
        _drain_call(ws, "ankiwebSetRows")            # reload (tolerates the opchanges frame)
    assert all(_run(client, lambda col, c=c: col.get_card(c).queue) == -1 for c in cids)


def test_select_one_pushes_detail(client):
    cid = _run(client, lambda col: list(col.find_cards("dog"))[0])
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        detail = _drain_call(ws, "ankiwebSetDetail")[0]
        assert "DOG" in detail


def test_delete_removes_notes(client):
    cid = _run(client, lambda col: list(col.find_cards("dog"))[0])
    before = _run(client, lambda col: len(col.find_notes("")))
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        _drain_call(ws, "ankiwebSetDetail")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "delete"})
        _drain_call(ws, "ankiwebSetRows")
    assert _run(client, lambda col: len(col.find_notes(""))) == before - 1


def test_changedeck_moves_card(client):
    cid = _run(client, lambda col: list(col.find_cards("dog"))[0])
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        _drain_call(ws, "ankiwebSetDetail")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "changedeck:Spanish"})
        _drain_call(ws, "ankiwebSetRows")
    did = _run(client, lambda col: col.get_card(cid).did)
    assert did == _run(client, lambda col: col.decks.id("Spanish"))


def test_add_and_remove_tag(client):
    cid = _run(client, lambda col: list(col.find_cards("dog"))[0])
    nid = _run(client, lambda col: col.get_card(cid).nid)
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        _drain_call(ws, "ankiwebSetDetail")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "addtag:marked"})
        _drain_call(ws, "ankiwebSetRows")
    assert "marked" in _run(client, lambda col: col.get_note(nid).tags)
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        _drain_call(ws, "ankiwebSetDetail")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "removetag:marked"})
        _drain_call(ws, "ankiwebSetRows")
    assert "marked" not in _run(client, lambda col: col.get_note(nid).tags)


def test_setdue_runs(client):
    cid = _run(client, lambda col: list(col.find_cards("dog"))[0])
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        _drain_call(ws, "ankiwebSetDetail")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "setdue:0"})
        _drain_call(ws, "ankiwebSetRows")            # reload pushed, no crash
```
(The D1 `_seed` already creates a "Spanish" deck? It does NOT — D1's fixture only adds cards to Default. **Update the D1 `_seed` in this file to also create the Spanish deck:** add `col.decks.id("Spanish")` at the end of `_seed`.)

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_browser.py -k "select or delete or changedeck or tag or setdue" -v` → FAIL.

- [ ] **Step 3: Implement (modify `ankiweb/screens/browser.py`)**

(a) Add `.selected` styling — in `_STYLE`, add this rule (before the closing `</style>`):
```python
    "#results tr.selected{background:#cde}"
```

(b) `_rows_html` — give each row `data-cid` and DROP the inline `onclick` (selection is now handled by a delegated listener):
```python
def _rows_html(rows) -> str:
    out = []
    for cid, sort, deck, due in rows:
        text = html.escape(_TAG_STRIP.sub("", sort))[:200]
        out.append(
            f"<tr class='browser-row' data-cid='{cid}'>"
            f"<td>{text}</td><td>{html.escape(deck)}</td><td>{due}</td></tr>")
    return "".join(out)
```

(c) `render_browser_html` — add an action toolbar and the selection/action JS. Replace the `#browser-top` block to include the toolbar, and replace the inline `<script>` with the extended version:
```python
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
```

(d) `make_browser_handler` — add a `_reload` helper, the `select:` branch, and the action branches. Keep the existing `search:`/`searchdeck:`/`searchtag:`/`open:` branches. The full handler becomes:
```python
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

    def _selected(col):
        return list(hub.ui_state.selected_card_ids or [])

    def _selected_nids(col, cids):
        nids = []
        for c in cids:
            try:
                nid = col.get_card(c).nid
            except Exception:
                continue
            if nid not in nids:
                nids.append(nid)
        return nids

    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "search":
            await _do_search(rest)
        elif cmd == "searchdeck":
            name = await service.run(lambda col: col.decks.name(int(rest)))
            await _do_search(f'deck:"{name}"')
        elif cmd == "searchtag":
            await _do_search(f'tag:"{rest}"')
        elif cmd in ("select", "open"):
            cids = [int(c) for c in rest.split(",") if c] if cmd == "select" else [int(rest)]

            def fn(col):
                nids = _selected_nids(col, cids)
                detail = _detail_html(col, cids[0]) if len(cids) == 1 else ""
                return nids, detail
            nids, detail = await service.run(fn)
            hub.ui_state.selected_card_ids = cids
            hub.ui_state.selected_note_ids = nids
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
                else:  # delete the notes of the selected cards
                    def dele(col):
                        return col.remove_notes(_selected_nids(col, cids))
                    await service.run_op(dele, initiator="browser")
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
                def mv(col):
                    return col.set_deck(cids, col.decks.id(rest))   # id() get-or-creates
                await service.run_op(mv, initiator="browser")
                await _reload()
        elif cmd in ("addtag", "removetag"):
            cids = list(hub.ui_state.selected_card_ids or [])
            if cids and rest:
                def tag(col):
                    nids = _selected_nids(col, cids)
                    if cmd == "addtag":
                        return col.tags.bulk_add(nids, rest)
                    return col.tags.bulk_remove(nids, rest)
                await service.run_op(tag, initiator="browser")
                await _reload()
        return None

    return handler
```
(The `_selected` helper above is unused — omit it; shown only for orientation. Use `hub.ui_state.selected_card_ids` directly as in the action branches.)

- [ ] **Step 4: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_browser.py -v` (D1 tests + the new ones). Then `conda run -n ankiweb python -m pytest tests/test_screen_routes.py tests/test_reviewer.py tests/ankiconnect/test_gui_actions.py -q` (no regression).

- [ ] **Step 5: Commit**
```bash
git add ankiweb/screens/browser.py tests/test_browser.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(browser): multi-select + bulk actions (suspend/forget/setdue/changedeck/delete/tags)"
```

## Context
Rows carry `data-cid`; a delegated click handler maintains the client selection (`_sel`) with ctrl-toggle / shift-range, highlights `.selected`, and sends `select:<cids>` (the server mirrors it into `ui_state.selected_card_ids/note_ids` and pushes the single-selection detail). The toolbar issues action verbs; each runs the matching op (`suspend_cards`/`unsuspend_cards`/`schedule_cards_as_new`/`set_due_date`/`set_deck`/`remove_notes`/`tags.bulk_add`/`bulk_remove`) via `service.run_op` (broadcasts → all screens refresh), then `_reload`s the current search and clears the selection/detail. Card ops use `selected_card_ids`; note ops (delete/tags) use their notes. `changedeck` `col.decks.id(name)` get-or-creates the deck (matches AnkiConnect). The `select:` mirror makes B4's `guiSelectCard`/`guiSelectedNotes` reflect the live selection.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 2: Playwright multi-select + action

**Files:** Append to `tests/test_browser_integration.py`.

- [ ] **Step 1: Write the failing test** — reuse the `live_server_browse` fixture from D1 (it seeds `dogword`/`catword` in Default). Append an inline `sync_playwright` test:
```python
def test_select_all_and_suspend(live_server_browse):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{live_server_browse}/browse")
        page.wait_for_function(
            "document.getElementById('results-body').children.length>=2", timeout=6000)
        # click first row, ctrl+click second -> two selected
        rows = page.locator(".browser-row")
        rows.nth(0).click()
        rows.nth(1).click(modifiers=["Control"])
        page.wait_for_function(
            "document.querySelectorAll('#results-body tr.selected').length===2", timeout=6000)
        # Suspend the selection (no crash; rows reload and selection clears)
        page.click("#browser-actions >> text=Suspend")
        page.wait_for_function(
            "document.querySelectorAll('#results-body tr.selected').length===0", timeout=6000)
        browser.close()
```

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_browser_integration.py -v` (PASS if chromium available; SKIPS if playwright missing). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_browser_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(browser): Playwright multi-select + suspend"
```

## Context
End-to-end: load `/browse`, click + ctrl-click two rows (assert two `.selected`), click Suspend, and assert the reload clears the selection — proving the delegated selection handler, `select:` round-trip, and the action→reload path in a real browser.

## Report Format
Status, pytest summary (note Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (D2 = selection + bulk actions):** multi-select with ctrl-toggle/shift-range + highlight (Task 1 JS); the action verbs suspend/unsuspend/forget/delete/setdue/changedeck/addtag/removetag (Task 1 handler) over the existing op layer via `run_op`; `select:` mirrors `ui_state.selected_*` (upgrades B4 `guiSelectCard`/`guiSelectedNotes`); Playwright e2e (Task 2). Deferred (per spec): the real column model/`browser_row_for_id` + row state colors, reposition, change-notetype, find&replace, notes-mode — D4/later.

**2. Placeholder scan:** No TBD/TODO. The `_selected` orientation helper is explicitly omitted. `Set Due`/`Change Deck`/`Add Tag`/`Remove Tag` use `prompt()` for input (a dropdown/datepicker is D4 polish). The table doesn't yet show suspended/marked colors (needs `browser_row_for_id` — D4).

**3. Type/name consistency:** Reuses D1's `render_browser_html`/`make_browser_handler`/`_rows_html`/`_detail_html`/`_row_data`/`_sidebar_html`/`_STYLE`/`_LIMIT`. New handler verbs `select:`/`suspend`/`unsuspend`/`forget`/`delete`/`setdue:`/`changedeck:`/`addtag:`/`removetag:` via `arg.partition(":")`; new JS globals `ankiwebAct`/`ankiwebActP`; rows now `data-cid` (no inline onclick) + a delegated `#results-body` click listener; `ankiwebSetRows` clears `_sel`. All ops verified live and returned via `service.run_op` (handles OpChanges* wrappers). `col.decks.id(name)` get-or-creates.

**4. Risks:** `run_op` broadcasts to ALL contexts → the test's browser WS receives an `{type:opchanges}` frame before the reload; `_drain_call` tolerates it. Actions read `ui_state.selected_card_ids` (set by the prior `select:` cmd) — sequential WS processing guarantees order. After delete, the selected cards are gone; `_reload` re-runs the query (fresh rows) and the selection/detail are cleared. `changedeck`/`addtag` create-or-mutate via the same ops AnkiConnect uses, so behavior matches the API. The D1 `open:` branch is folded into the `select:` branch (single id) — the D1 `test_browse_open_*` test still passes (it sends `open:<cid>` → one-id selection → detail).
