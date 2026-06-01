# ankiweb Plan D3 — Note Editor (reuse editor.js) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working single-note editor at `GET /edit?nid=<id>` that reuses Anki's real compiled `editor.js`: load the note's fields/fonts/tags into the editor, and persist field edits + tag edits back to the collection.

**Architecture:** A new `editor` screen like the reviewer: `/edit?nid=X` serves the editor page (empty body + vendored `editor.js`; an inline script calls `setupEditor("browse")` and, gated on `require("anki/ui").loaded`, sends `load:<nid>` over the bridge). The `make_editor_handler` bridge closure responds to `load:<nid>` by building the note's loadNote data and pushing `ankiwebLoadNote([data])` (the client applies the proven setter sequence), and persists `blur:`/`key:`/`saveTags:` events via `col.update_note`. **No `eval_with_callback` from inside a handler** (the documented deadlock). Image-occlusion, media paste/upload, and the toolbar-button commands are deferred to D4/later (the handler ignores unknown commands).

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the vendored `editor.js`/`editor.css`/`editable.css`/`mathjax.js`, the existing screens/bridge, pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is D3 of Sub-project D.** Spec: `docs/superpowers/specs/2026-06-01-ankiweb-browser-editor-design.md`. **A de-risking Playwright spike PROVED the recipe below works end-to-end** (editor mounts, `setFields` populates, typing+blur emits `blur:0:nid:html` — zero errors). Next: D4 (embed editor in the Browser pane + Add-Note dialog + reviewer Edit button + gui* wiring).

