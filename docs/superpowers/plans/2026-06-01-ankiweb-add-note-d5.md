# ankiweb Plan D5 — Add-Note Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An Add-Note screen at `GET /add` that reuses `editor.js` in add-mode: pick a deck + notetype, fill the fields, click "Add Note" → a new note is created in the collection; the form then resets for the next note.

**Architecture:** A new `add` screen like `/edit` (D3): `/add` serves the editor page with a deck `<select>` + notetype `<select>` + an "Add Note" button. `setupEditor("add")` mounts an empty note. **Field capture is a client-side DOM deep-read** (the spike proved `saveNow` only flushes the focused field): the Add button reads each field's current HTML from the editor's shadow-DOM contenteditables and sends `addnote:<json>`. The `make_add_handler` bridge closure tracks the chosen notetype/deck/tags, and on `addnote` builds a fresh note (`col.new_note` → set fields by ord → `check_addable` → `col.add_note`), broadcasts, then resets the form. Changing the notetype re-pushes empty fields for it.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the vendored `editor.js`, D3's editor recipe + `_munge`, the B2 `check_addable`, pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is D5 of Sub-project D.** Spec: `docs/superpowers/specs/2026-06-01-ankiweb-browser-editor-design.md`. **A spike de-risked add-mode** (`/tmp/editor_spike_addnote.py`). **Deferred to D6 (documented):** image paste/upload (editor.js intercepts paste → `bridgeCommand("paste")` with no payload → needs a client paste handler + an upload endpoint, NOT a server-side scrub), and the B4-deferred `guiAddCards`/`guiEditNote`/`guiAddNoteSetData`/`guiBrowse`-reorder fidelity.

**Grounded facts (spike + live probes):**
- Add-mode render: `setupEditor("add")` + `setFields([[name,""],…])` + `setIsImageOcclusion(false)` (MANDATORY) + `setFonts([[family,size,rtl],…])` + `setNotetypeMeta({id,modTime})` + `setNoteId(0)` (use `0`, not omitted — else `key:`/`blur:` carry the literal `"null"`) → empty editable fields (empty = `innerHTML === "<br>"`).
- **Field-capture deep-read (verified):** fields are `.field-container[data-index]`; the content is in an `[contenteditable]` inside the **shadow root** of that container's `.rich-text-editable` host. Read all fields in one synchronous pass (reflects un-blurred typed text); `saveNow` does NOT (it flushes only the focused field).
- Collection APIs (verified): `col.models.current()→NotetypeDict` (`.id`, `.flds`), `col.models.get(id)→NotetypeDict|None`, `col.models.all_names_and_ids()→[NotetypeNameId(.name,.id)]`, `col.decks.get_current_id()→DeckId`, `col.decks.all_names_and_ids()→[DeckNameId(.name,.id)]`, `col.new_note(model)→Note`, `col.add_note(note, deck_id)→OpChangesWithCount`. `check_addable(col, note, None)→(ok, err)` (rejects empty: `(False, "cannot create note because it is empty")`). `model["flds"][i]` has `name`/`font`/`size`/`rtl`. `_munge(col, html)` (from `screens/editor.py`): null-strip + drop bare `<br>`/`<div><br></div>` + `escape_media_filenames(unescape=True)`. `op_changes_to_flags` + `service.emit` broadcast.
- The editor mounts into `document.body` (Svelte `mount` APPENDS, doesn't clear) — a chrome `<div>` already in body coexists; render the chrome as a fixed top bar so the editor app (appended after) isn't obscured.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/screens/add.py` (create) | `render_add_html(col)` + `add_page_body(deck_opts, nt_opts)` + `make_add_handler(service, hub)` |
| `ankiweb/screens/routes.py` (modify) | add `GET /add` + `set_handler("add", …)` |
| `tests/test_add.py` (create) | WS tests: addReady, addnote creates, setnotetype, setdeck, saveTags, empty rejected |
| `tests/test_add_integration.py` (create) | Playwright: type fields + Add → note created (form resets) |

---

## Task 1: `/add` screen + add bridge handler

**Files:** Create `ankiweb/screens/add.py`; Modify `ankiweb/screens/routes.py`; Test `tests/test_add.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_add.py`:
```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _run(client, fn):
    return client.portal.call(client.app.state.service.run, fn)


def _drain_call(ws, fn, tries=8):
    for _ in range(tries):
        m = ws.receive_json()
        if m["type"] == "call" and m["fn"] == fn:
            return m["args"]
    raise AssertionError(f"no {fn} frame")


def test_add_route_renders(client):
    r = client.get("/add")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="add"' in r.text
    assert "/_anki/js/editor.js" in r.text
    assert "setupEditor" in r.text and "addnote:" in r.text
    assert "id='add-deck'" in r.text and "id='add-notetype'" in r.text
    assert "Default" in r.text and "Basic" in r.text     # picker options


def test_add_ready_pushes_empty_fields(client):
    with client.websocket_connect("/ws?context=add") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": "addReady"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["noteId"] == 0
        assert [f[0] for f in data["fields"]] == ["Front", "Back"]
        assert all(f[1] == "" for f in data["fields"])
        assert len(data["fonts"]) == 2


def test_addnote_creates_note(client):
    before = _run(client, lambda col: len(col.find_notes("")))
    with client.websocket_connect("/ws?context=add") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": "addReady"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": 'addnote:["Hello","World"]'})
        _drain_call(ws, "ankiwebToast")               # "Added"
    assert _run(client, lambda col: len(col.find_notes(""))) == before + 1
    note = _run(client, lambda col: col.get_note(list(col.find_notes("Hello"))[0]))
    assert note.fields == ["Hello", "World"]


