# ankiweb Plan E5 — Filtered-Deck Options Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** REBUILD Anki's "Filtered Deck" (create/edit) dialog as a server-rendered HTML form at `GET /filtered-deck` (new) / `GET /filtered-deck/{deck_id}` (edit) — the dialog is Qt-only — save via `col.sched.add_or_update_filtered_deck(...)` (which builds the deck + selects it + broadcasts), and route to it from a "Create Filtered Deck" entry (new) and from a filtered (dyn) deck's gear/Options (edit).

**Architecture:** A new server-rendered screen (same pattern as `overview`/`custom_study`): `render_filtered_deck_html(col, deck_id)` calls `col.sched.get_or_create_filtered_deck(deck_id)` (deck_id=0 → a new deck with backend defaults) and renders a `<form>` with the deck name, a "reschedule" checkbox, filter 1 (search / limit / order `<select>` populated from `col.sched.filtered_deck_order_labels()`), an optional second filter (toggled by a checkbox), the three preview-delay inputs (again/hard/good — shown only when reschedule is OFF, matching Qt), and an "allow empty" checkbox. A small inline `<script>` toggles the second-filter + preview blocks and on OK gathers the fields to JSON and `pycmd("submit:"+json)`. The `filtereddeck` WS handler re-fetches `get_or_create_filtered_deck(id)`, applies the form fields (name, allow_empty, config.reschedule, config.preview_*_secs, and 1–2 `Deck.Filtered.SearchTerm{search,limit,order}` replacing config.search_terms; clears config.delays), runs `col.sched.add_or_update_filtered_deck(deck)` via `run_op` (returns `OpChangesWithId` → broadcasts; the backend BUILDS the deck and selects it), sets it current, and `ankiwebNavigate("/overview")`; on `anki.errors.FilteredDeckError` (e.g. no cards matched + allow_empty off) it pushes `ankiwebFilteredDeckError(msg)` and stays. Launch wiring: a "Create Filtered Deck" button on the deck browser → `/filtered-deck`; the deck-browser gear (`opts:{did}`) and the overview "Options" (`opts`) become **dyn-aware** — a filtered deck routes to `/filtered-deck/{did}`, a normal deck to `/deck-options/{did}` (the E2/E4 wiring). The overview's existing Rebuild/Empty already call `rebuild_filtered_deck`/`empty_filtered_deck` — unchanged.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the server-rendered screen framework, `col.sched.get_or_create_filtered_deck`/`add_or_update_filtered_deck`/`filtered_deck_order_labels`, `anki.decks_pb2.Deck.Filtered.SearchTerm`, pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is E5 of Sub-project E** (the last screen before the deferred E6/E7). Spec: `docs/superpowers/specs/2026-06-01-ankiweb-specialized-screens-design.md`. E4 established the server-rendered-form pattern. After E5, the E sub-project's shippable screens (E1–E5) are done; E6 (import/export) + E7 (image-occlusion) remain deferred to their own specs.