**Grounded facts (spike + live probes):**
- Assets vendored + served at `/_anki/{path}`: `js/editor.js` (3.5MB), `js/mathjax.js`, `css/editor.css`, `css/editable.css`. The editor fires `POST /_anki/i18nResources` on setup — **the existing passthrough satisfies it** (blocking it prevents mount; no new route needed).
- Page recipe: head loads (in order) `editor.css`, `editable.css`, then `mathjax.js`, then `editor.js` (render_page puts js in `<head>`, then shell `bootstrap.js`); the shell aliases `window.bridgeCommand = window.pycmd` → WS. Empty body; `setupEditor("browse")` mounts the Svelte app into `document.body`.
- **Minimal setter sequence to render+populate a field (all REQUIRED), gated on `require("anki/ui").loaded`:** `setFields([[name, html], …])` (array of `[name, html]` pairs), `setIsImageOcclusion(false)` (**MANDATORY** for non-IO notetypes — omitting it renders ZERO fields), `setFonts([[family, sizePx, rtl], …])` (**load-bearing** — one per field, same length, else TypeError), `setNotetypeMeta({id, modTime})`, `setNoteId(int)` (so blur/key carry the real nid), `setTags([str])`, `triggerChanges()`.
- JS→server commands (via `window.bridgeCommand`): `focus:{ord}`, `blur:{ord}:{nid}:{html}`, `key:{ord}:{nid}:{html}` (debounced ~600ms; a spurious `key:` can fire on load — idempotent saves are fine), `saveTags:{json}` (does NOT carry the nid → handler tracks the current note id from the last `load:`), `editorState:{n}:{o}`/`setTagsCollapsed:{bool}` (ignore). Parse with `arg.partition(":")` then `rest.split(":", 2)` for blur/key (the html, index 2, keeps its colons).
- Persistence (verified live): `col.media.escape_media_filenames(s)` escapes (`a b.png`→`a%20b.png`); `escape_media_filenames(s, unescape=True)` reverses. Inbound munge: null-strip + drop bare `<br>`/`<div><br></div>` + unescape media. `col.update_note(note, skip_undo_entry=True)→OpChanges` (run_op unwraps + broadcasts). `model["flds"][i]` has `font`/`size`/`rtl`/`name`; `model["id"]`/`model["mod"]`.
- **Route-ordering trap:** the media catch-all `GET /{path}` is last but matches late-added routes — the `/edit` route MUST be in `build_screen_router` (like `/browse`), not appended after `create_app`.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/screens/editor.py` (create) | `editor_page_body(nid)` (inline setupEditor + ankiwebLoadNote registerCalls + load:) + `make_editor_handler(service, hub)` + `_build_load`/`_save_field`/`_munge` |
| `ankiweb/screens/routes.py` (modify) | add `GET /edit` + `set_handler("editor", …)` |
| `tests/test_editor.py` (create) | WS tests: load→ankiwebLoadNote, blur/key save, saveTags |
| `tests/test_editor_integration.py` (create) | Playwright: real editor.js mounts + field populated via the real /edit route |

---

## Task 1: `/edit` screen + editor bridge handler (load + save)

**Files:** Create `ankiweb/screens/editor.py`; Modify `ankiweb/screens/routes.py`; Test `tests/test_editor.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_editor.py`:
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
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "CapitalFrance"; n["Back"] = "Paris"
    n.tags = ["geo"]
    col.add_note(n, col.decks.id("Default"))


def _nid(client):
    return client.portal.call(client.app.state.service.run, lambda col: list(col.find_notes(""))[0])


def _drain_call(ws, fn, tries=6):
    for _ in range(tries):
        m = ws.receive_json()
        if m["type"] == "call" and m["fn"] == fn:
            return m["args"]
    raise AssertionError(f"no {fn} frame")


def test_edit_route_renders(client):
    nid = _nid(client)
    r = client.get(f"/edit?nid={nid}")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="editor"' in r.text
    assert "/_anki/js/editor.js" in r.text
    assert "/_anki/css/editor.css" in r.text
    assert "setupEditor" in r.text and f"window.__ankiwebEditNid={nid}" in r.text


def test_editor_load_pushes_note(client):
    nid = _nid(client)
    with client.websocket_connect("/ws?context=editor") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["noteId"] == nid
        assert data["fields"][0][0] == "Front" and data["fields"][0][1] == "CapitalFrance"
        assert data["fields"][1][1] == "Paris"
        assert len(data["fonts"]) == len(data["fields"])
        assert data["fonts"][0][0] and isinstance(data["fonts"][0][1], int)
        assert data["io"] is False
        assert data["tags"] == ["geo"]
        assert "id" in data["meta"] and "modTime" in data["meta"]


def test_editor_blur_saves_field(client):
    nid = _nid(client)
    with client.websocket_connect("/ws?context=editor") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"blur:1:{nid}:Lyon"})
        # re-load to confirm the save landed (sequential WS processing guarantees order)
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["fields"][1][1] == "Lyon"
    assert client.portal.call(client.app.state.service.run,
                              lambda col: col.get_note(nid).fields[1]) == "Lyon"


def test_editor_key_saves_field(client):
    nid = _nid(client)
    with client.websocket_connect("/ws?context=editor") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"key:0:{nid}:Berlin"})
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["fields"][0][1] == "Berlin"


def test_editor_blur_munges_bare_br(client):
    nid = _nid(client)
    with client.websocket_connect("/ws?context=editor") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"blur:1:{nid}:<br>"})
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["fields"][1][1] == ""


def test_editor_savetags(client):
    nid = _nid(client)
    with client.websocket_connect("/ws?context=editor") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        _drain_call(ws, "ankiwebLoadNote")
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": 'saveTags:["x","y"]'})
        ws.send_json({"type": "cmd", "id": None, "ctx": "editor", "arg": f"load:{nid}"})
        data = _drain_call(ws, "ankiwebLoadNote")[0]
        assert data["tags"] == ["x", "y"]
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_editor.py -v` → FAIL.

