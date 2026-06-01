# ankiweb Plan D4 — Editor Integration (embed in Browser + reviewer Edit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the D3 editor reachable and live from the UI: single-selecting a row in the Browser embeds the live editor for that note (edits update the row in place), and the reviewer gains an Edit action (`e`) that opens the editor for the current card's note.

**Architecture:** The Browser's `#detail` pane becomes an `<iframe src="/edit?nid=X">` on single-select (the iframe is its own `editor` WS context — D3 unchanged). The blocker is that an editor field-save broadcasts `opchanges`, which the parent Browser's generic `anki-opchanges` handler turns into a full `location.reload()` — killing the iframe. Fix: a small, backward-compatible opt-out in `bootstrap.ts` — if a screen sets `window.__ankiwebOnOpchanges`, it is called instead of the default reload. The Browser sets it to re-run its search in place (`pycmd("refresh")` → re-push rows only, leaving the iframe). The reviewer gets an `edit` command (`e` key) → navigate to `/edit?nid=<current note>`.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, D1–D3 (browser + editor), the shell build (`node tools/build_shell.mjs`, verified working — node v23 + esbuild present), pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is D4 of Sub-project D.** Spec: `docs/superpowers/specs/2026-06-01-ankiweb-browser-editor-design.md`. Builds on D1/D2 (`browser.py`), D3 (`/edit`, `editor.py`), Plan 4 (reviewer shortcuts). **Deferred to D5 (documented):** Add-Note dialog (draft + deck/notetype pickers + flush-on-add), image paste/upload endpoint, and making `guiAddCards`/`guiEditNote`/`guiAddNoteSetData`/`guiBrowse`-reorder faithful against the live editor. D4 is the *editing* integration only.

**Grounded facts:** `bootstrap.ts` `anki-opchanges` listener (bootstrap.ts:30-36): `if (detail.initiator !== ctx && (flags.study_queues||flags.deck||flags.card||flags.note)) location.reload()`. The shell builds via `node tools/build_shell.mjs` → `ankiweb/shell/static/bootstrap.js` (`tests/test_shell_build.py` asserts the output exists + contains markers). The browser handler (D2) already has `_do_search(query)` (pushes `ankiwebSetRows` only, leaves `#detail`), `select:`/`open:` (mirror `ui_state.selected_*`, push `ankiwebSetDetail`), and `ui_state.last_browse_query`. The editor `/edit?nid=` route + `editor` context exist (D3). The reviewer handler (`make_reviewer_handler`) has `session.card` (a `Card`; `.nid` is the note id) and its `reviewer_page_body` inline script has a `keydown` handler (Plan 4) with a `_side` flag. `service.run`/`hub.push_call` as usual. iframe to `/edit` is same-origin (served by the same app) → loads fine; the iframe runs its own `editor` WS context.

---

## File Structure

| File | Responsibility |
|---|---|
| `shell_src/bootstrap.ts` (modify) + rebuild → `ankiweb/shell/static/bootstrap.js` | `__ankiwebOnOpchanges` opt-out before the default reload |
| `ankiweb/screens/browser.py` (modify) | single-select detail = editor iframe; `refresh` verb; set `__ankiwebOnOpchanges` |
| `ankiweb/screens/reviewer.py` (modify) | `edit` handler verb → navigate `/edit?nid`; `e` key in the keydown handler |
| `tests/test_browser.py` (modify) | update detail asserts (iframe); `refresh` test |
| `tests/test_reviewer.py` / `tests/test_screen_routes.py` (modify/append) | reviewer `edit` WS test |
| `tests/test_shell_build.py` (append) | assert `__ankiwebOnOpchanges` in bootstrap.js |
| `tests/test_editor_integration.py` (append) | Playwright: browser select → embedded editor; reviewer `e` → /edit |

---

## Task 1: Embed the editor in the Browser pane + opchanges opt-out

**Files:** Modify `shell_src/bootstrap.ts` (+ rebuild), `ankiweb/screens/browser.py`; Test: `tests/test_browser.py`, `tests/test_shell_build.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_shell_build.py` (READ it first to match its style — it reads `ankiweb/shell/static/bootstrap.js`):
```python
def test_bootstrap_has_opchanges_optout():
    from pathlib import Path
    js = Path("ankiweb/shell/static/bootstrap.js").read_text()
    assert "__ankiwebOnOpchanges" in js
```

