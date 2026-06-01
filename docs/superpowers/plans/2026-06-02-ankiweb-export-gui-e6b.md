# ankiweb Plan E6b — GUI Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export to `.apkg` / `.colpkg` / notes-CSV / cards-CSV via a rebuilt server-rendered form (export is Qt-only — no SvelteKit page); the form POSTs to `/export`, the backend writes a temp file, and the server streams it back as a browser download. Launched from a deck-browser "Export" link.

**Architecture:** A `GET /export` server-rendered form (`render_export_html(col)`): a target `<select>` (Whole Collection / each non-filtered deck via `col.decks.all_names_and_ids`), format radios (`.apkg`/`.colpkg`/notes-CSV/cards-CSV), and option checkboxes (a "Package options" group for apkg/colpkg, a "CSV options" group for the CSV formats; a tiny inline script toggles which group shows + disables the target for colpkg). **The form submits a plain `POST /export`** (NOT the WS bridge that E4/E5 use — a binary file download needs an HTTP response body): the handler builds the `ExportLimit` (whole-collection via `lim.whole_collection.SetInParent()`, vs `deck_id=int`) + the format-specific request, runs the backend export to a `tempfile` out-path on the collection executor, and returns a `FileResponse(out, media_type, filename, background=delete-temp)` (`Content-Disposition: attachment`). **For `.colpkg` only**, `export_collection_package` KILLS the live collection, so the handler calls a new `CollectionService.reopen()` immediately after to revive it. On a backend error the handler re-renders the form with an inline message (never a partial download).

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the server-rendered screen framework (`render_page`), `fastapi.Form` + `fastapi.responses.FileResponse` + `starlette.background.BackgroundTask`, `col.sched`/`col.export_*`, `anki.import_export_pb2.{ExportLimit, ExportAnkiPackageOptions}`, pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is E6b of Sub-project E6** (import/export). Spec: `docs/superpowers/specs/2026-06-02-ankiweb-import-export-e6-design.md`. Builds on E6a (which added `import_tmp`/`service.settings`/the import flow). Next: E6c (AnkiConnect import/export).

**Grounded facts (live-probed):**
- `col.decks.all_names_and_ids(skip_empty_default=False, include_filtered=False) -> Sequence[DeckNameId]` (each `.name`, `.id`). (Probed: `[('Default', 1), ('Sub', ...)]`.)
- `col.export_anki_package(*, out_path, options: ExportAnkiPackageOptions, limit: ExportLimit) -> int` (keyword-only). `ExportAnkiPackageOptions(with_scheduling, with_media, with_deck_configs, legacy)`. Probed: a deck-limited apkg export wrote a 59 KB file, count=1.
- `col.export_collection_package(out_path, include_media, legacy) -> None` (POSITIONAL). **Probed: this CLOSES the live collection** — afterward `col.card_count()` raises `AttributeError`; a fresh `Collection(path)` reopens it (card_count works). Ignores any limit (always whole-collection).
- `col.export_note_csv(*, out_path, limit, with_html, with_tags, with_deck, with_notetype, with_guid) -> int` (keyword-only). Probed: a whole-collection notes-CSV wrote a 95-byte file.
- `col.export_card_csv(*, out_path, limit, with_html) -> int` (keyword-only).
- `ExportLimit` oneof: `whole_collection` (a `google.protobuf.Empty` MESSAGE — set via `lim.whole_collection.SetInParent()`; `ExportLimit(whole_collection=True)` raises `TypeError`) | `deck_id` (int). Probed both.
- `CollectionService`: `open()` does `self._col = await loop.run_in_executor(self._executor, lambda: Collection(str(path), server=False))`; `close()` ALSO `self._executor.shutdown()`s (so `reopen()` must NOT reuse `close()`). `self._settings.collection_path` is the path. `self._lock` (asyncio.Lock) serializes. `service.run(fn)` runs `fn(col)` on the executor under the lock; `service.settings` property exists (E6a).
- The deck browser's create line (`deckbrowser.py`) currently: `Create Deck` + `Create Filtered Deck` + `Import` + `<a href='/graphs'>Stats</a>`. FastAPI `bool = Form(False)` parses an HTML checkbox: checked → "on" → True (pydantic v2 bool coercion); unchecked → absent → default False.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/screens/export.py` (create) | `render_export_html(col)` — the export form (target/format/options + toggle JS) |
| `ankiweb/collection_service.py` (modify) | add `async reopen()` — re-acquire `self._col` on the executor without shutting it down |
| `ankiweb/screens/routes.py` (modify) | `GET /export` (render the form) + `POST /export` (build request → export to temp → `FileResponse` download; reopen after colpkg; re-render on error) |
| `ankiweb/screens/deckbrowser.py` (modify) | an "Export" link → `/export` |
| `tests/test_export.py` (create) | route renders; apkg (whole + deck) / notes-csv / cards-csv downloads; colpkg + collection-still-usable (reopen guard); deck-browser link |
| `tests/test_export_integration.py` (create) | Playwright: the form renders + submitting triggers a file download |

