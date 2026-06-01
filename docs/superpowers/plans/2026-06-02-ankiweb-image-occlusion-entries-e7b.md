# ankiweb Plan E7b — Image Occlusion Entry Points + Playwright

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the E7a IO data plane reachable: an **Add** flow (deck-browser "Image Occlusion" button → upload an image → the IO canvas opens in add mode → save creates the note) and an **Edit** flow (the browser routes an existing IO note to the IO canvas instead of the normal editor), plus a real-browser Playwright proof of both.

**Architecture:** A `POST /image-occlusion/upload` saves the image to a dedicated **`<import_tmp_dir>/io/` subdir** (the E6a import GC's non-recursive `iterdir` never sweeps it — protecting a long drawing session), ensures the IO notetype exists (`col.add_image_occlusion_notetype()` — a safe idempotent no-op in 25.9.4), and returns `{path}`. The deck-browser **"Image Occlusion"** button calls a new `ankiwebImageOcclusion()` (shell `bootstrap.ts`): image picker → upload → `window.location = "/image-occlusion/" + encodeURIComponent(path)` (an absolute path ⇒ no leading digit ⇒ the route classifies it as add-mode; the SPA sends `notetypeId: 0` itself). For **Edit**, the browser's single-select detail iframe points at `/image-occlusion/<noteId>` (instead of `/edit?nid=`) when the note's notetype has **`originalStockKind == 6`** (the robust IO marker — NOT name equality; `type==1` is shared with Cloze). **Refinement vs the spec:** the spec said edit-mode uses a full-page `ankiwebNavigate`; this plan uses the browser's existing **detail-iframe** mechanism instead (`<iframe class='editor-frame' src='/image-occlusion/<id>'>`), so IO editing stays inside the browser screen — consistent with how every other note opens (D4's editor iframe) and the IO standalone SPA works fine in an iframe (it's self-contained, loads `/_app/`, POSTs `/_anki/`).

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, E6a's `import_tmp` (+ new IO-subdir helpers), `fastapi.UploadFile`, the shell `bootstrap.ts` (esbuild via `node tools/build_shell.mjs`), pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is E7b of Sub-project E7** (image occlusion) — the final plan. Spec: `docs/superpowers/specs/2026-06-02-ankiweb-image-occlusion-e7-design.md`. Builds on E7a (the route + IO RPC wiring, merged). After E7b, Sub-project E (E1–E7) is complete.

**Grounded facts (live-probed + E7a-verified):**
- E7a shipped: `GET /image-occlusion/{path:path}` (serves the SPA shell); passthrough `get_image_occlusion_note`/`get_image_occlusion_fields`; CUSTOM `getImageForOcclusion` (path-confined + touch-on-read), `addImageOcclusionNote` (path-confined + broadcast), `updateImageOcclusionNote` (broadcast).
- The IO notetype "Image Occlusion" ships by default; `col.add_image_occlusion_notetype() -> None` is idempotent (safe no-op). The IO notetype dict has `originalStockKind == 6` (probed; Cloze=5, Basic=1; `type==1` shared with Cloze — so use originalStockKind).
- `import_tmp` (E6a): `dir(settings)` (the managed temp dir), `allocate`/`is_within`/`gc` (gc is non-recursive: `for f in dir.iterdir(): if f.is_file()` — verified it skips a `dir/io/` subdir's files). `is_within(settings, path)` accepts any path under `dir(settings)`, including the `io/` subdir.
- `col.get_note(nid).mid` → the note's notetype id; `col.models.get(mid)` → the notetype dict (`.get("originalStockKind")`). The browser select branch (`browser.py:187-194`) sets a single-select `detail` iframe to `/edit?nid={nids[0]}`; `.editor-frame` CSS exists. `_nids(col, cids)` maps card-ids→note-ids.
- The IO SvelteKit page renders a `<canvas id="canvas">` (MaskEditor.svelte) and POSTs `getImageForOcclusion` (add) / `getImageOcclusionNote` (edit). `python-multipart` is installed (D6). `bootstrap.ts` holds `ankiwebCreateDeck`/`ankiwebImportFile`; `node tools/build_shell.mjs` rebuilds the git-tracked (gitignored, force-added) `ankiweb/shell/static/bootstrap.js`. The deck-browser create line (`deckbrowser.py:50-54`) currently: Create Deck + Create Filtered Deck + Import + Export + Stats.
- `add_image_occlusion_note(notetype_id=0, image_path=<abs in io/>, occlusions, …)` copies the image into `col.media.dir()` and creates the note (E7a-tested); the media copy persists after the temp is deleted.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/import_tmp.py` (modify) | `io_dir`/`io_allocate`/`io_gc` (the `io/` subdir + its long-TTL GC) |
| `ankiweb/screens/routes.py` (modify) | `POST /image-occlusion/upload` (image → `io/` subdir; ensure IO notetype; return `{path}`) |
| `shell_src/bootstrap.ts` (modify) + rebuild | `ankiwebImageOcclusion()` (image picker → upload → navigate) |
| `ankiweb/screens/deckbrowser.py` (modify) | an "Image Occlusion" button |
| `ankiweb/screens/browser.py` (modify) | single-select IO note → `/image-occlusion/<id>` detail iframe (via `originalStockKind==6`) |
| `tests/test_image_occlusion_entry.py` (create) | upload→io-path/400/ensure-notetype; io-GC-survival; media-persistence; browser IO-routing; deck-browser button |
| `tests/test_image_occlusion_integration.py` (create) | Playwright: add-mode + edit-mode boot proofs |

---

## Task 1: upload flow + entry points (Add button + Edit browser-routing)

**Files:** Modify `ankiweb/import_tmp.py`, `ankiweb/screens/routes.py`, `shell_src/bootstrap.ts`, `ankiweb/screens/deckbrowser.py`, `ankiweb/screens/browser.py`; Test `tests/test_image_occlusion_entry.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_image_occlusion_entry.py`:
```python
import io
import os
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f1f0000000049454e44ae426082")
OCCL = "{{c1::image-occlusion:rect:left=.1:top=.1:width=.2:height=.2}}"
BIN = {"content-type": "application/binary"}


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "c.anki2",
                        import_tmp_dir=tmp_path / "import-tmp")
    with TestClient(create_app(settings)) as c:
        yield c


def test_upload_image_returns_io_path(client):
    files = {"file": ("photo.png", io.BytesIO(PNG), "image/png")}
    r = client.post("/image-occlusion/upload", files=files)
    assert r.status_code == 200
    p = Path(r.json()["path"])
    assert p.exists() and p.read_bytes() == PNG
    assert p.parent.name == "io"                       # the dedicated subdir
    assert not p.name[:1].isdigit() or p.is_absolute()  # absolute => add-mode classification
    assert p.is_absolute()
    from ankiweb import import_tmp
    assert import_tmp.is_within(client.app.state.service.settings, str(p))


def test_upload_non_image_400(client):
    files = {"file": ("notes.csv", io.BytesIO(b"a,b"), "text/csv")}
    r = client.post("/image-occlusion/upload", files=files)
    assert r.status_code == 400


def test_upload_ensures_io_notetype(client):
    files = {"file": ("photo.png", io.BytesIO(PNG), "image/png")}
    client.post("/image-occlusion/upload", files=files)
    exists = client.portal.call(client.app.state.service.run,
                                lambda col: col.models.by_name("Image Occlusion") is not None)
    assert exists


def test_io_temp_survives_import_gc(client):
    from ankiweb import import_tmp
    s = client.app.state.service.settings
    p = import_tmp.io_allocate(s, ".png")
    p.write_bytes(PNG)
    old = time.time() - 7200
    os.utime(p, (old, old))
    import_tmp.gc(s, ttl_seconds=3600)   # the IMPORT gc (non-recursive) must NOT reap io/
    assert p.exists()


def test_image_persists_after_temp_deleted(client):
    import anki.image_occlusion_pb2 as iopb
    from ankiweb import import_tmp
    svc = client.app.state.service
    p = import_tmp.io_allocate(svc.settings, ".png")
    p.write_bytes(PNG)
    req = iopb.AddImageOcclusionNoteRequest(
        notetype_id=0, image_path=str(p), occlusions=OCCL, header="H", back_extra="B", tags=[])
    r = client.post("/_anki/addImageOcclusionNote", content=req.SerializeToString(), headers=BIN)
    assert r.status_code == 200
    os.remove(p)                                          # temp gone
    media = client.portal.call(svc.run, lambda col: os.listdir(col.media.dir()))
    assert any(f.endswith(".png") for f in media)          # note's image survives in media


def test_browser_routes_io_note_to_io_editor(client):
    import anki.image_occlusion_pb2 as iopb
    from ankiweb import import_tmp
    svc = client.app.state.service
    p = import_tmp.io_allocate(svc.settings, ".png")
    p.write_bytes(PNG)
    client.post("/_anki/addImageOcclusionNote", headers=BIN, content=iopb.AddImageOcclusionNoteRequest(
        notetype_id=0, image_path=str(p), occlusions=OCCL, header="H", back_extra="B", tags=[]).SerializeToString())

    def seed_normal(col):
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"; n["Back"] = "a"
        col.add_note(n, col.decks.id("Default"))
        return col.find_cards('note:"Image Occlusion"')[0], col.find_cards("note:Basic")[0]
    io_cid, normal_cid = client.portal.call(svc.run, seed_normal)

    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{io_cid}"})
        m = ws.receive_json()
        while not (m["type"] == "call" and m["fn"] == "ankiwebSetDetail"):
            m = ws.receive_json()
        assert "/image-occlusion/" in m["args"][0]
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{normal_cid}"})
        m = ws.receive_json()
        while not (m["type"] == "call" and m["fn"] == "ankiwebSetDetail"):
            m = ws.receive_json()
        assert "/edit?nid=" in m["args"][0]


def test_deckbrowser_has_image_occlusion_button(client):
    r = client.get("/deckbrowser")
    assert "ankiwebImageOcclusion" in r.text
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_image_occlusion_entry.py -v` → FAIL.

- [ ] **Step 3: Add the IO-subdir helpers** — in `ankiweb/import_tmp.py` (after `gc`):
```python
def io_dir(settings) -> Path:
    d = dir(settings) / "io"
    d.mkdir(parents=True, exist_ok=True)
    return d


def io_allocate(settings, ext: str) -> Path:
    return io_dir(settings) / (secrets.token_hex(8) + ext)


def io_gc(settings, ttl_seconds: int = 86400) -> None:
    base = io_dir(settings)
    now = time.time()
    for f in base.iterdir():
        try:
            if f.is_file() and now - f.stat().st_mtime > ttl_seconds:
                f.unlink()
        except OSError:
            pass
```

- [ ] **Step 4: Add the upload endpoint** — in `ankiweb/screens/routes.py` `build_screen_router` (next to `/import/upload`):
```python
    @router.post("/image-occlusion/upload")
    async def image_occlusion_upload(file: UploadFile):
        from fastapi.responses import JSONResponse
        from ankiweb import import_tmp
        service = get_service()
        import_tmp.io_gc(service.settings)
        name = (file.filename or "").lower()
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".avif"):
            return JSONResponse({"error": f"unsupported image type: {ext or '(none)'}"}, status_code=400)
        dest = import_tmp.io_allocate(service.settings, ext)
        dest.write_bytes(await file.read())
        await service.run(lambda col: col.add_image_occlusion_notetype())  # idempotent ensure
        return {"path": str(dest)}