def test_addnote_empty_rejected(client):
    before = _run(client, lambda col: len(col.find_notes("")))
    with client.websocket_connect("/ws?context=add") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": "addReady"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": 'addnote:["<br>",""]'})
        toast = _drain_call(ws, "ankiwebToast")[0]
        assert "empty" in toast.lower()
    assert _run(client, lambda col: len(col.find_notes(""))) == before    # nothing added


def test_setnotetype_reloads_fields(client):
    cloze_id = _run(client, lambda col: col.models.by_name("Cloze")["id"])
    with client.websocket_connect("/ws?context=add") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": "addReady"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": f"setnotetype:{cloze_id}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert "Text" in [f[0] for f in data["fields"]]   # Cloze's fields


def test_setdeck_and_tags_applied(client):
    other = _run(client, lambda col: col.decks.id("Target"))
    with client.websocket_connect("/ws?context=add") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": "addReady"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": f"setdeck:{other}"})
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": 'saveTags:["mytag"]'})
        ws.send_json({"type": "cmd", "id": None, "ctx": "add", "arg": 'addnote:["Q","A"]'})
        _drain_call(ws, "ankiwebToast")
    nid = _run(client, lambda col: list(col.find_notes("Q"))[0])
    note = _run(client, lambda col: col.get_note(nid))
    assert "mytag" in note.tags
    assert _run(client, lambda col, n=note: col.get_card(n.card_ids()[0]).did) == other
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_add.py -v` → FAIL.

- [ ] **Step 3: Create `ankiweb/screens/add.py`**
```python
from __future__ import annotations
import html
import json
from ankiweb.screens.editor import _munge
from ankiweb.ankiconnect.actions._helpers import check_addable
from ankiweb.collection_service import op_changes_to_flags

_STYLE = (
    "<style>"
    "#add-chrome{position:fixed;top:0;left:0;right:0;height:38px;display:flex;gap:8px;"
    "align-items:center;padding:4px 8px;background:#f4f4f4;border-bottom:1px solid #ccc;z-index:1000}"
    "body{padding-top:44px}"
    "#add-toast{color:#080;margin-left:8px}"
    "</style>"
)