---

## Task 1: the `/export` form + `POST /export` download + `reopen()`

**Files:** Create `ankiweb/screens/export.py`; modify `ankiweb/collection_service.py`, `ankiweb/screens/routes.py`, `ankiweb/screens/deckbrowser.py`; Test `tests/test_export.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_export.py`:
```python
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "c.anki2",
                        import_tmp_dir=tmp_path / "import-tmp")
    with TestClient(create_app(settings)) as c:
        yield c


def _seed(client, n=2):
    def seed(col):
        did = col.decks.id("Default")
        for i in range(n):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = f"f{i}"; note["Back"] = f"b{i}"
            col.add_note(note, did)
        return did
    return client.portal.call(client.app.state.service.run, seed)


def test_export_route_renders_form(client):
    _seed(client)
    r = client.get("/export")
    assert r.status_code == 200
    body = r.text
    assert "Whole Collection" in body
    assert "Default" in body
    assert "value='apkg'" in body and "value='colpkg'" in body
    assert "value='notes_csv'" in body and "value='cards_csv'" in body


def _assert_download(r, ext):
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert ext in r.headers.get("content-disposition", "")
    assert len(r.content) > 0


def test_export_apkg_whole_collection(client):
    _seed(client)
    r = client.post("/export", data={"fmt": "apkg", "target": "all",
                                     "with_media": "on", "legacy": "on"})
    _assert_download(r, ".apkg")


def test_export_apkg_deck(client):
    did = _seed(client)
    r = client.post("/export", data={"fmt": "apkg", "target": str(did), "legacy": "on"})
    _assert_download(r, ".apkg")


def test_export_notes_csv(client):
    _seed(client)
    r = client.post("/export", data={"fmt": "notes_csv", "target": "all",
                                     "with_tags": "on", "with_deck": "on", "with_notetype": "on"})
    _assert_download(r, ".csv")


def test_export_cards_csv(client):
    _seed(client)
    r = client.post("/export", data={"fmt": "cards_csv", "target": "all"})
    _assert_download(r, ".csv")


def test_export_colpkg_then_collection_still_usable(client):
    _seed(client)
    r = client.post("/export", data={"fmt": "colpkg", "with_media": "on", "legacy": "on"})
    _assert_download(r, ".colpkg")
    # the reopen() guard: export_collection_package killed the live collection;
    # the service must have revived it.
    count = client.portal.call(client.app.state.service.run, lambda col: col.card_count())
    assert count == 2


def test_deckbrowser_has_export_link(client):
    _seed(client)
    r = client.get("/deckbrowser")
    assert "/export" in r.text
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_export.py -v` → FAIL.

- [ ] **Step 3: Add `CollectionService.reopen()`** — in `ankiweb/collection_service.py`, add to `CollectionService` (next to `open`/`close`; uses the same `asyncio`/`Collection` already imported):
```python
    async def reopen(self) -> None:
        """Re-open the collection on the worker WITHOUT shutting it down — for ops
        that close it (export_collection_package). Unlike close(), keeps the executor."""
        path = self._settings.collection_path
        loop = asyncio.get_event_loop()
        async with self._lock:
            self._col = await loop.run_in_executor(
                self._executor, lambda: Collection(str(path), server=False))
```