In `tests/test_browser.py`, the D1/D2 detail tests assert the read-only fields. D4 replaces single-select detail with the editor iframe — UPDATE those assertions. Change `test_browse_open_pushes_detail_and_selection` and `test_select_one_pushes_detail` so the detail assert becomes the iframe (keep the `ui_state` assertions). Concretely, replace their detail-content asserts with:
```python
        # D4: single-select embeds the live editor iframe (not read-only fields)
        assert "iframe" in detail and "/edit?nid=" in detail
```
And add a new test for the `refresh` verb:
```python
def test_browse_refresh_repushes_rows(client):
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "search:dog"})
        _drain_call(ws, "ankiwebSetRows")
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "refresh"})
        args = _drain_call(ws, "ankiwebSetRows")
        assert "dog" in args[0]            # re-ran the last query; rows only (no detail push)
```
(For `test_browse_open_pushes_detail_and_selection`, the `open:<cid>` path also now pushes an iframe; update its detail assert the same way. The `open` arg carries a card id; the handler resolves the note id for `/edit?nid=`.)

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_shell_build.py::test_bootstrap_has_opchanges_optout tests/test_browser.py -k "open or select_one or refresh" -v` → FAIL.

- [ ] **Step 3: Modify `shell_src/bootstrap.ts`** — replace the `anki-opchanges` listener with the opt-out version:
```typescript
// Cross-screen refresh: a screen may set window.__ankiwebOnOpchanges to handle this
// itself (e.g. the Browser re-searches in place to keep an embedded editor iframe alive);
// otherwise reload when another screen's op changed our data.
window.addEventListener("anki-opchanges", (e: Event) => {
  const detail = (e as CustomEvent).detail;
  const flags = detail.flags || {};
  if (detail.initiator === ctx) return;            // skip our own changes
  const custom = (window as any).__ankiwebOnOpchanges;
  if (typeof custom === "function") {
    custom(detail);
    return;
  }
  if (flags.study_queues || flags.deck || flags.card || flags.note) {
    location.reload();
  }
});
```
Then REBUILD: `node tools/build_shell.mjs` (regenerates `ankiweb/shell/static/bootstrap.js`).

- [ ] **Step 4: Modify `ankiweb/screens/browser.py`**

(a) In `_STYLE`, widen the detail pane and style the iframe — add before `</style>`:
```python
    "#detail{width:46%}"
    ".editor-frame{width:100%;height:78vh;border:0}"
```
(the existing `#detail{width:280px;...}` rule stays; the later `#detail{width:46%}` overrides the width — or edit the existing rule to `width:46%`. Make the detail pane wide enough for the editor.)

(b) Change the `select:`/`open:` branch so a SINGLE selection pushes the editor iframe instead of read-only fields (multi/zero → empty):
```python
        elif cmd in ("select", "open"):
            cids = [int(c) for c in rest.split(",") if c] if cmd == "select" else [int(rest)]

            def fn(col):
                return _nids(col, cids)
            nids = await service.run(fn)
            hub.ui_state.selected_card_ids = cids
            hub.ui_state.selected_note_ids = nids
            detail = (f"<iframe class='editor-frame' src='/edit?nid={nids[0]}'></iframe>"
                      if len(cids) == 1 and nids else "")
            await hub.push_call("browser", "ankiwebSetDetail", [detail])
```
(c) Add a `refresh` verb (re-run the last query, push rows only — leaves `#detail`/the iframe):
```python
        elif cmd == "refresh":
            await _do_search(hub.ui_state.last_browse_query or "")
```
(d) In `render_browser_html`'s inline `<script>` IIFE, register the opchanges opt-out so an editor save re-searches in place instead of reloading the page. Add right after `var b=window.__ankiwebBridge;`:
```javascript
"window.__ankiwebOnOpchanges=function(){window.pycmd('refresh');};"
```

- [ ] **Step 5: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_browser.py tests/test_shell_build.py -v`, then `conda run -n ankiweb python -m pytest tests/test_screen_routes.py tests/test_reviewer.py tests/test_editor.py -q` (no regression).

- [ ] **Step 6: Commit**
```bash
git add shell_src/bootstrap.ts ankiweb/shell/static/bootstrap.js ankiweb/screens/browser.py tests/test_browser.py tests/test_shell_build.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(browser): embed the live editor on single-select + opchanges opt-out"
```

## Context
Single-selecting a row now embeds `<iframe src="/edit?nid=X">` (the real D3 editor) in the Browser's `#detail` pane. Because an editor field-save broadcasts `opchanges` (which would `location.reload()` the parent and kill the iframe), `bootstrap.ts` now calls a screen-provided `window.__ankiwebOnOpchanges` instead of the default reload; the Browser sets it to `pycmd("refresh")`, which re-runs the last search and re-pushes ONLY the rows (the `#detail` iframe survives, and the edited row's sort field updates live). Backward-compatible: screens that don't set the hook keep the default reload.