```

- [ ] **Step 5: Add the shell function** — in `shell_src/bootstrap.ts`, after `ankiwebImportFile`:
```typescript
(window as any).ankiwebImageOcclusion = () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.onchange = async () => {
    const f = input.files && input.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    const resp = await fetch("/image-occlusion/upload", { method: "POST", body: fd });
    if (!resp.ok) { window.alert("Image occlusion upload failed: " + (await resp.text())); return; }
    const { path } = await resp.json();
    window.location.href = "/image-occlusion/" + encodeURIComponent(path);
  };
  input.click();
};
```
Then recompile: `node tools/build_shell.mjs` (regenerates `ankiweb/shell/static/bootstrap.js`).

- [ ] **Step 6: Add the deck-browser button** — in `ankiweb/screens/deckbrowser.py` `render_deckbrowser_html`, extend the `create` line (before the Stats link):
```python
    create = ("<button onclick='ankiwebCreateDeck()'>Create Deck</button>"
              " <button onclick='pycmd(\"createfiltered\")'>Create Filtered Deck</button>"
              " <button onclick='ankiwebImportFile()'>Import</button>"
              " <a href='/export'>Export</a>"
              " <button onclick='ankiwebImageOcclusion()'>Image Occlusion</button>"
              " <a href='/graphs'>Stats</a>")