**Grounded facts (live-probed + source-read against `/mnt/sda/git/tools/anki`):**
- `col.sched.get_or_create_filtered_deck(deck_id) -> FilteredDeckForUpdate` (fields `id`, `name`, `config`, `allow_empty`). deck_id=0 → a NEW deck: name auto "Filtered Deck HH:MM", allow_empty=False, config.reschedule=True, preview_again/hard/good=60/600/0, and **2 default search_terms** referencing the current deck (`deck:<cur> is:due` limit 100 order 1, `deck:<cur> is:new` limit 20 order 6).
- `col.sched.add_or_update_filtered_deck(deck: FilteredDeckForUpdate) -> OpChangesWithId` — BROADCASTS, `out.id` is the deck id, the backend **BUILDS the deck (populates cards) and SELECTS it as current** (probed: after save, `get_current_id()==out.id`, deck `dyn=1`, cards present).
- `col.sched.filtered_deck_order_labels()` → 10 labels (index = `Deck.Filtered.SearchTerm.Order` enum value 0–9): `['Oldest seen first','Random','Increasing intervals','Decreasing intervals','Most lapses','Order added','Order due','Latest added first','Ascending retrievability','Descending retrievability']`.
- `Deck.Filtered` fields: `reschedule`(bool), `search_terms`(repeated `SearchTerm{search,limit,order}`), `delays`(v1 — clear it), `preview_delay`, `preview_again_secs`, `preview_hard_secs`, `preview_good_secs`. `from anki.errors import FilteredDeckError` works. `col.sched.rebuild_filtered_deck`/`empty_filtered_deck` exist (already used by the overview).
- Launch points (Qt): NEW (deck_id 0) from Tools "Create Filtered Deck" / overview "cram" / browser "Create Filtered Deck"; EDIT from `display_options_for_deck` when `deck["dyn"]` (the gear / overview opts). Save closes the dialog (no separate rebuild — `add_or_update` builds).
- ankiweb wiring today: deck-browser gear `opts:{did}` → `/deck-options/{did}` (E2, `ankiweb/screens/deckbrowser.py:86-87`, UNCONDITIONAL — must become dyn-aware); overview `opts` → `/deck-options/{cur}` (E4, UNCONDITIONAL — must become dyn-aware); the deck browser's create area is at `deckbrowser.py:50-51` (`Create Deck` button + Stats link). Screen framework: `render_page(context, body, …)` sets `window.__ankiwebContext`; `register_screen_handlers` → `hub.set_handler(ctx, handler)`; handlers drive the page via `hub.push_call(ctx, fn, args)`; `service.run_op(fn, initiator)` broadcasts.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/screens/filtered_deck.py` (create) | `render_filtered_deck_html(col, deck_id)` (the form) + `make_filtered_deck_handler(service, hub)` (apply → `add_or_update_filtered_deck` → nav/err) |
| `ankiweb/screens/routes.py` (modify) | import; `GET /filtered-deck` + `GET /filtered-deck/{deck_id}` routes; register the `filtereddeck` handler |
| `ankiweb/screens/deckbrowser.py` (modify) | dyn-aware `opts:` branch; a "Create Filtered Deck" button → `pycmd("createfiltered")` → nav `/filtered-deck` |
| `ankiweb/screens/overview.py` (modify) | dyn-aware `opts` branch |
| `tests/test_filtered_deck.py` (create) | new/edit route render; WS create+edit save; dyn-aware gear/opts; create-filtered entry; error path |
| `tests/test_filtered_deck_integration.py` (create) | Playwright: the form renders + submitting builds the deck + navigates to /overview |

---

## Task 1: the `/filtered-deck` form screen + handler + launch wiring