## Report Format
Status, pytest summaries, files changed (incl. the rebuilt bootstrap.js), self-review, commit SHA, concerns.

---

## Task 2: Reviewer Edit action

**Files:** Modify `ankiweb/screens/reviewer.py`; Test: `tests/test_screen_routes.py` (append).

- [ ] **Step 1: Write the failing test** — append to `tests/test_screen_routes.py` (mirror its reviewer WS tests: seed a card, set current deck, connect `/ws?context=reviewer`, send `show`, drain, then `edit`):
```python
def test_reviewer_edit_navigates_to_editor(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    nid = client.portal.call(client.app.state.service.run, lambda col: list(col.find_notes(""))[0])
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        ws.receive_json(); ws.receive_json()          # drain the show pushes
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "edit"})
        m = ws.receive_json()
        while m["type"] != "call" or m["fn"] != "ankiwebNavigate":
            m = ws.receive_json()
        assert m["args"] == [f"/edit?nid={nid}"]
```
Also append a unit assert to `tests/test_reviewer.py` that the keydown handler maps `e`:
```python
def test_reviewer_body_has_edit_shortcut():
    from ankiweb.screens.reviewer import reviewer_page_body
    body = reviewer_page_body()
    assert "'edit'" in body or '"edit"' in body    # the e-key -> pycmd('edit')
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_screen_routes.py::test_reviewer_edit_navigates_to_editor tests/test_reviewer.py::test_reviewer_body_has_edit_shortcut -v` → FAIL.

- [ ] **Step 3: Modify `ankiweb/screens/reviewer.py`**