- [ ] **Step 4: Create `ankiweb/screens/export.py`**:
```python
from __future__ import annotations
import html


def render_export_html(col) -> str:
    decks = col.decks.all_names_and_ids(skip_empty_default=False, include_filtered=False)
    opts = "".join(
        f"<option value='{d.id}'>{html.escape(d.name)}</option>" for d in decks)
    body = f"""
<div class='export'>
  <h3>Export</h3>
  <form id='ex' method='post' action='/export'>
    <div><label>Export: <select name='target' id='target'>
      <option value='all'>Whole Collection</option>{opts}</select></label></div>
    <fieldset><legend>Format</legend>
      <label><input type='radio' name='fmt' value='apkg' checked onchange='onFmt()'> Anki Deck Package (.apkg)</label><br>
      <label><input type='radio' name='fmt' value='colpkg' onchange='onFmt()'> Anki Collection Package (.colpkg)</label><br>
      <label><input type='radio' name='fmt' value='notes_csv' onchange='onFmt()'> Notes in Plain Text (.csv)</label><br>
      <label><input type='radio' name='fmt' value='cards_csv' onchange='onFmt()'> Cards in Plain Text (.csv)</label>
    </fieldset>
    <fieldset id='pkgopts'><legend>Package options</legend>
      <label><input type='checkbox' name='with_scheduling'> Include scheduling information</label><br>
      <label><input type='checkbox' name='with_media' checked> Include media</label><br>
      <label><input type='checkbox' name='with_deck_configs'> Include deck presets</label><br>
      <label><input type='checkbox' name='legacy' checked> Support older Anki versions</label>
    </fieldset>
    <fieldset id='csvopts' style='display:none;'><legend>CSV options</legend>
      <label><input type='checkbox' name='with_html'> Include HTML and media references</label><br>
      <label><input type='checkbox' name='with_tags' checked> Include tags</label><br>
      <label><input type='checkbox' name='with_deck' checked> Include deck</label><br>
      <label><input type='checkbox' name='with_notetype' checked> Include notetype</label><br>
      <label><input type='checkbox' name='with_guid'> Include unique identifier</label>
    </fieldset>
    <div style='margin-top:10px;'>
      <button type='submit' id='go'>Export</button>
      <a href='/deckbrowser'>Cancel</a>
    </div>
  </form>
</div>
<script>
function onFmt() {{
  var f = document.querySelector("input[name='fmt']:checked").value;
  var pkg = (f === 'apkg' || f === 'colpkg');
  document.getElementById('pkgopts').style.display = pkg ? '' : 'none';
  document.getElementById('csvopts').style.display = pkg ? 'none' : '';
  document.getElementById('target').disabled = (f === 'colpkg');
}}
onFmt();
</script>
"""
    return body
```