```

- [ ] **Step 7: Wire the browser IO edit-routing** — in `ankiweb/screens/browser.py`, replace the single-select detail logic in the `("select", "open")` branch (READ the current branch first; it builds `detail` from `/edit?nid=`):
```python
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
```

- [ ] **Step 8: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_image_occlusion_entry.py -v`, then regression: `conda run -n ankiweb python -m pytest tests/test_browser.py tests/test_deckbrowser.py tests/test_import_upload.py tests/test_image_occlusion.py tests/test_screen_routes.py -q`.

- [ ] **Step 9: Commit**
```bash
git add ankiweb/import_tmp.py ankiweb/screens/routes.py shell_src/bootstrap.ts ankiweb/shell/static/bootstrap.js ankiweb/screens/deckbrowser.py ankiweb/screens/browser.py tests/test_image_occlusion_entry.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(image-occlusion): Add upload flow + deck-browser button + Edit browser-routing"
```

## Context
The Add entry uploads an image to the `io/` subdir (excluded from the import GC) + ensures the IO notetype, then navigates to `/image-occlusion/<path>` (add-mode). The Edit entry routes a single-selected IO note (`originalStockKind==6`) to `/image-occlusion/<noteId>` via the browser's existing detail iframe (instead of `/edit?nid=`), keeping IO editing inside the browser. The E7a RPCs make both functional.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns (incl. that `bootstrap.js` rebuilt + the browser IO/non-IO routing both pass + the io-GC-survival test).