- [ ] **Step 3: Create `ankiweb/screens/editor.py`**
```python
from __future__ import annotations
import json


def _munge(col, html: str) -> str:
    """editor_will_munge_html equivalent: null-strip, drop bare <br>, unescape media."""
    html = (html or "").replace("\x00", "")
    if html in ("<br>", "<div><br></div>"):
        html = ""
    return col.media.escape_media_filenames(html, unescape=True)


def _build_load(col, nid: int) -> dict:
    note = col.get_note(nid)
    model = note.note_type()
    flds = model["flds"]
    return {
        "fields": [[f["name"], col.media.escape_media_filenames(note.fields[i])]
                   for i, f in enumerate(flds)],
        "fonts": [[f.get("font", "Arial"), int(f.get("size", 20)), bool(f.get("rtl", False))]
                  for f in flds],
        "io": False,                                   # image-occlusion deferred
        "noteId": nid,
        "meta": {"id": model["id"], "modTime": model.get("mod", 0)},
        "tags": list(note.tags),
    }


def _save_field(col, nid: int, ord_: int, html: str):
    note = col.get_note(nid)
    if 0 <= ord_ < len(note.fields):
        note.fields[ord_] = _munge(col, html)
        return col.update_note(note, skip_undo_entry=True)
    return None


def editor_page_body(nid: int) -> str:
    """Empty-body host for editor.js: mount the Svelte editor, register the loadNote
    applier, and ask the server to load the note (all gated on require('anki/ui').loaded)."""
    return (
        f"<script>window.__ankiwebEditNid={int(nid)}</script>"
        "<script>(function(){"
        "window.setupEditor('browse');"
        "var b=window.__ankiwebBridge;"
        "b.registerCalls({ankiwebLoadNote:function(d){"
        "require('anki/ui').loaded.then(function(){"
        "window.setFields(d.fields);"
        "window.setIsImageOcclusion(d.io);"            # MANDATORY before fields render
        "window.setFonts(d.fonts);"                    # load-bearing
        "window.setNotetypeMeta(d.meta);"
        "window.setNoteId(d.noteId);"
        "window.setTags(d.tags);"
        "window.triggerChanges();"
        "});}});"
        "require('anki/ui').loaded.then(function(){"
        "window.pycmd('load:'+window.__ankiwebEditNid);"
        "});"
        "})();</script>"
    )


def make_editor_handler(service, hub):
    """Bridge handler for the 'editor' context. Tracks the current note id for saveTags
    (which does not carry it); blur/key carry their own nid."""
    state = {"nid": None}

    async def handler(arg: str):
        head, _, rest = arg.partition(":")
        if head == "load":
            nid = int(rest)
            state["nid"] = nid
            data = await service.run(lambda col: _build_load(col, nid))
            await hub.push_call("editor", "ankiwebLoadNote", [data])
        elif head in ("blur", "key"):
            parts = rest.split(":", 2)               # ord:nid:html  (html keeps its colons)
            if len(parts) == 3:
                ord_, nid, htmlval = int(parts[0]), int(parts[1]), parts[2]
                if head == "blur":                   # final save → broadcast (other screens refresh)
                    await service.run_op(lambda col: _save_field(col, nid, ord_, htmlval),
                                         initiator="editor")
                else:                                # debounced keystroke → save silently
                    await service.run(lambda col: _save_field(col, nid, ord_, htmlval))
        elif head == "saveTags":
            if state["nid"] is not None:
                tags = json.loads(rest)
                nid = state["nid"]

                def fn(col):
                    n = col.get_note(nid)
                    n.tags = list(tags)
                    return col.update_note(n, skip_undo_entry=True)
                await service.run_op(fn, initiator="editor")
        # focus:/editorState:/setTagsCollapsed:/toolbar buttons → ignored (D4/later)
        return None

    return handler
```

- [ ] **Step 4: Modify `ankiweb/screens/routes.py`**
1. Add import: `from ankiweb.screens.editor import editor_page_body, make_editor_handler`.
2. In `build_screen_router`, add (the `nid` query param is required):
```python
    @router.get("/edit", response_class=HTMLResponse)
    async def edit_page(nid: int):
        return HTMLResponse(render_page(
            "editor", editor_page_body(nid),
            ["css/editor.css", "css/editable.css"],
            ["js/mathjax.js", "js/editor.js"]))
```
3. In `register_screen_handlers`, add: `hub.set_handler("editor", make_editor_handler(service, hub))`.