def _empty_load(col, ntid: int) -> dict:
    model = col.models.get(ntid)
    flds = model["flds"]
    return {
        "fields": [[f["name"], ""] for f in flds],
        "fonts": [[f.get("font", "Arial"), int(f.get("size", 20)), bool(f.get("rtl", False))]
                  for f in flds],
        "io": False,
        "noteId": 0,
        "meta": {"id": model["id"], "modTime": model.get("mod", 0)},
        "tags": [],
    }


def add_page_body(deck_opts: str, nt_opts: str) -> str:
    return (
        _STYLE +
        "<div id='add-chrome'>"
        "<label>Deck <select id='add-deck' "
        "onchange=\"window.pycmd('setdeck:'+this.value)\">" + deck_opts + "</select></label>"
        "<label>Type <select id='add-notetype' "
        "onchange=\"window.pycmd('setnotetype:'+this.value)\">" + nt_opts + "</select></label>"
        "<button id='add-btn' onclick='ankiwebAddNote()'>Add Note</button>"
        "<a href='/deckbrowser'>Close</a><span id='add-toast'></span>"
        "</div>"
        "<script>(function(){"
        "window.setupEditor('add');"
        "var b=window.__ankiwebBridge;"
        "function readAllFields(){"
        "var cs=Array.prototype.slice.call(document.querySelectorAll('.field-container'));"
        "cs.sort(function(a,b){return Number(a.dataset.index)-Number(b.dataset.index);});"
        "return cs.map(function(fc){var h=fc.querySelector('.rich-text-editable');"
        "if(!h||!h.shadowRoot)return '';"
        "var e=h.shadowRoot.querySelector('[contenteditable]');return e?e.innerHTML:'';});}"
        "window.ankiwebAddNote=function(){window.pycmd('addnote:'+JSON.stringify(readAllFields()));};"
        "b.registerCalls({"
        "ankiwebLoadNote:function(d){require('anki/ui').loaded.then(function(){"
        "window.setFields(d.fields);window.setIsImageOcclusion(d.io);window.setFonts(d.fonts);"
        "window.setNotetypeMeta(d.meta);window.setNoteId(d.noteId);window.setTags(d.tags);"
        "window.triggerChanges();});},"
        "ankiwebToast:function(m){var t=document.getElementById('add-toast');if(t){"
        "t.textContent=String(m);setTimeout(function(){t.textContent='';},2000);}}"
        "});"
        "require('anki/ui').loaded.then(function(){window.pycmd('addReady');});"
        "})();</script>"
    )


def render_add_html(col) -> str:
    cur_nt = col.models.current()["id"]
    cur_did = col.decks.get_current_id()
    decks = "".join(
        f"<option value='{d.id}'{' selected' if d.id == cur_did else ''}>{html.escape(d.name)}</option>"
        for d in col.decks.all_names_and_ids())
    nts = "".join(
        f"<option value='{m.id}'{' selected' if m.id == cur_nt else ''}>{html.escape(m.name)}</option>"
        for m in col.models.all_names_and_ids())
    return add_page_body(decks, nts)


def make_add_handler(service, hub):
    state = {"notetype_id": None, "deck_id": None, "tags": []}

    async def handler(arg: str):
        head, _, rest = arg.partition(":")
        if head == "addReady":
            def init(col):
                ntid = col.models.current()["id"]
                did = col.decks.get_current_id()
                return ntid, did, _empty_load(col, ntid)
            ntid, did, data = await service.run(init)
            state.update(notetype_id=ntid, deck_id=did, tags=[])
            await hub.push_call("add", "ankiwebLoadNote", [data])
        elif head == "setnotetype":
            ntid = int(rest)
            state["notetype_id"] = ntid
            state["tags"] = []
            data = await service.run(lambda col: _empty_load(col, ntid))
            await hub.push_call("add", "ankiwebLoadNote", [data])
        elif head == "setdeck":
            state["deck_id"] = int(rest)
        elif head == "saveTags":
            state["tags"] = json.loads(rest)
        elif head == "addnote":
            fields = json.loads(rest)
            ntid, did, tags = state["notetype_id"], state["deck_id"], list(state["tags"])

            def add(col):
                model = col.models.get(ntid)
                note = col.new_note(model)
                for i, h in enumerate(fields):
                    if i < len(note.fields):
                        note.fields[i] = _munge(col, h)
                note.tags = tags
                ok, err = check_addable(col, note, None)
                if not ok:
                    return (None, err), None
                op = col.add_note(note, did)
                return (note.id, None), op
            (nid, err), op = await service.run(add)
            if op is not None:
                flags = op_changes_to_flags(getattr(op, "changes", op))
                if any(flags.values()):
                    await service.emit(flags, "add")
            if err:
                await hub.push_call("add", "ankiwebToast", [err])
            else:
                data = await service.run(lambda col: _empty_load(col, ntid))
                await hub.push_call("add", "ankiwebLoadNote", [data])     # reset for next note
                await hub.push_call("add", "ankiwebToast", ["Added"])
        # blur/key/focus/editorState ignored — fields are captured by the Add button's deep-read
        return None

    return handler
