# ankiweb Plan D6 — Editor Paste (text + image) + gui* Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make paste work in the editor (it is currently broken — `editor.js` `preventDefault`s all paste and fires a payload-less `bridgeCommand("paste")`): a client-side handler that pastes text/HTML and uploads + inserts pasted images. Plus two clean `gui*` fidelity wins deferred from B4: `guiEditNote` opens the editor, and `guiBrowse` validates the reorder `columnId`.

**Architecture:** A `document`-level CAPTURE-phase `paste` listener (added to the `/edit` and `/add` editor pages) reads `ClipboardEvent.clipboardData`, calls `preventDefault()`+`stopImmediatePropagation()` synchronously to take over from `editor.js`, and inserts via the editor's own `window.pasteHTML(html, false, false)`. Images are POSTed to a new `/upload_media` route (stores via `col.media.write_data`) and inserted as `<img src="filename">`. The spike proved every step (capture listener fires across the shadow boundary; `stopImmediatePropagation` suppresses editor.js's paste cmd; `pasteHTML` inserts into the focused field; `write_data` stores + names). `guiEditNote`/`guiBrowse` are small edits to `actions/gui.py`.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, D3/D5 editor pages, B4 gui actions, pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is D6 of Sub-project D (the last D plan).** Spec: `docs/superpowers/specs/2026-06-01-ankiweb-browser-editor-design.md`. **A spike fully de-risked paste** (`/tmp/editor_spike_paste.py`). **Deferred (documented, low-value):** `guiAddCards`/`guiAddNoteSetData` *live-prefill against the open /add dialog* (needs cross-context add-handler state plumbing — the B4 shapes [int id / "dialog not open" dict] remain); a richer HTML paste sanitizer; remote-URL image download on paste.

**Grounded facts (spike + live probes):**
- `editor.js` attaches its paste handler on the field's shadow-DOM contenteditable and does `preventDefault()` + `bridgeCommand("paste")` (NO payload). So a `document` CAPTURE listener fires FIRST (clipboard events are composed); `e.preventDefault(); e.stopImmediatePropagation()` (called SYNCHRONOUSLY, before any `await`) suppresses editor.js's cmd and makes our handler authoritative (verified). `window.pasteHTML(html, false, false)` inserts html at the cursor in the focused field (verified for text + `<img>`); do NOT call `focusField` in the handler (the paste target already has focus; `focusField` is async).
- `col.media.write_data(desired_fname: str, data: bytes) -> str` (returns the possibly-renamed name; dedupes/renames on collision) — verified. `add_extension_based_on_mime` is NOT in `anki.media` → use a small mime→ext map.
- `col.all_browser_columns() -> [Column]` with `.key` (19 keys incl. `answer`/`deck`/`template`/`noteCrt`/`cardDue`/…) — for the `guiBrowse` columnId allowlist. `_ui(rt)` = `rt.hub.ui_state` (has `current_screen`, set on WS connect/dispatch_cmd).
- The `/upload_media` route must be in `build_screen_router` (before the media catch-all); do NOT use a `/_anki/...` path (POST `/_anki/{method}` is the anki_rpc passthrough). FastAPI `UploadFile` receives the multipart `file` field.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/screens/editor.py` (modify) | add `paste_handler_js()`; include it in `editor_page_body` |
| `ankiweb/screens/add.py` (modify) | include `paste_handler_js()` in `add_page_body` |
| `ankiweb/screens/routes.py` (modify) | add `POST /upload_media` |
| `ankiweb/ankiconnect/actions/gui.py` (modify) | `guiEditNote` → navigate /edit; `guiBrowse` columnId allowlist |
| `tests/test_editor.py` / `tests/test_add.py` (append) | upload route test; paste-handler-present unit asserts |
| `tests/ankiconnect/test_gui_actions.py` (append) | guiEditNote navigate; guiBrowse bad columnId |
| `tests/test_editor_integration.py` (append) | Playwright: paste an image into /edit |

---

## Task 1: `/upload_media` route + client paste handler

**Files:** Modify `ankiweb/screens/editor.py`, `ankiweb/screens/add.py`, `ankiweb/screens/routes.py`; Test `tests/test_editor.py`, `tests/test_add.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_editor.py`:
```python
def test_upload_media_stores_and_returns_name(client):
    r = client.post("/upload_media", files={"file": ("x.png", b"\x89PNG-bytes", "image/png")})
    assert r.status_code == 200
    fname = r.json()["filename"]
    assert fname.endswith(".png")
    assert client.portal.call(client.app.state.service.run, lambda col: col.media.have(fname))