- [ ] **Step 5: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_editor.py -v`, then `conda run -n ankiweb python -m pytest tests/test_screen_routes.py tests/test_browser.py tests/test_reviewer.py -q` (no regression).

- [ ] **Step 6: Commit**
```bash
git add ankiweb/screens/editor.py ankiweb/screens/routes.py tests/test_editor.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(editor): /edit screen reusing editor.js (load note + save fields/tags)"
```

## Context
The `/edit` page hosts the real `editor.js`: `setupEditor("browse")` mounts the Svelte editor, then `load:<nid>` asks the server to push `ankiwebLoadNote([data])`, which the client applies via the spike-proven setter sequence (`setFields`/`setIsImageOcclusion(false)`/`setFonts`/`setNotetypeMeta`/`setNoteId`/`setTags`/`triggerChanges`, gated on `require("anki/ui").loaded`). Field edits arrive as `blur:`/`key:` (parsed `split(":",2)`; munged: null-strip + drop bare `<br>` + unescape media) and persist via `col.update_note(skip_undo_entry=True)` — `blur` broadcasts (via `run_op`), `key` saves silently (via `run`). `saveTags:` (no nid) uses the handler's tracked current note id. Outbound field HTML is media-escaped; inbound is unescaped — the round-trip the spike verified.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 2: Playwright — real editor.js mounts + loads via /edit

**Files:** Create `tests/test_editor_integration.py`.

- [ ] **Step 1: Write the test** — mirror `tests/test_reviewer_integration.py`'s `live_server` fixture (uvicorn in a thread, `pytest.importorskip("playwright.sync_api")`, inline `sync_playwright`). Seed a Basic note and yield both the URL and its note id:
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
def live_server_edit(tmp_path: Path):
    col_path = tmp_path / "edit.anki2"
    col = Collection(str(col_path))
    try:
        n = col.new_note(col.models.by_name("Basic"))
        n["Front"] = "CapitalFrance"; n["Back"] = "Paris"
        col.add_note(n, col.decks.id("Default"))
        nid = n.id
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8128)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8128, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8128", nid
    server.should_exit = True; t.join(timeout=5)


def test_editor_mounts_and_loads(live_server_edit):
    url, nid = live_server_edit
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{url}/edit?nid={nid}")
        # the real editor.js mounts its Svelte app
        page.wait_for_function("document.querySelector('.note-editor')!==null", timeout=8000)
        # the server's load: -> ankiwebLoadNote -> setFields populated the first field
        page.wait_for_function(
            "Array.from(document.querySelectorAll('[contenteditable]'))"
            ".some(function(e){return e.textContent.indexOf('CapitalFrance')>=0;})",
            timeout=8000)
        assert not errors, errors
        browser.close()
```

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_editor_integration.py -v` (PASS if chromium available; SKIPS if playwright missing). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_editor_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(editor): Playwright — editor.js mounts + loads the note via /edit"
```

## Context
End-to-end proof that the REAL `editor.js`, served through ankiweb's actual `/edit` route + shell + WS bridge (not the spike's standalone page), mounts and that the server's `load:` → `ankiwebLoadNote` → `setFields` round-trip populates the field in a real browser — with no page errors.

## Report Format
Status, pytest summary (note Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (D3 = editor reuse):** `/edit?nid=` route serving vendored `editor.js` (Task 1); `setupEditor`/`require("anki/ui").loaded` gating + the spike-proven minimal setter sequence via `ankiwebLoadNote` (Task 1); `load:`/`blur:`/`key:`/`saveTags:` handler with media-munge + `col.update_note` (Task 1); Playwright mount+load proof through the real route (Task 2). Deferred (per spec): image-occlusion, media paste/upload endpoint, toolbar-button commands, Add-mode, embedding in the Browser pane, the reviewer Edit button — D4/later.

**2. Placeholder scan:** No TBD/TODO. `io` is hardcoded `False` (IO deferred). Toolbar/unknown commands are intentionally ignored (the handler returns None — the editor prints "uncaught cmd" rather than throwing). No `eval_with_callback` is used (deadlock avoided — the load is a server push, saves are fire-and-forget client→server cmds).

**3. Type/name consistency:** `editor_page_body(nid)`/`make_editor_handler(service, hub)`/`_build_load`/`_save_field`/`_munge` (editor.py); bridge call `ankiwebLoadNote(data)` (server push ↔ inline registerCalls); handler verbs `load:`/`blur:`/`key:`/`saveTags:` via `arg.partition(":")` + `rest.split(":",2)`; the client setter sequence (`setFields`/`setIsImageOcclusion`/`setFonts`/`setNotetypeMeta`/`setNoteId`/`setTags`/`triggerChanges`) matches the spike. `col.media.escape_media_filenames(s, unescape=…)`, `col.update_note(note, skip_undo_entry=True)→OpChanges`, `model["flds"][i]` font/size/rtl all verified live. Route in `build_screen_router` (before the media catch-all); handler in `register_screen_handlers`.

**4. Risks:** the WS-save tests use the "save then re-`load:` and check" pattern (sequential WS processing guarantees the save completed) rather than draining the `run_op` opchanges broadcast — robust and order-independent. A spurious on-load `key:` is idempotent (`_save_field` just rewrites the same value). `saveTags` relies on the handler's tracked `state["nid"]` from the last `load:` — single-user, sequential. The Playwright test asserts `not errors` so a regression in the shell+editor.js integration (load order, the `anki/ui` gate, i18n) fails loudly. If `.note-editor` isn't the mounted root selector in this bundle version, the spike report lists alternatives (`.fields`, `.editor-field`, `anki-editable`); adjust the wait selector to whatever the spike's `/tmp/editor_spike.py` proved.