**Files:** Create `ankiweb/screens/filtered_deck.py`; modify `ankiweb/screens/routes.py`, `ankiweb/screens/deckbrowser.py`, `ankiweb/screens/overview.py`; Test `tests/test_filtered_deck.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_filtered_deck.py`:
```python
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _seed(client, n=4):
    def seed(col):
        did = col.decks.id("Default")
        col.decks.set_current(did)
        for i in range(n):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = f"f{i}"; note["Back"] = f"b{i}"
            col.add_note(note, did)
        return did
    return client.portal.call(client.app.state.service.run, seed)


def _make_filtered(client, search="deck:Default", limit=10):
    def mk(col):
        import anki.decks_pb2 as dp
        g = col.sched.get_or_create_filtered_deck(0)
        g.name = "Filt"
        del g.config.search_terms[:]
        g.config.search_terms.append(
            dp.Deck.Filtered.SearchTerm(search=search, limit=limit, order=5))
        return col.sched.add_or_update_filtered_deck(g).id
    return client.portal.call(client.app.state.service.run, mk)


def _drain_for(ws, fn):
    m = ws.receive_json()
    while not (m["type"] == "call" and m["fn"] == fn):
        m = ws.receive_json()
    return m


def test_filtered_deck_new_route_renders(client):
    _seed(client)
    r = client.get("/filtered-deck")
    assert r.status_code == 200
    body = r.text
    assert 'id="name"' in body
    assert 'id="search1"' in body
    assert "Random" in body and "Order due" in body   # order labels
    assert ">Build<" in body                            # new-deck OK label


def test_filtered_deck_edit_route_renders(client):
    _seed(client)
    did = _make_filtered(client)
    r = client.get(f"/filtered-deck/{did}")
    assert r.status_code == 200
    assert "Filt" in r.text
    assert ">Rebuild<" in r.text                          # edit OK label


def test_filtered_deck_create_saves_and_navigates(client):
    _seed(client)
    payload = {"id": 0, "name": "NewFiltered", "reschedule": True,
               "search1": "deck:Default", "limit1": 10, "order1": 1,
               "second": False, "search2": "", "limit2": 20, "order2": 5,
               "preview_again": 60, "preview_hard": 600, "preview_good": 0,
               "allow_empty": False}
    with client.websocket_connect("/ws?context=filtereddeck") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "filtereddeck",
                      "arg": "submit:" + json.dumps(payload)})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == ["/overview"]
    info = client.portal.call(
        client.app.state.service.run,
        lambda col: (col.decks.by_name("NewFiltered") is not None,
                     bool(col.decks.by_name("NewFiltered")["dyn"])))
    assert info == (True, True)


def test_filtered_deck_edit_renames(client):
    _seed(client)
    did = _make_filtered(client)
    payload = {"id": did, "name": "Renamed", "reschedule": True,
               "search1": "deck:Default", "limit1": 10, "order1": 5,
               "second": False, "search2": "", "limit2": 20, "order2": 5,
               "preview_again": 60, "preview_hard": 600, "preview_good": 0,
               "allow_empty": True}
    with client.websocket_connect("/ws?context=filtereddeck") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "filtereddeck",
                      "arg": "submit:" + json.dumps(payload)})
        _drain_for(ws, "ankiwebNavigate")
    name = client.portal.call(client.app.state.service.run,
                              lambda col: col.decks.get(did)["name"])
    assert name == "Renamed"


def test_filtered_deck_error_when_no_match(client):
    _seed(client)
    payload = {"id": 0, "name": "Empty", "reschedule": True,
               "search1": "tag:__nonexistent__", "limit1": 10, "order1": 1,
               "second": False, "search2": "", "limit2": 20, "order2": 5,
               "preview_again": 60, "preview_hard": 600, "preview_good": 0,
               "allow_empty": False}
    with client.websocket_connect("/ws?context=filtereddeck") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "filtereddeck",
                      "arg": "submit:" + json.dumps(payload)})
        m = ws.receive_json()
        seen = False
        for _ in range(10):
            if m["type"] == "call" and m["fn"] == "ankiwebFilteredDeckError":
                seen = True
                break
            if m["type"] == "call" and m["fn"] == "ankiwebNavigate":
                pytest.fail("navigated despite FilteredDeckError")
            m = ws.receive_json()
        assert seen


def test_deckbrowser_gear_dyn_opens_filtered(client):
    _seed(client)
    did = _make_filtered(client)
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "deckbrowser", "arg": f"opts:{did}"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == [f"/filtered-deck/{did}"]


def test_deckbrowser_gear_normal_opens_deck_options(client):
    did = _seed(client)
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "deckbrowser", "arg": f"opts:{did}"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == [f"/deck-options/{did}"]


def test_deckbrowser_create_filtered_entry(client):
    _seed(client)
    r = client.get("/deckbrowser")
    assert "createfiltered" in r.text
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "deckbrowser", "arg": "createfiltered"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == ["/filtered-deck"]


def test_overview_opts_dyn_opens_filtered(client):
    _seed(client)
    did = _make_filtered(client)   # add_or_update selects it as current
    with client.websocket_connect("/ws?context=overview") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "overview", "arg": "opts"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == [f"/filtered-deck/{did}"]
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_filtered_deck.py -v` → FAIL.