def test_upload_media_derives_extension_from_mime(client):
    r = client.post("/upload_media", files={"file": ("noext", b"data", "image/jpeg")})
    assert r.json()["filename"].endswith(".jpg")


def test_editor_body_has_paste_handler(client):
    from ankiweb.screens.editor import editor_page_body
    body = editor_page_body(1)
    assert ("addEventListener('paste'" in body) or ('addEventListener("paste"' in body)
    assert "stopImmediatePropagation" in body and "pasteHTML" in body and "/upload_media" in body
```
Append to `tests/test_add.py`:
```python
def test_add_body_has_paste_handler(client):
    from ankiweb.screens.add import render_add_html
    body = client.portal.call(client.app.state.service.run, render_add_html)
    assert "pasteHTML" in body and "/upload_media" in body
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_editor.py -k "upload or paste_handler" tests/test_add.py -k "paste_handler" -v` → FAIL.

- [ ] **Step 3: Add `paste_handler_js()` to `ankiweb/screens/editor.py`** (a `document`-capture paste handler; image → upload → `<img>`, else text/html → insert):
```python
def paste_handler_js() -> str:
    """A document-capture paste handler that takes over from editor.js (which prevent-defaults
    paste and fires a payload-less bridgeCommand('paste')). Inserts via the editor's pasteHTML."""
    return (
        "document.addEventListener('paste',function(e){"
        "var cd=e.clipboardData;if(!cd)return;"
        "var img=null,items=cd.items||[];"
        "for(var i=0;i<items.length;i++){if(items[i].kind==='file'&&items[i].type&&"
        "items[i].type.indexOf('image/')===0){img=items[i].getAsFile();break;}}"
        "var html=cd.getData('text/html'),text=cd.getData('text/plain');"
        "if(!img&&!html&&!text)return;"
        "e.preventDefault();e.stopImmediatePropagation();"   // sync, before any await — beats editor.js
        "if(img){var f=new FormData();f.append('file',img,img.name||'paste.png');"
        "fetch('/upload_media',{method:'POST',body:f}).then(function(r){return r.json();})"
        ".then(function(j){window.pasteHTML('<img src=\"'+j.filename+'\">',false,false);});}"
        "else if(html){window.pasteHTML(html,false,false);}"
        "else{var s=text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')"
        ".replace(/\\n/g,'<br>');window.pasteHTML(s,false,false);}"
        "},true);"   // capture phase is mandatory
    )
```
Then include it inside `editor_page_body`'s inline IIFE — add `+ paste_handler_js()` to the script string (e.g. right after the `b.registerCalls({...});` call, still inside the IIFE). READ `editor_page_body` and insert the call so the JS lands inside the `(function(){ ... })()`.

- [ ] **Step 4: Include the paste handler in `ankiweb/screens/add.py`** — import `paste_handler_js` from `editor` and add it inside `add_page_body`'s IIFE (same placement — after `registerCalls`).
```python
from ankiweb.screens.editor import _munge, paste_handler_js
```
and insert `paste_handler_js()` into the inline script string.

- [ ] **Step 5: Add `POST /upload_media` to `ankiweb/screens/routes.py`**
```python
from fastapi import UploadFile

_MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
             "image/webp": ".webp", "image/svg+xml": ".svg", "image/bmp": ".bmp"}
```
In `build_screen_router`:
```python
    @router.post("/upload_media")
    async def upload_media(file: UploadFile):
        data = await file.read()
        base = (file.filename or "paste").rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or "paste"
        if "." not in base:
            base += _MIME_EXT.get(file.content_type or "", ".png")
        fname = await get_service().run(lambda col: col.media.write_data(base, data))
        return {"filename": fname}
```

- [ ] **Step 6: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_editor.py tests/test_add.py -v`, then `conda run -n ankiweb python -m pytest tests/test_browser.py tests/test_screen_routes.py -q` (no regression).

- [ ] **Step 7: Commit**
```bash
git add ankiweb/screens/editor.py ankiweb/screens/add.py ankiweb/screens/routes.py tests/test_editor.py tests/test_add.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(editor): client paste handler (text + image upload) + /upload_media"
```

