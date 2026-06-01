# ankiweb Plan D1 — Browser Table (read core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only web Browser screen — search bar + results table (Sort-field / Deck / Due, capped) + a sidebar (decks/tags) + click-a-row to view the card's fields — on the existing screen/bridge pattern, writing the `hub.ui_state` mirror so the B4 `guiBrowse`/`guiSelectedNotes` reflect the live browser.

**Architecture:** A new `browser` screen exactly like `deckbrowser`/`reviewer`: a `GET /browse` route renders a server-built body (search input + server-rendered sidebar + empty results table + detail pane + an inline `registerCalls` script), and a `make_browser_handler` bridge closure dispatches `search:`/`searchdeck:`/`searchtag:`/`open:` commands — running `col.find_cards` (capped 500) and pushing rows/detail HTML via `hub.push_call`. **No mutation, no multi-select, no editor** (those are D2/D3/D4). Fixed columns computed from the note/card (NOT `browser_row_for_id`, to avoid the global active-columns state). CSS is inlined in the body (no vendored `browser.css` exists — Anki's browser is Qt).

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the existing screens/bridge/ui_state, pytest (+ Playwright like `tests/test_reviewer_integration.py`). Run via `conda run -n ankiweb ...`.

**This is D1 of Sub-project D (Browser+Editor).** Spec: `docs/superpowers/specs/2026-06-01-ankiweb-browser-editor-design.md`. Next: D2 (selection+actions), D3 (editor reuse), D4 (add/edit + gui* wiring).

**Grounded anki 25.9.4 facts (verified live):** `col.find_cards(query, order=False, reverse=False) -> Sequence[CardId]`; `find_cards("")` returns ALL cards; bad syntax raises `anki.errors.SearchError` (catch it). `col.decks.all_names_and_ids() -> Sequence[DeckNameId]` (`.name` full "A::B", `.id`). `col.decks.name(did) -> str`. `col.tags.all() -> list[str]`. `card.due`/`card.did`/`card.nid`; `note.fields` (list); `model["sortf"]` = sort-field index; `model["flds"][i]["name"]`. The screen pattern: `render_*_html(col)` (built via `service.run`), a `GET` route via `build_screen_router`, and `hub.set_handler(ctx, make_*_handler(service, hub))` via `register_screen_handlers` (both in `screens/routes.py`). Handler idiom: `cmd, _, rest = arg.partition(":")`; collection work via `service.run`/`run_op`; DOM via `hub.push_call(ctx, fn, args)`; the page's inline script does `b=window.__ankiwebBridge; b.registerCalls({...}); window.pycmd('search:')` on load. `ui_state` (on the hub, from B4) has `browser_open`/`last_browse_query`/`matched_card_ids`/`selected_card_ids`/`selected_note_ids`.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/screens/browser.py` (create) | `render_browser_html(col)` (search + sidebar + table + detail + inline CSS/script) + `make_browser_handler(service, hub)` |
| `ankiweb/screens/routes.py` (modify) | add `GET /browse` + `set_handler("browser", …)` |
| `tests/test_browser.py` (create) | TestClient route test + WS search/searchdeck/open tests |
| `tests/test_browser_integration.py` (create) | Playwright end-to-end (Task 2) |

---

## Task 1: `/browse` screen + browser bridge handler

**Files:** Create `ankiweb/screens/browser.py`; Modify `ankiweb/screens/routes.py`; Test `tests/test_browser.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_browser.py`:
```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        c.portal.call(c.app.state.service.run, _seed)
        yield c


def _seed(col):
    for q in ("dog", "cat"):
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = q; n["Back"] = q.upper()
        col.add_note(n, col.decks.id("Default"))
    col.tags.bulk_add(col.find_notes(""), "animals")


def _drain_call(ws, fn, tries=6):
    for _ in range(tries):
        m = ws.receive_json()
        if m["type"] == "call" and m["fn"] == fn:
            return m["args"]
    raise AssertionError(f"no {fn} frame")


def test_browse_route_renders(client):
    r = client.get("/browse")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="browser"' in r.text
    assert "id='results'" in r.text or 'id="results"' in r.text
    assert "id='search'" in r.text or 'id="search"' in r.text
    assert "Default" in r.text          # sidebar deck
    assert "animals" in r.text          # sidebar tag


def test_browse_search_pushes_rows_and_mirrors_ui_state(client):
    hub = client.app.state.hub
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "search:dog"})
        args = _drain_call(ws, "ankiwebSetRows")
        assert "dog" in args[0] and "cat" not in args[0]
        assert args[1] == 1               # count
    assert hub.ui_state.browser_open is True
    assert hub.ui_state.last_browse_query == "dog"
    assert len(hub.ui_state.matched_card_ids) == 1


def test_browse_searchdeck_and_searchtag(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"searchdeck:{did}"})
        rows = _drain_call(ws, "ankiwebSetRows")[0]
        assert "dog" in rows and "cat" in rows
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "searchtag:animals"})
        rows = _drain_call(ws, "ankiwebSetRows")[0]
        assert "dog" in rows and "cat" in rows


def test_browse_open_pushes_detail_and_selection(client):
    cid = client.portal.call(client.app.state.service.run, lambda col: list(col.find_cards("dog"))[0])
    hub = client.app.state.hub
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"open:{cid}"})
        detail = _drain_call(ws, "ankiwebSetDetail")[0]
        assert "DOG" in detail            # the Back field value
        assert "Front" in detail and "Back" in detail
    assert hub.ui_state.selected_card_ids == [cid]
    assert len(hub.ui_state.selected_note_ids) == 1


def test_browse_invalid_search_does_not_crash(client):
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "search:deck:((("})
        args = _drain_call(ws, "ankiwebSetRows")
        assert args[1] == 0               # invalid -> 0 count, socket survives
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_browser.py -v` → FAIL (no `/browse`, no `browser` handler).

- [ ] **Step 3: Create `ankiweb/screens/browser.py`**
```python
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
        if cids is None:   # invalid search → empty, socket survives
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
        # mutation/selection/editor are D2/D3/D4
        return None

    return handler
```

- [ ] **Step 4: Modify `ankiweb/screens/routes.py`**
1. Add the import: `from ankiweb.screens.browser import render_browser_html, make_browser_handler`.
2. In `build_screen_router`, add a route (mirror the `/overview` route):
```python
    @router.get("/browse", response_class=HTMLResponse)
    async def browse_page():
        service = get_service()
        body = await service.run(render_browser_html)
        return HTMLResponse(render_page("browser", body))
```
3. In `register_screen_handlers`, add: `hub.set_handler("browser", make_browser_handler(service, hub))`.

- [ ] **Step 5: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_browser.py -v`, then `conda run -n ankiweb python -m pytest tests/test_screen_routes.py tests/test_reviewer.py -q` (no regression).

- [ ] **Step 6: Commit**
```bash
git add ankiweb/screens/browser.py ankiweb/screens/routes.py tests/test_browser.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(browser): read-only Browser screen (search + table + sidebar + detail)"
```

## Context
The `/browse` screen reuses the deckbrowser/reviewer pattern: server-rendered body + inline `registerCalls` + a `make_browser_handler` closure. `search:`/`searchdeck:`/`searchtag:` run `col.find_cards` (capped 500, `SearchError` caught → 0 rows) and push `ankiwebSetRows`; `open:` pushes the card's fields via `ankiwebSetDetail`. The handler mirrors `hub.ui_state` (browser_open/last_browse_query/matched_card_ids/selected_*) so the B4 `guiBrowse`/`guiSelectedNotes` reflect the live browser. Fixed Sort-field/Deck/Due columns avoid the global active-columns backend state (deferred to D2/D4). CSS is inlined (Anki's browser is Qt — no vendored `browser.css`).

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 2: Playwright end-to-end for the Browser

**Files:** Create `tests/test_browser_integration.py`.

- [ ] **Step 1: Write the failing test** — mirror `tests/test_reviewer_integration.py` EXACTLY (READ it first for the `live_server` fixture shape: it seeds a card, runs uvicorn in a thread on a port, `pytest.importorskip("playwright.sync_api")`, inline `with sync_playwright()`). Use a fresh port (8127) and seed two cards:
```python
import threading
import time
import pytest
import uvicorn
from pathlib import Path
from anki.collection import Collection
from ankiweb.config import Settings
from ankiweb.app import create_app

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


@pytest.fixture
def live_server_browse(tmp_path: Path):
    col_path = tmp_path / "browse.anki2"
    col = Collection(str(col_path))
    try:
        for q in ("dogword", "catword"):
            n = col.new_note(col.models.by_name("Basic")); n["Front"] = q; n["Back"] = q.upper()
            col.add_note(n, col.decks.id("Default"))
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8127)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8127, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8127"
    server.should_exit = True; t.join(timeout=5)