```

- [ ] **Step 4: Modify `ankiweb/screens/routes.py`**
1. Add import: `from ankiweb.screens.add import render_add_html, make_add_handler`.
2. In `build_screen_router`:
```python
    @router.get("/add", response_class=HTMLResponse)
    async def add_page():
        service = get_service()
        body = await service.run(render_add_html)
        return HTMLResponse(render_page(
            "add", body, ["css/editor.css", "css/editable.css"],
            ["js/mathjax.js", "js/editor.js"]))
```
3. In `register_screen_handlers`, add: `hub.set_handler("add", make_add_handler(service, hub))`.

- [ ] **Step 5: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_add.py -v`, then `conda run -n ankiweb python -m pytest tests/test_editor.py tests/test_browser.py tests/test_screen_routes.py -q` (no regression).

- [ ] **Step 6: Commit**
```bash
git add ankiweb/screens/add.py ankiweb/screens/routes.py tests/test_add.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(add): /add Add-Note dialog reusing editor.js (deck/notetype pickers + add)"
```

## Context
`/add` serves `editor.js` in add-mode with deck/notetype `<select>` chrome (fixed top bar; the editor mounts into `document.body` below). The Add button captures every field by a synchronous shadow-DOM deep-read (the spike proved `saveNow` only flushes the focused field) and sends `addnote:<json>`. The handler tracks the chosen notetype/deck/tags (`setnotetype` re-pushes empty fields; `setdeck`/`saveTags` accumulate), and on `addnote` builds a fresh note by ord, `check_addable` (rejects empty), `col.add_note`, broadcasts via `emit`, then resets the form + toasts. `blur`/`key` are ignored (the deep-read is the source of truth).

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 2: Playwright — add a note through /add

**Files:** Create `tests/test_add_integration.py`.

- [ ] **Step 1: Write the test** — mirror `tests/test_editor_integration.py` (uvicorn thread, `pytest.importorskip("playwright.sync_api")`, inline `sync_playwright`; fresh port 8129; empty collection). Type into the editor's fields (focus via `window.focusField`, then `page.keyboard.type`) and click Add; assert the note was created (the toast appears AND a follow-up check finds it):
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
def live_server_add(tmp_path: Path):
    col_path = tmp_path / "add.anki2"
    Collection(str(col_path)).close()           # empty collection
    settings = Settings(collection_path=col_path, port=8129)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8129, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8129", settings
    server.should_exit = True; t.join(timeout=5)


def test_add_note_via_ui(live_server_add):
    url, settings = live_server_add
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page()
        page.goto(f"{url}/add")
        # editor mounts (add mode) with empty fields
        page.wait_for_function("document.querySelector('.note-editor')!==null", timeout=8000)
        page.wait_for_function(
            "document.querySelectorAll('.field-container').length>=2", timeout=8000)
        # focus field 0 via the editor API, type, then field 1
        page.evaluate("window.focusField(0)")
        page.keyboard.type("FrontText")
        page.evaluate("window.focusField(1)")
        page.keyboard.type("BackText")
        page.click("#add-btn")
        page.wait_for_function(
            "document.getElementById('add-toast').textContent.includes('Added')", timeout=8000)
        browser.close()
    # the note really landed in the collection
    col = Collection(str(settings.collection_path))
    try:
        nids = col.find_notes("FrontText")
        assert len(nids) == 1
        assert col.get_note(nids[0]).fields[0] == "FrontText"
    finally:
        col.close()