---

## Task 2: Playwright — add-mode + edit-mode boot proofs

**Files:** Create `tests/test_image_occlusion_integration.py`.

- [ ] **Step 1: Write the test** — mirror the E6a/E6b `live_server` (uvicorn thread, fresh port 8137, `pytest.importorskip`, inline `sync_playwright`). Pre-seed an image in the `io/` subdir (add-mode) and an IO note (edit-mode); open each route and assert the canvas SPA boots + the right load RPC fired:
```python
import threading
import time
from pathlib import Path
from urllib.parse import quote
import pytest
import uvicorn
from anki.collection import Collection
from ankiweb.config import Settings
from ankiweb.app import create_app

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f1f0000000049454e44ae426082")
OCCL = "{{c1::image-occlusion:rect:left=.1:top=.1:width=.2:height=.2}}"


@pytest.fixture
def live_io(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    tmp_dir = tmp_path / "import-tmp"
    io_dir = tmp_dir / "io"
    io_dir.mkdir(parents=True)
    img = io_dir / "pic.png"
    img.write_bytes(PNG)
    col = Collection(str(col_path))
    try:
        import anki.image_occlusion_pb2 as iopb
        col.add_image_occlusion_notetype()
        nt = col.models.by_name("Image Occlusion")
        col.add_image_occlusion_note(notetype_id=nt["id"], image_path=str(img),
                                     occlusions=OCCL, header="H", back_extra="B", tags=[])
        nid = col.find_notes('note:"Image Occlusion"')[0]
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8137, import_tmp_dir=tmp_dir)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8137, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8137", str(img), nid
    server.should_exit = True
    t.join(timeout=5)


def _boot(url, expect_method):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed",
                lambda r: errors.append("REQFAIL " + r.url) if ("/_app/" in r.url or "/_anki/" in r.url) else None)
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/_anki/" in r.url else None)
        page.goto(url)
        page.wait_for_selector("canvas", timeout=15000)   # MaskEditor's <canvas>
        page.wait_for_function("document.body.innerText.length>0 || document.querySelector('canvas')", timeout=10000)
        assert not errors, errors
        assert any(expect_method.lower() in u.lower() for u in posts), (expect_method, posts)
        browser.close()


def test_io_add_mode_boots(live_io):
    base, img_path, _nid = live_io
    _boot(f"{base}/image-occlusion/{quote(img_path, safe='')}", "get_image_for_occlusion")


def test_io_edit_mode_boots(live_io):
    base, _img, nid = live_io
    _boot(f"{base}/image-occlusion/{nid}", "get_image_occlusion_note")
```
(NOTE: the IO page renders `<canvas id="canvas">` (MaskEditor). add-mode POSTs `getImageForOcclusion`; edit-mode POSTs `getImageOcclusionNote`. Load-bearing asserts: the canvas mounted, no `/_app/`-or-`/_anki/` request failed, no page error, and the expected load RPC fired. If `wait_for_selector("canvas")` times out, dump `page.content()` to find the real mount element and adjust; if a benign error appears, narrow the filter with a comment — never weaken the load-bearing asserts.)

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_image_occlusion_integration.py -v` (PASS if chromium; SKIPS if not). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_image_occlusion_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(image-occlusion): Playwright — add-mode + edit-mode SPA boot proofs"
```