def test_browse_search_and_open(live_server_browse):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{live_server_browse}/browse")
        # initial empty search loads all rows
        page.wait_for_function(
            "document.getElementById('results-body').children.length>=2", timeout=6000)
        # narrow the search
        page.fill("#search", "dogword")
        page.keyboard.press("Enter")
        page.wait_for_function(
            "document.getElementById('results-body').children.length===1", timeout=6000)
        assert "dogword" in page.inner_text("#results-body")
        # click the row -> detail pane shows the field value
        page.click(".browser-row")
        page.wait_for_function(
            "document.getElementById('detail').textContent.includes('DOGWORD')", timeout=6000)
        browser.close()
```

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_browser_integration.py -v` (PASS if chromium available; the whole module SKIPS if playwright is missing).

- [ ] **Step 3: Commit**
```bash
git add tests/test_browser_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(browser): Playwright end-to-end (search + open)"
```

## Context
End-to-end browser check mirroring `test_reviewer_integration.py`: load `/browse`, confirm rows render from the on-load empty search, narrow via the search box, and click a row to show the detail pane — proving the full `pycmd → handler → push_call → registerCalls` round-trip in a real browser.

## Report Format
Status, pytest summary (note Playwright skip/pass), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (D1 = browser read core):** `/browse` route + `browser` context (Task 1); search bar + `search:`/`searchdeck:`/`searchtag:` (Task 1); results table with fixed Sort-field/Deck/Due columns capped 500 (Task 1); sidebar decks+tags (Task 1); open-row → card-field detail (Task 1); `hub.ui_state` mirror so `guiBrowse`/`guiSelectedNotes` reflect the live browser (Task 1); end-to-end Playwright (Task 2). Deferred (per spec): multi-select, mutations, the real column model/`browser_row_for_id`, the editor — D2/D3/D4.