```
(NOTE: opening the collection in the test AFTER the server still holds it may need the server stopped first — the fixture teardown runs at `yield` end, so open the `Collection` for the assert OUTSIDE/after the `with sync_playwright` block but the server is still up. If anki refuses a second handle to the same file, instead assert success purely via the toast, and add a WS-level "note created" check in Task 1's tests (already present). Prefer the toast assertion if the file-lock is a problem; the Task-1 `test_addnote_creates_note` already proves the collection write.)

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_add_integration.py -v` (PASS if chromium available; SKIPS if not). If the post-test `Collection(...)` open fails due to the server holding the file, drop that block and rely on the toast assertion. Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_add_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(add): Playwright — add a note through the /add dialog"
```

## Context
End-to-end proof that `/add` works in a real browser: the editor mounts in add-mode, the user types into the fields, clicking "Add Note" deep-reads the fields and creates the note (toast confirms; the Task-1 WS test confirms the collection write).

## Report Format
Status, pytest summary (Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (D5 = Add-Note dialog):** `/add` route + `add` context (Task 1); deck/notetype pickers (Task 1); add-mode editor via the D3 recipe with `setNoteId(0)` + empty fields (Task 1); client deep-read field capture + Add button (Task 1 page body, Task 2 e2e); `addnote` builds + `check_addable` + `add_note` + broadcast + reset (Task 1); `setnotetype` reloads fields, `setdeck`/`saveTags` accumulate (Task 1). Deferred to D6 (documented): image paste/upload, `guiAddCards`/`guiEditNote`/`guiAddNoteSetData`/`guiBrowse`-reorder fidelity.

**2. Placeholder scan:** No TBD/TODO. The Playwright collection-reopen assertion has a documented fallback (toast-only) if the file is locked by the running server. `io` hardcoded `False` (IO notetypes deferred). Tags come from the editor's tag UI via `saveTags`; deck/notetype from the pickers.

**3. Type/name consistency:** `render_add_html(col)`/`add_page_body(deck_opts, nt_opts)`/`make_add_handler(service, hub)`/`_empty_load(col, ntid)` (add.py); reuses `_munge` (editor.py), `check_addable` (_helpers), `op_changes_to_flags` (collection_service). Bridge calls `ankiwebLoadNote(data)` + `ankiwebToast(msg)`; client `ankiwebAddNote()` (deep-read) + `readAllFields()`; handler verbs `addReady`/`setnotetype:`/`setdeck:`/`saveTags:`/`addnote:` via `arg.partition(":")`. Setter sequence matches D3/the spike (`setFields`/`setIsImageOcclusion`/`setFonts`/`setNotetypeMeta`/`setNoteId(0)`/`setTags`/`triggerChanges`). `col.models.current/get/all_names_and_ids`, `col.new_note`, `col.add_note`, `col.decks.get_current_id/all_names_and_ids` all verified live. New `add` context (distinct from D3's `editor`); route in `build_screen_router`; handler in `register_screen_handlers`.

**4. Risks:** the chrome `<div>` is in `document.body` when `setupEditor` mounts — Svelte `mount` APPENDS (doesn't clear), and the chrome is a fixed bar, so the editor renders below it; the Task-2 Playwright `.note-editor` + `.field-container` waits would fail loudly if the mount broke (fallback: prepend the chrome via JS after mount). The deep-read couples to the editor's `.field-container`/`.rich-text-editable`-shadow structure — pinned to the vendored `editor.js`, spike-verified. `addnote` ignores `blur`/`key` (the deep-read is authoritative) — a spurious on-load `key:` is harmless. Empty/dup notes are rejected by `check_addable` with a toast, nothing added. The form resets (re-push empty `setFields`) after a successful add so the next note starts clean.