(a) Add an `edit` branch to `make_reviewer_handler`'s `handler` (BEFORE the `decks` branch, alongside `starttimer`/`replay`):
```python
        elif arg == "edit":
            if session.card is not None:
                nid = await service.run(lambda col: session.card.nid)
                await hub.push_call("reviewer", "ankiwebNavigate", ["/edit?nid=" + str(nid)])
```
(b) In `reviewer_page_body`'s inline `keydown` handler (Plan 4), add an `e` mapping. The existing chain ends with the `r`/`R`/`F5` → replay branch; add another `else if`:
```javascript
"  else if(k==='e'||k==='E'){e.preventDefault();window.pycmd('edit');}"
```
(insert it inside the keydown handler's `if/else if` chain — e.g. right after the replay branch and before the closing `});`. The `typeans`-focus guard at the top already prevents `e` from firing while typing in a field.)

- [ ] **Step 4: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_reviewer.py tests/test_screen_routes.py -v`.

- [ ] **Step 5: Commit**
```bash
git add ankiweb/screens/reviewer.py tests/test_reviewer.py tests/test_screen_routes.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(reviewer): Edit action (e) opens /edit for the current note"
```

## Context
The reviewer's `e` key (guarded against the typeans input by Plan 4's handler) sends `pycmd("edit")`; the handler resolves the current card's note id and navigates to `/edit?nid=<nid>`. (Anki opens a modal editor; navigating to `/edit` is the web v1 — browser-back returns to the reviewer, which re-shows the question with the edited content. A modal/overlay editor is a later refinement.)

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 3: Playwright — edit from the Browser pane + reviewer Edit

**Files:** Append to `tests/test_editor_integration.py`.

- [ ] **Step 1: Write the tests** — reuse the D3 `live_server_edit` fixture (it seeds a `CapitalFrance`/`Paris` note and yields `(url, nid)`) and add a Browser-seeded fixture. Append inline `sync_playwright` tests (NO `page` fixture). Note: the editor's contenteditables live in custom-element SHADOW ROOTS — use a deep-walk to read text (mirror D3's `test_editor_mounts_and_loads`):
```python
_DEEP_TEXT = """
() => {
  function walk(root, acc){ root.querySelectorAll('*').forEach(function(el){
    if (el.shadowRoot) walk(el.shadowRoot, acc);
    if (el.isContentEditable) acc.push(el.textContent);
  }); }
  const acc=[]; walk(document, acc); return acc.join(' || ');
}
"""


def test_browse_single_select_embeds_editor(live_server_edit):
    url, nid = live_server_edit
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page()
        page.goto(f"{url}/browse")
        page.wait_for_function(
            "document.getElementById('results-body').children.length>=1", timeout=6000)
        page.locator(".browser-row").first.click()           # single-select -> embed editor
        page.wait_for_selector("#detail iframe.editor-frame", timeout=6000)
        frame = page.frame_locator("#detail iframe.editor-frame")
        # the editor inside the iframe mounts and loads the note's field
        page.wait_for_function(
            "() => { const f=document.querySelector('#detail iframe'); "
            "return f && f.contentDocument && f.contentDocument.querySelector('.note-editor')!==null; }",
            timeout=8000)
        browser.close()


def test_reviewer_e_opens_editor(live_server_edit):
    url, nid = live_server_edit
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page()
        page.goto(f"{url}/reviewer")
        page.wait_for_function(
            "document.getElementById('qa').textContent.includes('CapitalFrance')", timeout=8000)
        page.keyboard.press("e")
        page.wait_for_url("**/edit?nid=*", timeout=6000)
        browser.close()
```
(If `frame_locator` proves awkward, the `wait_for_function` reaching into `iframe.contentDocument` for `.note-editor` is the load-bearing assertion — keep that. The D3 `live_server_edit` fixture seeds exactly one card, so the reviewer shows it and `/browse` lists it.)

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_editor_integration.py -v` (PASS if chromium available; SKIPS if not). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_editor_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(editor): Playwright — embedded browser editor + reviewer Edit"
```

## Context
End-to-end proof of the editing integration in a real browser: single-selecting a Browser row embeds the editor iframe and the editor mounts+loads the note inside it (no parent reload — the `__ankiwebOnOpchanges` opt-out keeps the iframe alive); and the reviewer `e` key navigates to `/edit` for the current note.

## Report Format
Status, pytest summary (Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (D4 = editor integration for editing):** embed the live editor in the Browser pane on single-select (Task 1); the `bootstrap.ts` opt-out so the embedded editor's saves refresh rows in place instead of reloading (Task 1); reviewer `e` → `/edit` (Task 2); Playwright e2e for both (Task 3). Deferred to D5 (documented): Add-Note dialog, image paste/upload, `guiAddCards`/`guiEditNote`/`guiAddNoteSetData`/`guiBrowse`-reorder fidelity.

**2. Placeholder scan:** No TBD/TODO. The iframe is recreated per single-select (editor.js is cached after first load, so subsequent loads are cheap); a persistent-iframe + cross-frame load message is a later refinement. The reviewer Edit navigates (full page) rather than a modal — a documented v1.

**3. Type/name consistency:** `bootstrap.ts` adds the `window.__ankiwebOnOpchanges` hook (checked before the default reload) — REBUILT into `bootstrap.js` via `node tools/build_shell.mjs`. Browser: single-select detail = `<iframe class='editor-frame' src='/edit?nid=N'>`; new `refresh` verb = `_do_search(last_browse_query)` (rows only); the inline script sets `__ankiwebOnOpchanges = ()=>pycmd('refresh')`. Reviewer: new `edit` handler verb → `ankiwebNavigate('/edit?nid='+session.card.nid)`; `e` key in the Plan-4 keydown handler (guarded against `#typeans`). Reuses D3's `/edit` route + `editor` context unchanged. `session.card.nid` verified (Card has `.nid`).

**4. Risks & mitigations:** the iframe-vs-reload conflict is the core risk — solved by the `__ankiwebOnOpchanges` opt-out (Browser re-searches in place; verified by the Task 3 Playwright test which would fail if the iframe were destroyed on a field save). Two WS contexts coexist (parent `browser` + iframe `editor`) — independent handlers, fine for single-user; `ui_state.current_screen` flip-flops between them (cosmetic; only affects gui* nav, addressed in D5). `ankiwebSetRows` on refresh clears the selection highlight (the iframe/editor survives) — minor cosmetic. The `bootstrap.ts` change is backward-compatible (screens without the hook keep the default reload), so deckbrowser/overview/reviewer are unaffected; `test_shell_build` + the existing Playwright reviewer/browser tests confirm no regression after the rebuild.