**2. Placeholder scan:** No TBD/TODO. The "open → detail" is read-only (the live editor is D3/D4); the detail shows raw field HTML (media `<img src>` resolves via the existing media route). The Playwright test SKIPS cleanly if playwright is absent.

**3. Type/name consistency:** `render_browser_html(col)`/`make_browser_handler(service, hub)`/`_sidebar_html`/`_row_data`/`_rows_html`/`_detail_html` (browser.py); bridge calls `ankiwebSetRows(html, count)` + `ankiwebSetDetail(html)` (server push ↔ inline registerCalls); handler verbs `search:`/`searchdeck:`/`searchtag:`/`open:` via `arg.partition(":")`; `col.find_cards`/`col.decks.all_names_and_ids`/`col.decks.name`/`col.tags.all`/`model["sortf"]`/`card.due`/`card.nid` all verified live. Route added to `build_screen_router`; handler registered in `register_screen_handlers`. `render_page("browser", body)` (no css_files — CSS is inlined).

**4. Risks:** `find_cards` with no LIMIT could return tens of thousands of ids → the row materialization is capped at 500 (`cids[:_LIMIT]`) so the single-worker executor doesn't stall; the full count is still reported and stored in `matched_card_ids` (uncapped, ids only — cheap). `SearchError` on bad syntax is caught → 0 rows, socket survives. The detail renders raw field HTML (XSS is not a concern for a single-user local app over its own collection).