- [ ] **Step 3: Create `ankiweb/screens/filtered_deck.py`**:
```python
from __future__ import annotations
import html
import json


def render_filtered_deck_html(col, deck_id: int) -> str:
    g = col.sched.get_or_create_filtered_deck(deck_id)
    cfg = g.config
    labels = list(col.sched.filtered_deck_order_labels())
    terms = list(cfg.search_terms)
    t0 = terms[0] if terms else None
    t1 = terms[1] if len(terms) > 1 else None
    is_edit = g.id != 0

    def order_select(sel_id: str, selected: int) -> str:
        opts = "".join(
            f"<option value='{i}'{' selected' if i == selected else ''}>{html.escape(l)}</option>"
            for i, l in enumerate(labels))
        return f"<select id='{sel_id}'>{opts}</select>"

    name = html.escape(g.name)
    search1 = html.escape(t0.search if t0 else "")
    limit1 = t0.limit if t0 else 100
    order1 = t0.order if t0 else 0
    has2 = t1 is not None
    search2 = html.escape(t1.search if t1 else "")
    limit2 = t1.limit if t1 else 20
    order2 = t1.order if t1 else 5
    resched = "checked" if cfg.reschedule else ""
    allow_empty = "checked" if g.allow_empty else ""
    second_checked = "checked" if has2 else ""
    second_disp = "" if has2 else "display:none;"
    preview_disp = "display:none;" if cfg.reschedule else ""
    oklabel = "Rebuild" if is_edit else "Build"

    body = f"""
<div class='filtered-deck'>
  <h3>{'Edit' if is_edit else 'Create'} Filtered Deck</h3>
  <form id='fd' onsubmit='return false;'>
    <input type='hidden' id='did' value='{g.id}'>
    <div><label>Name <input type='text' id='name' value="{name}" size='30'></label></div>
    <fieldset><legend>Filter</legend>
      <div><label>Search <input type='text' id='search1' value="{search1}" size='40'></label></div>
      <div><label>Limit <input type='number' id='limit1' value='{limit1}' min='1' style='width:6em;'></label>
           &nbsp; Order {order_select('order1', order1)}</div>
    </fieldset>
    <div><label><input type='checkbox' id='second' {second_checked} onchange='onSecond()'> Enable second filter</label></div>
    <fieldset id='filter2' style='{second_disp}'><legend>Second filter</legend>
      <div><label>Search <input type='text' id='search2' value="{search2}" size='40'></label></div>
      <div><label>Limit <input type='number' id='limit2' value='{limit2}' min='1' style='width:6em;'></label>
           &nbsp; Order {order_select('order2', order2)}</div>
    </fieldset>
    <div style='margin-top:8px;'><label><input type='checkbox' id='resched' {resched} onchange='onResched()'> Reschedule cards based on my answers</label></div>
    <fieldset id='previewblock' style='{preview_disp}'><legend>Preview delays (seconds)</legend>
      <label>Again <input type='number' id='preview_again' value='{cfg.preview_again_secs}' min='0' style='width:6em;'></label>
      <label>Hard <input type='number' id='preview_hard' value='{cfg.preview_hard_secs}' min='0' style='width:6em;'></label>
      <label>Good <input type='number' id='preview_good' value='{cfg.preview_good_secs}' min='0' style='width:6em;'></label>
    </fieldset>
    <div style='margin-top:8px;'><label><input type='checkbox' id='allow_empty' {allow_empty}> Create even if empty</label></div>
    <div style='margin-top:10px;'>
      <button type='button' id='go' onclick='submitFd()'>{oklabel}</button>
      <button type='button' onclick="pycmd('cancel')">Cancel</button>
    </div>
    <div id='err' style='color:#c00;margin-top:8px;'></div>
  </form>
</div>
<script>
function chk(id) {{ return document.getElementById(id).checked; }}
function val(id) {{ return document.getElementById(id).value; }}
function num(id) {{ return parseInt(document.getElementById(id).value || '0'); }}
function onSecond() {{ document.getElementById('filter2').style.display = chk('second') ? '' : 'none'; }}
function onResched() {{ document.getElementById('previewblock').style.display = chk('resched') ? 'none' : ''; }}
function submitFd() {{
  document.getElementById('err').textContent = '';
  var p = {{
    id: parseInt(val('did')), name: val('name'), reschedule: chk('resched'),
    search1: val('search1'), limit1: num('limit1'), order1: parseInt(val('order1')),
    second: chk('second'), search2: val('search2'), limit2: num('limit2'), order2: parseInt(val('order2')),
    preview_again: num('preview_again'), preview_hard: num('preview_hard'), preview_good: num('preview_good'),
    allow_empty: chk('allow_empty')
  }};
  pycmd('submit:' + JSON.stringify(p));
}}
window.ankiwebFilteredDeckError = function(msg) {{ document.getElementById('err').textContent = msg; }};
</script>
"""
    return body


def make_filtered_deck_handler(service, hub):
    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "cancel":
            await hub.push_call("filtereddeck", "ankiwebNavigate", ["/overview"])
            return None
        if cmd != "submit":
            return None
        try:
            p = json.loads(rest)
        except Exception:
            return None

        def build_and_run(col):
            import anki.decks_pb2 as dp
            g = col.sched.get_or_create_filtered_deck(int(p.get("id", 0)))
            g.name = p.get("name", g.name)
            g.allow_empty = bool(p.get("allow_empty"))
            cfg = g.config
            cfg.reschedule = bool(p.get("reschedule"))
            cfg.preview_again_secs = int(p.get("preview_again", 0))
            cfg.preview_hard_secs = int(p.get("preview_hard", 0))
            cfg.preview_good_secs = int(p.get("preview_good", 0))
            del cfg.delays[:]
            terms = [dp.Deck.Filtered.SearchTerm(
                search=p.get("search1", ""), limit=int(p.get("limit1", 100)),
                order=int(p.get("order1", 0)))]
            if p.get("second"):
                terms.append(dp.Deck.Filtered.SearchTerm(
                    search=p.get("search2", ""), limit=int(p.get("limit2", 20)),
                    order=int(p.get("order2", 5))))
            del cfg.search_terms[:]
            cfg.search_terms.extend(terms)
            out = col.sched.add_or_update_filtered_deck(g)
            col.decks.set_current(out.id)
            return out

        try:
            await service.run_op(build_and_run, initiator="filtereddeck")
        except Exception as e:
            from anki.errors import FilteredDeckError
            msg = str(e) if isinstance(e, FilteredDeckError) else "Could not build the filtered deck."
            await hub.push_call("filtereddeck", "ankiwebFilteredDeckError", [msg])
            return None
        await hub.push_call("filtereddeck", "ankiwebNavigate", ["/overview"])
        return None

    return handler
```
(NOTE: `add_or_update_filtered_deck` returns `OpChangesWithId`; `run_op` unwraps `.changes` to broadcast. The backend builds + selects the deck; we also `set_current(out.id)` for safety. On `FilteredDeckError` the op never broadcasts; we surface the message and do NOT navigate.)