- [ ] **Step 5: Add the routes** — in `ankiweb/screens/routes.py`: import `from ankiweb.screens.export import render_export_html`, `from fastapi import Form`, `from fastapi.responses import FileResponse`, `from starlette.background import BackgroundTask`, and `import os, tempfile`. Then inside `build_screen_router`:
```python
    @router.get("/export", response_class=HTMLResponse)
    async def export_page():
        service = get_service()
        body = await service.run(render_export_html)
        return HTMLResponse(render_page("export", body))

    @router.post("/export")
    async def export_post(
        target: str = Form("all"),
        fmt: str = Form("apkg"),
        with_scheduling: bool = Form(False),
        with_media: bool = Form(False),
        with_deck_configs: bool = Form(False),
        legacy: bool = Form(False),
        with_html: bool = Form(False),
        with_tags: bool = Form(False),
        with_deck: bool = Form(False),
        with_notetype: bool = Form(False),
        with_guid: bool = Form(False),
    ):
        import anki.import_export_pb2 as ie
        service = get_service()

        def make_limit():
            lim = ie.ExportLimit()
            if target == "all":
                lim.whole_collection.SetInParent()
            else:
                lim.deck_id = int(target)
            return lim

        suffix = {"apkg": ".apkg", "colpkg": ".colpkg",
                  "notes_csv": ".csv", "cards_csv": ".csv"}.get(fmt, ".apkg")
        fd, out = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            if fmt == "apkg":
                opts = ie.ExportAnkiPackageOptions(
                    with_scheduling=with_scheduling, with_media=with_media,
                    with_deck_configs=with_deck_configs, legacy=legacy)
                lim = make_limit()
                await service.run(lambda col: col.export_anki_package(
                    out_path=out, options=opts, limit=lim))
                filename, media = "export.apkg", "application/octet-stream"
            elif fmt == "colpkg":
                await service.run(lambda col: col.export_collection_package(
                    out, with_media, legacy))
                await service.reopen()  # export_collection_package closed the collection
                filename, media = "collection.colpkg", "application/octet-stream"
            elif fmt == "notes_csv":
                lim = make_limit()
                await service.run(lambda col: col.export_note_csv(
                    out_path=out, limit=lim, with_html=with_html, with_tags=with_tags,
                    with_deck=with_deck, with_notetype=with_notetype, with_guid=with_guid))
                filename, media = "notes.csv", "text/csv"
            elif fmt == "cards_csv":
                lim = make_limit()
                await service.run(lambda col: col.export_card_csv(
                    out_path=out, limit=lim, with_html=with_html))
                filename, media = "cards.csv", "text/csv"
            else:
                os.remove(out)
                return HTMLResponse("unknown export format", status_code=400)
        except Exception as exc:
            try:
                os.remove(out)
            except OSError:
                pass
            body = await service.run(render_export_html)
            return HTMLResponse(render_page(
                "export", f"<div style='color:#c00'>Export failed: {exc}</div>" + body))
        return FileResponse(out, media_type=media, filename=filename,
                            background=BackgroundTask(os.remove, out))
```
(NOTE: a disabled `<select>` is not submitted, so colpkg's disabled target falls back to `target="all"` — correct, colpkg is always whole-collection. `bool = Form(False)` reads HTML checkboxes. `FileResponse` reads the file as the response and the `BackgroundTask` deletes the temp after sending.)

- [ ] **Step 6: Add the deck-browser Export link** — in `ankiweb/screens/deckbrowser.py` `render_deckbrowser_html`, extend the `create` line (it currently ends with the Stats link):
```python
    create = ("<button onclick='ankiwebCreateDeck()'>Create Deck</button>"
              " <button onclick='pycmd(\"createfiltered\")'>Create Filtered Deck</button>"
              " <button onclick='ankiwebImportFile()'>Import</button>"
              " <a href='/export'>Export</a>"
              " <a href='/graphs'>Stats</a>")
```

- [ ] **Step 7: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_export.py -v`, then regression: `conda run -n ankiweb python -m pytest tests/test_deckbrowser.py tests/test_screen_routes.py tests/test_import_upload.py tests/test_import_rpc.py -q`.

- [ ] **Step 8: Commit**
```bash
git add ankiweb/screens/export.py ankiweb/collection_service.py ankiweb/screens/routes.py ankiweb/screens/deckbrowser.py tests/test_export.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(export): server-rendered export form + POST /export FileResponse download + CollectionService.reopen() for colpkg"
```

## Context
`/export` is a server-rendered REBUILD (export is Qt-only). The form POSTs to `/export` (a real HTTP POST, not the WS bridge, because the response IS the file download). The handler maps the chosen format to `col.export_anki_package`/`export_collection_package`/`export_note_csv`/`export_card_csv`, writes a temp file on the collection executor, and streams it back with `Content-Disposition: attachment`. `.colpkg` export closes the live collection, so the handler calls the new `CollectionService.reopen()` right after to revive it (proven by `test_export_colpkg_then_collection_still_usable`). The deck browser gains an "Export" link.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns (incl. the colpkg reopen guard result + any Form/checkbox parsing surprise).

---

## Task 2: Playwright — the export form renders + submitting downloads a file

**Files:** Create `tests/test_export_integration.py`.

- [ ] **Step 1: Write the test** — mirror the E6a `live_server` (uvicorn thread, fresh port 8136, `pytest.importorskip`, inline `sync_playwright`). Seed notes; open `/export`; assert the form renders; submit (default apkg) and assert a download fires:
```python
import threading
import time
from pathlib import Path
import pytest
import uvicorn
from anki.collection import Collection
from ankiweb.config import Settings
from ankiweb.app import create_app

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


@pytest.fixture
def live_server_exp(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    col = Collection(str(col_path))
    try:
        did = col.decks.id("Default")
        for i in range(2):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"] = f"f{i}"; n["Back"] = f"b{i}"
            col.add_note(n, did)
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8136,
                        import_tmp_dir=tmp_path / "import-tmp")
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8136, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8136"
    server.should_exit = True
    t.join(timeout=5)


def test_export_form_downloads(live_server_exp):
    url = live_server_exp
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{url}/export")
        page.wait_for_selector("#go", timeout=10000)
        assert "Export" in page.inner_text("body")
        with page.expect_download(timeout=15000) as dl:
            page.click("#go")
        download = dl.value
        assert download.suggested_filename.endswith(".apkg")
        assert not errors, errors
        browser.close()
```
(NOTE: `page.expect_download` captures the browser download triggered by the form POST returning a `FileResponse` with `Content-Disposition: attachment`. Default format is apkg → filename `export.apkg`. Load-bearing asserts: the form rendered (`#go` + "Export" text), a download fired with the `.apkg` name, no page error. If the inline toggle script errors, the `pageerror` listener catches it — fix `export.py`.)

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_export_integration.py -v` (PASS if chromium available; SKIPS if not). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_export_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(export): Playwright — the export form renders and submitting downloads a file"
```

## Context
End-to-end proof the rebuilt export form works in a real browser: renders the target/format/options controls, and submitting the form triggers a browser file download (the `POST /export` → `FileResponse` round-trip). The per-format correctness + the colpkg reopen guard are covered by Task 1.

## Report Format
Status, pytest summary (Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (E6b = GUI export):** `GET /export` server-rendered form with target dropdown (whole/deck) + 4 format radios + package/CSV option groups (Task 1); `POST /export` builds the `ExportLimit` (whole via `SetInParent()`, deck via `deck_id=int`) + format-specific request, exports to a temp on the executor, returns a `FileResponse` download (Task 1, tested apkg-whole/apkg-deck/notes-csv/cards-csv); `CollectionService.reopen()` after `.colpkg` (Task 1, tested via the collection-still-usable guard); deck-browser Export link (Task 1); error → re-render form (Task 1 code path); Playwright download proof (Task 2). Note/card-id limits remain out of core (no Browser changes), per the spec.

**2. Placeholder scan:** No TBD/TODO. The form HTML + toggle JS + the full `POST /export` handler are verbatim. `reopen()` is spelled out (no executor shutdown).

**3. Type/name consistency:** `render_export_html(col)` in `export.py`; `GET /export`→`render_page("export", body)`; `POST /export` with `Form(...)` params; `ie.ExportLimit`/`ie.ExportAnkiPackageOptions`; `col.export_anki_package(out_path=, options=, limit=)` / `export_collection_package(out, media, legacy)` / `export_note_csv(out_path=, limit=, with_*=)` / `export_card_csv(out_path=, limit=, with_html=)`; `CollectionService.reopen()` re-acquires `self._col` on `self._executor` under `self._lock`. `FileResponse(out, media_type, filename, background=BackgroundTask(os.remove, out))`. deck-browser create line gains `<a href='/export'>Export</a>`.

**4. Risks:** `export_collection_package` kills the collection — the handler `await service.reopen()` revives it BEFORE returning (tested: card_count==2 after). The disabled colpkg target falls back to `target="all"` (correct). HTML checkbox→`bool` Form coercion (pydantic v2 accepts "on"). The temp file is deleted by the response `BackgroundTask` after streaming (TestClient runs background tasks post-response, so `r.content` is read first). A backend export error re-renders the form (no partial file; the temp is removed). The export runs on the single-worker executor (serialized with all other collection ops). Large exports load into a temp file on disk (not memory) — fine. `render_page("export", ...)` connects a WS (context=export) with no handler — harmless (the form uses POST, not pycmd).