## Context
`editor.js` swallows all paste; the new `document`-capture handler (in both `/edit` and `/add`) reads the clipboard, synchronously `preventDefault`+`stopImmediatePropagation` to beat editor.js, and inserts via the editor's own `pasteHTML(html, false, false)`. Pasted images upload to `POST /upload_media` (→ `col.media.write_data`, mime-derived extension) and insert as `<img src="filename">`. The route lives in `build_screen_router` (before the media catch-all; NOT under `/_anki/`).

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 2: gui* fidelity — guiEditNote opens the editor; guiBrowse columnId allowlist

**Files:** Modify `ankiweb/ankiconnect/actions/gui.py`; Test: `tests/ankiconnect/test_gui_actions.py` (append).

- [ ] **Step 1: Write the failing tests (append)** — (reuse the file's `client` fixture + `_gui`/`_drain` helpers; READ them first):
```python
def test_gui_edit_note_navigates(client):
    # a connected screen sets current_screen; guiEditNote navigates it to /edit
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        assert _gui(client, "guiEditNote", note=42) is None
        m = ws.receive_json()
        while m["type"] != "call" or m["fn"] != "ankiwebNavigate":
            m = ws.receive_json()
        assert m["args"] == ["/edit?nid=42"]


def test_gui_browse_invalid_columnid_raises(client):
    r = client.post("/", json={"action": "guiBrowse", "version": 6, "params": {
        "query": "", "reorderCards": {"columnId": "definitelyNotAColumn", "order": "ascending"}}})
    assert r.json()["error"] is not None


def test_gui_browse_valid_columnid_ok(client):
    # a real column key is accepted (reorder is a no-op without a table)
    r = client.post("/", json={"action": "guiBrowse", "version": 6, "params": {
        "query": "", "reorderCards": {"columnId": "deck", "order": "descending"}}})
    assert r.json()["error"] is None and isinstance(r.json()["result"], list)
```
(If the existing `test_gui_browse_reorder_validation` uses a `columnId` like `"noteFld"`, first CONFIRM `noteFld` is in `col.all_browser_columns()` keys — if not, change that test's valid columnId to a confirmed key like `"deck"`. Run `conda run -n ankiweb python -c "from anki.collection import Collection;import tempfile,os;c=Collection(os.path.join(tempfile.mkdtemp(),'c.anki2'));print([x.key for x in c.all_browser_columns()])"` to list the keys.)

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/ankiconnect/test_gui_actions.py -k "edit_note_navigates or columnid" -v` → FAIL.

- [ ] **Step 3: Implement (modify `ankiweb/ankiconnect/actions/gui.py`)**

(a) Replace `gui_edit_note` so it navigates the active screen to `/edit` (still returns None):
```python
@action("guiEditNote")
async def gui_edit_note(rt, note=None):
    screen = _ui(rt).current_screen
    if screen:
        await rt.hub.push_call(screen, "ankiwebNavigate", ["/edit?nid=" + str(note)])
    return None
```
(b) In `gui_browse`, add the columnId allowlist check inside the `reorderCards` validation, AFTER the `order` check (the other 3 checks stay):
```python
        valid = await rt.service.run(lambda col: {c.key for c in col.all_browser_columns()})
        if reorderCards["columnId"] not in valid:
            raise Exception("invalid columnId: " + str(reorderCards["columnId"]))
```

- [ ] **Step 4: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/ankiconnect/test_gui_actions.py -v`, then `conda run -n ankiweb python -m pytest tests/ankiconnect -q` (no regression — confirm the existing reorder test still passes with a valid columnId).

- [ ] **Step 5: Commit**
```bash
git add ankiweb/ankiconnect/actions/gui.py tests/ankiconnect/test_gui_actions.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(ankiconnect): guiEditNote opens /edit; guiBrowse validates columnId"
```

## Context
`guiEditNote` now pushes `ankiwebNavigate("/edit?nid=…")` to the connected screen (the editor opens), matching the reference's "open the edit dialog" intent (returns None as the reference does); no-op if no screen is connected. `guiBrowse` now rejects an unknown `reorderCards.columnId` against `col.all_browser_columns()` keys (the reference's 4th validation check), closing the B4 deferral. `guiAddCards`/`guiAddNoteSetData` keep their B4 shapes (live-prefill deferred).

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 3: Playwright — paste an image into /edit

**Files:** Append to `tests/test_editor_integration.py`.

- [ ] **Step 1: Write the test** — reuse the `live_server_edit` fixture (yields `(url, nid)`). Synthesize an image paste on the focused field (mirror the spike `/tmp/editor_spike_paste.py`: build a `DataTransfer` with an image `File` and dispatch a `paste` `ClipboardEvent` on the field's shadow-DOM editable), then assert an `<img>` with an uploaded src lands in the field:
```python
def test_paste_image_uploads_and_inserts(live_server_edit):
    url, nid = live_server_edit
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR:", e))
        page.goto(f"{url}/edit?nid={nid}")
        page.wait_for_function("document.querySelector('.note-editor')!==null", timeout=8000)
        page.evaluate("window.focusField(0)")
        # dispatch a synthetic image paste on the focused editable (reaches the document-capture handler)
        page.evaluate(
            "() => {"
            "  const fc=document.querySelector('.field-container');"
            "  const host=fc.querySelector('.rich-text-editable');"
            "  const ed=host.shadowRoot.querySelector('[contenteditable]');"
            "  const bytes=new Uint8Array([137,80,78,71,13,10,26,10]);"   # PNG magic
            "  const file=new File([bytes],'p.png',{type:'image/png'});"
            "  const dt=new DataTransfer(); dt.items.add(file);"
            "  ed.focus();"
            "  ed.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,"
            "    cancelable:true,composed:true}));"
            "}")
        # the handler uploads then inserts <img src="..."> into the field (deep-walk shadow roots)
        page.wait_for_function(
            "() => { function walk(r,a){r.querySelectorAll('*').forEach(function(el){"
            "if(el.shadowRoot)walk(el.shadowRoot,a); if(el.tagName==='IMG')a.push(el.getAttribute('src'));});}"
            "const a=[]; walk(document,a); return a.some(function(s){return s&&s.indexOf('.png')>=0;}); }",
            timeout=8000)
        browser.close()
```
(If `ClipboardEvent` with a custom `clipboardData` can't be constructed in this Chromium [some builds make `clipboardData` read-only], fall back to the spike's exact technique in `/tmp/editor_spike_paste.py` — it constructed and dispatched a working paste. The load-bearing assertion is that an `<img>` with a `.png` src appears in a field after the synthetic paste, proving upload→insert through the real `/edit` + `/upload_media`.)

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_editor_integration.py -v` (PASS if chromium available; SKIPS if not). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_editor_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(editor): Playwright — paste an image uploads + inserts <img>"
```

## Context
End-to-end proof in a real browser that pasting an image into the `/edit` editor uploads it to `/upload_media` and inserts `<img src="…">` into the field — the full client-handler → upload → `pasteHTML` round-trip the spike validated, now through the real route + shell.

## Report Format
Status, pytest summary (Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (D6 = paste + gui* fidelity):** client paste handler for text/HTML + image (Task 1, in both `/edit` and `/add`); `/upload_media` route (Task 1); `guiEditNote` opens the editor + `guiBrowse` columnId allowlist (Task 2); Playwright image-paste e2e (Task 3). Deferred (documented): `guiAddCards`/`guiAddNoteSetData` live-prefill against the open /add dialog (B4 shapes kept); HTML-paste sanitizer + remote-URL image download.

**2. Placeholder scan:** No TBD/TODO. The Playwright synthetic-paste has a documented fallback to the spike's exact dispatch technique if `ClipboardEvent.clipboardData` is read-only. The mime→ext map covers the common image types (default `.png`).

**3. Type/name consistency:** `paste_handler_js()` in `editor.py`, imported by `add.py`; both inline it inside their IIFEs (after `registerCalls`). `POST /upload_media` in `build_screen_router` (FastAPI `UploadFile`, multipart field `file`) → `col.media.write_data(name, bytes)` (verified) → `{"filename": name}`. Client fetches `/upload_media` (NOT `/_anki/...`). `pasteHTML(html, false, false)` (verified insert API); `e.preventDefault()+e.stopImmediatePropagation()` before any `await` (spike-verified suppression of editor.js). `guiEditNote` uses `_ui(rt).current_screen` + `rt.hub.push_call`; `guiBrowse` uses `col.all_browser_columns()` keys (verified). All reuse existing patterns.

**4. Risks:** the capture-listener-beats-editor.js behavior is the crux — fully spike-verified (A/B/C all passed), and the Task 3 Playwright would fail loudly if it regressed. The handler must `preventDefault`+`stopImmediatePropagation` SYNCHRONOUSLY before the image `fetch` await (encoded in `paste_handler_js`). `write_data` renames on content collision (the returned name is used, so the `<img>` src is always correct). `guiEditNote` navigates the *current* screen — if none connected, no-op (returns None, still faithful-shaped). The `guiBrowse` columnId check adds one `service.run`; the existing reorder test must use a real column key (Task 2 Step 1 verifies/updates it).