- [ ] **Step 4: Wire the routes + handler** — in `ankiweb/screens/routes.py`: add `from ankiweb.screens.filtered_deck import render_filtered_deck_html, make_filtered_deck_handler`; add inside `build_screen_router` (next to `/custom-study`):
```python
    @router.get("/filtered-deck", response_class=HTMLResponse)
    async def filtered_deck_new_page():
        service = get_service()
        body = await service.run(lambda col: render_filtered_deck_html(col, 0))
        return HTMLResponse(render_page("filtereddeck", body))

    @router.get("/filtered-deck/{deck_id}", response_class=HTMLResponse)
    async def filtered_deck_edit_page(deck_id: int):
        service = get_service()
        body = await service.run(lambda col: render_filtered_deck_html(col, deck_id))
        return HTMLResponse(render_page("filtereddeck", body))
```
and register inside `register_screen_handlers`:
```python
    hub.set_handler("filtereddeck", make_filtered_deck_handler(service, hub))
```

- [ ] **Step 5: Dyn-aware gear + Create-Filtered entry** — in `ankiweb/screens/deckbrowser.py`:
  (a) replace the `opts` branch (`elif cmd == "opts": await hub.push_call("deckbrowser", "ankiwebNavigate", ["/deck-options/" + rest])`) with:
```python
        elif cmd == "opts":
            did = int(rest)
            is_dyn = await service.run(lambda col: bool(col.decks.get(did).get("dyn")))
            path = (f"/filtered-deck/{did}") if is_dyn else (f"/deck-options/{did}")
            await hub.push_call("deckbrowser", "ankiwebNavigate", [path])
        elif cmd == "createfiltered":
            await hub.push_call("deckbrowser", "ankiwebNavigate", ["/filtered-deck"])
```
  (b) in `render_deckbrowser_html`, add a Create-Filtered button to the `create` line:
```python
    create = ("<button onclick='ankiwebCreateDeck()'>Create Deck</button>"
              " <button onclick='pycmd(\"createfiltered\")'>Create Filtered Deck</button>"
              " <a href='/graphs'>Stats</a>")
```

- [ ] **Step 6: Dyn-aware overview opts** — in `ankiweb/screens/overview.py` `make_overview_handler`, replace the `opts` branch (added in E4) with:
```python
        elif arg == "opts":
            did = await service.run(lambda col: col.decks.get_current_id())
            is_dyn = await service.run(lambda col: bool(col.decks.get(did).get("dyn")))
            path = (f"/filtered-deck/{did}") if is_dyn else (f"/deck-options/{did}")
            await hub.push_call("overview", "ankiwebNavigate", [path])
```

- [ ] **Step 7: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_filtered_deck.py -v`, then regression:
`conda run -n ankiweb python -m pytest tests/test_deckbrowser.py tests/test_overview.py tests/test_custom_study.py tests/test_deck_options.py tests/test_screen_routes.py -q`.

- [ ] **Step 8: Commit**
```bash
git add ankiweb/screens/filtered_deck.py ankiweb/screens/routes.py ankiweb/screens/deckbrowser.py ankiweb/screens/overview.py tests/test_filtered_deck.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(filtered-deck): server-rendered filtered-deck create/edit form + dyn-aware gear/opts + create entry"
```

## Context
`/filtered-deck` (new) and `/filtered-deck/{id}` (edit) are server-rendered REBUILDs (the Qt dialog has no web bundle). The form (name, 1–2 search filters with order dropdowns from `filtered_deck_order_labels`, reschedule + preview delays, allow-empty) submits over the WS bridge; the `filtereddeck` handler applies the fields to a freshly-fetched `FilteredDeckForUpdate`, runs `add_or_update_filtered_deck` (which BUILDS + selects the deck + broadcasts), and navigates to `/overview` (showing the built deck) — or surfaces `FilteredDeckError` inline. The deck-browser gains a "Create Filtered Deck" button, and both the deck-browser gear and the overview "Options" become dyn-aware (filtered deck → `/filtered-deck/{id}`, normal → `/deck-options/{id}`).

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns (incl. the exact regression files used + any f-string/JS escaping or quoting issues).

---

## Task 2: Playwright — the filtered-deck form renders + builds + navigates

**Files:** Create `tests/test_filtered_deck_integration.py`.

- [ ] **Step 1: Write the test** — mirror `tests/test_custom_study_integration.py`'s `live_server` (uvicorn thread, fresh port 8134, `pytest.importorskip`, inline `sync_playwright`). Seed new cards + set the current deck. Open `/filtered-deck`; assert the form renders; set the search to `deck:Default`, submit, and assert it navigates to `/overview` and a filtered deck was created:
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
def live_server_fd(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    col = Collection(str(col_path))
    try:
        did = col.decks.id("Default")
        col.decks.set_current(did)
        for i in range(4):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"] = f"f{i}"; n["Back"] = f"b{i}"
            col.add_note(n, did)
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8134)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8134, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8134"
    server.should_exit = True
    t.join(timeout=5)


def test_filtered_deck_form_builds_and_navigates(live_server_fd):
    url = live_server_fd
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{url}/filtered-deck")
        page.wait_for_selector("#go", timeout=10000)
        assert "Filtered Deck" in page.inner_text("body")
        page.fill("#search1", "deck:Default")
        page.click("#go")
        page.wait_for_url("**/overview", timeout=10000)
        assert not errors, errors
        browser.close()
```
(NOTE: the seeded new cards match `deck:Default`, so the build succeeds and the page navigates. Load-bearing asserts: the form rendered (`#go` + "Filtered Deck" text), no page error, submit navigated to `/overview`. If a real JS error fires (f-string escaping), FIX `filtered_deck.py` and re-run the Task-1 tests.)

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_filtered_deck_integration.py -v` (PASS if chromium available; SKIPS if not). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_filtered_deck_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(filtered-deck): Playwright — the form renders, builds, and navigates to overview"
```