## Context
End-to-end proof both IO flows boot through ankiweb's routes: add-mode (an image in the `io/` subdir → `/image-occlusion/<path>` → the fabric canvas mounts, `getImageForOcclusion` fired) and edit-mode (a seeded IO note → `/image-occlusion/<noteId>` → canvas mounts, `getImageOcclusionNote` fired), both with zero errors. The upload + entry wiring is proven by Task 1; the write paths by E7a's round-trips.

## Report Format
Status, pytest summary (Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (E7b = entry points + Playwright):** `POST /image-occlusion/upload` → `io/` subdir + ensure-notetype + `{path}` (Task 1, tested + 400 on non-image); `io/` excluded from the import GC + the long-TTL `io_gc` (Task 1, survival test); media-persistence after temp delete (Task 1 test); deck-browser "Image Occlusion" button + `ankiwebImageOcclusion()` (Task 1); browser Edit-routing via `originalStockKind==6` (Task 1, IO→`/image-occlusion/`, non-IO→`/edit?nid=`); Playwright add+edit boot proofs (Task 2). Documented refinement: Edit uses the detail iframe (not full-page `ankiwebNavigate`).

**2. Placeholder scan:** No TBD/TODO. The upload handler, the io helpers, the shell fn, and the browser branch are complete and verbatim. The Playwright canvas selector is confirmed (`<canvas id="canvas">` from MaskEditor).

**3. Type/name consistency:** `import_tmp.io_dir`/`io_allocate`/`io_gc` (io subdir; `is_within` still accepts io/ paths since they're under `dir(settings)`). `POST /image-occlusion/upload` returns `{path}` (no notetype_id — add-mode self-resolves 0). `ankiwebImageOcclusion()` in `bootstrap.ts` (rebuilt). deck-browser `create` line += the IO button. browser `("select","open")` branch resolves `originalStockKind==6` via `col.models.get(col.get_note(nid).mid)` and sets the detail iframe `src` accordingly. Playwright add→`get_image_for_occlusion`, edit→`get_image_occlusion_note`.

**4. Risks:** the `io/` subdir is excluded from the import GC because `gc` is non-recursive (verified + a survival test); `io_gc` (24 h) + E7a's touch-on-read further protect a long session. The upload ensures the IO notetype (idempotent). The browser routing reads `originalStockKind` (robust vs renames; a non-IO note keeps `/edit?nid=`). `bootstrap.js` is regenerated + force-added (gitignored) — Task 1 commits both `.ts` and `.js`. The Playwright canvas selector + load-RPC assertions catch any route/serve regression; the fixture seeds both an `io/` image (add) and an IO note (edit). `add_image_occlusion_note` reads the temp image at request time (it exists); the media copy outlives the temp (tested).