## Context
End-to-end proof the rebuilt filtered-deck form works in a real browser: renders the name/search/order/preview controls, submits over the WS bridge, the backend builds the filtered deck, and the page navigates to `/overview` (showing it). The edit/error/dyn-routing paths are covered by the Task-1 WS tests.

## Report Format
Status, pytest summary (Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (E5 = filtered-deck options):** server-rendered `/filtered-deck` (new) + `/filtered-deck/{id}` (edit) REBUILD with name, reschedule, 1–2 search filters (search/limit/order from `filtered_deck_order_labels`), preview delays (hidden when reschedule on), allow-empty (Task 1); submit → `add_or_update_filtered_deck` (builds + selects + broadcasts via run_op) → nav `/overview`; `FilteredDeckError` surfaced inline (Task 1, create/edit/error tested); dyn-aware gear (deckbrowser) + opts (overview) routing filtered→`/filtered-deck/{id}` vs normal→`/deck-options/{id}` (Task 1); "Create Filtered Deck" entry (Task 1); Playwright render+build+nav (Task 2). Rebuild/Empty already exist on the overview (unchanged). Deferred: the browser "Create Filtered Deck from current search" prefill (a `?search=` arg) — noted, not built.

**2. Placeholder scan:** No TBD/TODO. The inline form JS is complete (chk/val/num/onSecond/onResched/submitFd + error hook). Order labels come from the live `filtered_deck_order_labels()` (not hardcoded). Regression files named explicitly.

**3. Type/name consistency:** `render_filtered_deck_html(col, deck_id)` + `make_filtered_deck_handler(service, hub)` in `filtered_deck.py`; routes `GET /filtered-deck` (→ deck_id 0) + `GET /filtered-deck/{deck_id}` → `render_page("filtereddeck", body)`; handler registered under context `"filtereddeck"`; page connects `/ws?context=filtereddeck`; handler pushes to the same context. Submit payload keys (id/name/reschedule/search1/limit1/order1/second/search2/limit2/order2/preview_again/preview_hard/preview_good/allow_empty) match the JS `submitFd()` exactly. `add_or_update_filtered_deck` via `run_op` (unwraps `OpChangesWithId.changes`); `set_current(out.id)`; `FilteredDeckError` from `anki.errors`. deckbrowser `opts`/`createfiltered` + overview `opts` push `ankiwebNavigate`.

**4. Risks:** inline `<script>` f-string `{{`/`}}` escaping — Step 3 shows it escaped; the Playwright `pageerror` listener (Task 2) catches a JS syntax error. The `name`/`search` values use double-quoted HTML attrs (`value="..."`) since searches contain single quotes/colons (e.g. `deck:Default`) — `html.escape` covers `"`/`&`/`<`. `run_op` raising `FilteredDeckError` is caught around the call (no broadcast on failure). The dyn-aware branches do one extra `service.run` to read `dyn` — cheap. The new-deck default search references the current deck (set by tests via `set_current`); a route hit with no current deck still renders (backend default). `get_or_create_filtered_deck(int(p["id"]))` for edit re-fetches and preserves unexposed config (delays cleared, preview_delay untouched).
