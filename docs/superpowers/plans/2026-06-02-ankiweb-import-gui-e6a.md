# ankiweb Plan E6a — GUI Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import CSV and `.apkg` files in the browser by reusing Anki's real compiled SvelteKit import pages — bridging "browser uploads bytes" to "backend wants a filesystem path" via an upload-to-temp endpoint, serving the import SPA routes, wiring the import RPCs (with path-confinement), and adding an "Import" entry to the deck browser.

**Architecture:** A new `POST /import/upload` accepts a multipart file, saves it to a **managed temp dir** (new `Settings.import_tmp_dir`), detects the route by extension, and returns `{route, path}`; the deck-browser "Import" button (JS in `bootstrap.ts`) uploads then navigates to `/import-csv/<temp-path>` or `/import-anki-package/<temp-path>` — **SvelteKit routes added to `build_sveltekit_router`** that serve the same `index.html` (the SPA client-routes on `location.pathname`, reads the path from the URL, and drives its column-mapping round-trip over `/_anki/` RPCs). The read RPCs `get_deck_names`/`get_field_names`/`get_import_anki_package_presets` are **passthrough**; `get_csv_metadata` is a **CUSTOM read** (it carries a path → must be path-confined); `importCsv`/`importAnkiPackage` are **CUSTOM writes** (path-confined + broadcast the returned `ImportLogWithChanges.changes`); `importDone` is a **CUSTOM no-op** (it raises `InvalidInput` via passthrough). Every path-bearing field (`CsvMetadataRequest.path`, `ImportCsvRequest.path`, `ImportAnkiPackageRequest.package_path`) is validated to resolve inside `import_tmp_dir` before reaching the backend.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the E1 `build_sveltekit_router`, the `anki_rpc` passthrough/CUSTOM mechanism (handlers take `(service, body, hub)` since E3), `fastapi.UploadFile` (`python-multipart` already a dep from D6), the shell `bootstrap.ts` (esbuild via `node tools/build_shell.mjs`), pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is E6a of Sub-project E6** (import/export). Spec: `docs/superpowers/specs/2026-06-02-ankiweb-import-export-e6-design.md`. Next: E6b (export), E6c (AnkiConnect import/export).

**Grounded facts (live-probed + spec-verified):**
- The SvelteKit routes `import-csv/[...path]` and `import-anki-package/[...path]` exist; `SVELTEKIT_PAGES` in `assets.py` already lists them. import-csv loads `getNotetypeNames`+`getDeckNames`+`getCsvMetadata`, re-fetches `getCsvMetadata`+`getFieldNames` on option change, submits `importCsv({path, metadata})`; import-anki-package loads `getImportAnkiPackagePresets({})`, submits `importAnkiPackage({packagePath, options})`. Both call `importDone({})` afterward (via the shared `import-page/ImportPage` wrapper — covered by serving the SPA shell wholesale). No host-bridge.
- Backend `*_raw` all exist: `get_csv_metadata`, `get_deck_names`, `get_field_names`, `get_import_anki_package_presets`, `import_csv`, `import_anki_package`. `get_notetype_names` already in PASSTHROUGH.
- `import_done_raw(b"")` RAISES `anki.errors.InvalidInput` ("InvalidServiceIndex") → CUSTOM no-op, NOT passthrough.
- CSV round-trip (probed): `col.get_csv_metadata(path=csv, delimiter=None)` returns a `CsvMetadata` with `global_notetype`+`deck_id` auto-detected; after `del meta.preview[:]`, `col.import_csv(ImportCsvRequest(path=csv, metadata=meta))` imports notes and returns `ImportLogWithChanges` with `.changes.note=True` (note_count 0→3 for a 3-line CSV).
- `ImportLogWithChanges` == `import_export_pb2.ImportResponse` (`.changes: OpChanges`, `.log`). `op_changes_to_flags` reads bool fields on an `OpChanges`.
- `Settings` is a frozen dataclass (`config.py`): `collection_path`, `host`, `port`, `assets_dir`, `shell_dir`. `CollectionService.__init__` stores `self._settings` (no public accessor yet). `CollectionService.close()` shuts the executor.
- `bootstrap.ts` defines `(window as any).ankiwebCreateDeck = () => {...}` (compiled to `bootstrap.js` via `node tools/build_shell.mjs`). The deck browser's create line is `deckbrowser.py:50-52`. `build_sveltekit_router` page routes use `return FileResponse(index, media_type="text/html")`.
- CUSTOM dispatch: `POST /_anki/{method}` → `if method in CUSTOM: await CUSTOM[method](service, body, get_hub())`; an exception → 500 + str(exc); `b""` out → 204. `service.backend_raw(snake, body)` runs `col._backend.<snake>_raw(body)`; `service.emit(flags, initiator)` broadcasts; `service.run(fn)` runs fn on the executor.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/config.py` (modify) | add `import_tmp_dir: Path` to `Settings` (+ env override) |
| `ankiweb/collection_service.py` (modify) | add a public `settings` property (handlers read `service.settings.import_tmp_dir`) |
| `ankiweb/import_tmp.py` (create) | the managed temp dir: `dir(settings)`, `allocate(settings, ext)`, `is_within(settings, path)`, `gc(settings, ttl)` |
| `ankiweb/screens/routes.py` (modify) | `POST /import/upload` (multipart → temp → `{route, path}`; lazy GC) |
| `ankiweb/assets.py` (modify) | `GET /import-csv/{path:path}` + `GET /import-anki-package/{path:path}` in `build_sveltekit_router` |
| `ankiweb/anki_rpc/passthrough.py` (modify) | add `get_deck_names`, `get_field_names`, `get_import_anki_package_presets` |
| `ankiweb/anki_rpc/handlers.py` (modify) | CUSTOM `getCsvMetadata` (path-confined read), `importCsv`/`importAnkiPackage` (path-confined write + broadcast), `importDone` (no-op) |
| `shell_src/bootstrap.ts` (modify) + recompile | `ankiwebImportFile()` (file picker → upload → navigate); rebuild `bootstrap.js` |
| `ankiweb/screens/deckbrowser.py` (modify) | an "Import" button calling `ankiwebImportFile()` |
| `tests/test_import_upload.py` (create) | Task 1: upload → temp/route; unknown ext → 400; routes serve shell; `settings` property |
| `tests/test_import_rpc.py` (create) | Task 2: passthrough/CUSTOM membership; path-confinement; importCsv round-trip; importDone→204 |
| `tests/test_import_integration.py` (create) | Task 3: Playwright — the import-csv SPA boots + loads via our routes |

---

## Task 1: upload-to-temp + temp manager + import SPA routes + Import button

**Files:** Modify `ankiweb/config.py`, `ankiweb/collection_service.py`, `ankiweb/assets.py`, `ankiweb/screens/routes.py`, `shell_src/bootstrap.ts`, `ankiweb/screens/deckbrowser.py`; Create `ankiweb/import_tmp.py`; Test `tests/test_import_upload.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_import_upload.py`:
```python
import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_settings_has_import_tmp_dir(tmp_path):
    s = Settings(collection_path=tmp_path / "c.anki2")
    assert isinstance(s.import_tmp_dir, Path)


def test_service_exposes_settings(client):
    assert client.app.state.service.settings.import_tmp_dir is not None


def test_upload_csv_returns_route_and_temp_path(client):
    files = {"file": ("notes.csv", io.BytesIO(b"front,back\na,b\n"), "text/csv")}
    r = client.post("/import/upload", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "import-csv"
    p = Path(body["path"])
    assert p.exists() and p.read_bytes() == b"front,back\na,b\n"
    # the temp file is inside the managed import dir
    from ankiweb import import_tmp
    assert import_tmp.is_within(client.app.state.service.settings, str(p))


def test_upload_apkg_routes_to_anki_package(client):
    files = {"file": ("deck.apkg", io.BytesIO(b"PK\x03\x04stub"), "application/octet-stream")}
    r = client.post("/import/upload", files=files)
    assert r.status_code == 200
    assert r.json()["route"] == "import-anki-package"


def test_upload_unknown_extension_400(client):
    files = {"file": ("note.xyz", io.BytesIO(b"x"), "application/octet-stream")}
    r = client.post("/import/upload", files=files)
    assert r.status_code == 400


def test_import_csv_route_serves_spa_shell(client):
    r = client.get("/import-csv/%2Ftmp%2Ffake.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "_app/immutable/entry" in r.text


def test_import_anki_package_route_serves_spa_shell(client):
    r = client.get("/import-anki-package/%2Ftmp%2Ffake.apkg")
    assert r.status_code == 200
    assert "_app/immutable/entry" in r.text


def test_gc_removes_old_files(client, tmp_path):
    import os, time
    from ankiweb import import_tmp
    s = client.app.state.service.settings
    p = import_tmp.allocate(s, ".csv")
    p.write_bytes(b"x")
    old = time.time() - 7200
    os.utime(p, (old, old))
    import_tmp.gc(s, ttl_seconds=3600)
    assert not p.exists()
```
(NOTE: `{path:path}` routes match a URL-encoded path even when the file doesn't exist — they just serve the SPA shell; the SPA's own `getCsvMetadata` call is what reads the file. `%2F` is an encoded `/`.)

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_import_upload.py -v` → FAIL.

- [ ] **Step 3: Add `Settings.import_tmp_dir`** — in `ankiweb/config.py`, add the field (default beside the collection) + env override:
```python
@dataclass(frozen=True)
class Settings:
    collection_path: Path
    host: str = "127.0.0.1"
    port: int = 8000
    assets_dir: Path = Path(__file__).parent / "web_assets"
    shell_dir: Path = Path(__file__).parent / "shell"
    import_tmp_dir: Path = Path(__file__).parent / "_import_tmp"
```
and in `from_env`, add: `import_tmp_dir=Path(os.environ["ANKIWEB_IMPORT_TMP_DIR"]) if os.environ.get("ANKIWEB_IMPORT_TMP_DIR") else (Path(os.environ.get("ANKIWEB_COLLECTION", str(default))).parent / "import-tmp")` — pass it as a kwarg in the `cls(...)` call. (Keep the dataclass default for direct `Settings(collection_path=...)` construction in tests.)

- [ ] **Step 4: Add the `settings` property** — in `ankiweb/collection_service.py`, add to `CollectionService`:
```python
    @property
    def settings(self):
        return self._settings
```

- [ ] **Step 5: Create `ankiweb/import_tmp.py`**:
```python
from __future__ import annotations
import secrets
import time
from pathlib import Path


def dir(settings) -> Path:
    d = Path(settings.import_tmp_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def allocate(settings, ext: str) -> Path:
    return dir(settings) / (secrets.token_hex(8) + ext)


def is_within(settings, candidate: str) -> bool:
    base = dir(settings).resolve()
    try:
        Path(candidate).resolve().relative_to(base)
        return True
    except (ValueError, OSError):
        return False


def gc(settings, ttl_seconds: int = 3600) -> None:
    base = dir(settings)
    now = time.time()
    for f in base.iterdir():
        try:
            if f.is_file() and now - f.stat().st_mtime > ttl_seconds:
                f.unlink()
        except OSError:
            pass
```

- [ ] **Step 6: Add the upload endpoint** — in `ankiweb/screens/routes.py` `build_screen_router`, add (mirror the existing `/upload_media`):
```python
    @router.post("/import/upload")
    async def import_upload(file: UploadFile):
        from fastapi.responses import JSONResponse
        from ankiweb import import_tmp
        service = get_service()
        import_tmp.gc(service.settings)  # lazy TTL sweep
        name = (file.filename or "").lower()
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        routes = {".csv": "import-csv", ".tsv": "import-csv", ".txt": "import-csv",
                  ".apkg": "import-anki-package", ".zip": "import-anki-package"}
        route = routes.get(ext)
        if route is None:
            return JSONResponse({"error": f"unsupported file type: {ext or '(none)'}"}, status_code=400)
        dest = import_tmp.allocate(service.settings, ext)
        dest.write_bytes(await file.read())
        return {"route": route, "path": str(dest)}
```

- [ ] **Step 7: Add the import SPA routes** — in `ankiweb/assets.py` `build_sveltekit_router`, next to the other page routes:
```python
    @router.get("/import-csv/{path:path}")
    def import_csv_page(path: str) -> Response:
        return FileResponse(index, media_type="text/html")

    @router.get("/import-anki-package/{path:path}")
    def import_anki_package_page(path: str) -> Response:
        return FileResponse(index, media_type="text/html")
```

- [ ] **Step 8: Add the Import button JS** — in `shell_src/bootstrap.ts`, after `ankiwebCreateDeck`:
```typescript
(window as any).ankiwebImportFile = () => {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".csv,.tsv,.txt,.apkg,.zip";
  input.onchange = async () => {
    const f = input.files && input.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    const resp = await fetch("/import/upload", { method: "POST", body: fd });
    if (!resp.ok) { window.alert("Import failed: " + (await resp.text())); return; }
    const { route, path } = await resp.json();
    window.location.href = "/" + route + "/" + encodeURIComponent(path);
  };
  input.click();
};
```
Then recompile: `node tools/build_shell.mjs` (regenerates the git-tracked `ankiweb/shell/static/bootstrap.js`).

- [ ] **Step 9: Add the deck-browser Import button** — in `ankiweb/screens/deckbrowser.py` `render_deckbrowser_html`, extend the `create` line:
```python
    create = ("<button onclick='ankiwebCreateDeck()'>Create Deck</button>"
              " <button onclick='pycmd(\"createfiltered\")'>Create Filtered Deck</button>"
              " <button onclick='ankiwebImportFile()'>Import</button>"
              " <a href='/graphs'>Stats</a>")
```

- [ ] **Step 10: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_import_upload.py -v`, then regression: `conda run -n ankiweb python -m pytest tests/test_deckbrowser.py tests/test_graphs.py tests/test_screen_routes.py -q`.

- [ ] **Step 11: Commit**
```bash
git add ankiweb/config.py ankiweb/collection_service.py ankiweb/import_tmp.py ankiweb/screens/routes.py ankiweb/assets.py shell_src/bootstrap.ts ankiweb/shell/static/bootstrap.js ankiweb/screens/deckbrowser.py tests/test_import_upload.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(import): upload-to-temp endpoint + import SPA routes + deck-browser Import button"
```

## Context
The upload endpoint bridges browser bytes → the backend's path-based import API: it saves the multipart file to `Settings.import_tmp_dir` (a managed dir under the collection's parent), GCs stale files, and returns `{route, path}`. The deck-browser "Import" button (JS in the shell) uploads then navigates to the matching SvelteKit import route (added to `build_sveltekit_router`), which serves the SPA shell. The RPC wiring (Task 2) makes the page functional.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns (incl. whether `from_env` needed adjusting and that `bootstrap.js` was regenerated).

---

## Task 2: import RPC wiring (passthrough + path-confined CUSTOM handlers + importDone)

**Files:** Modify `ankiweb/anki_rpc/passthrough.py`, `ankiweb/anki_rpc/handlers.py`; Test `tests/test_import_rpc.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_import_rpc.py`:
```python
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_passthrough_and_custom_registered():
    from ankiweb.anki_rpc.passthrough import PASSTHROUGH
    from ankiweb.anki_rpc.handlers import CUSTOM
    for m in ("get_deck_names", "get_field_names", "get_import_anki_package_presets"):
        assert m in PASSTHROUGH, m
    for m in ("getCsvMetadata", "importCsv", "importAnkiPackage", "importDone"):
        assert m in CUSTOM, m


def test_import_done_is_noop_204(client):
    r = client.post("/_anki/importDone", content=b"",
                    headers={"content-type": "application/binary"})
    assert r.status_code == 204


def _write_csv_in_tmp(client, text=b"front,back\nhello,world\nfoo,bar\n"):
    from ankiweb import import_tmp
    p = import_tmp.allocate(client.app.state.service.settings, ".csv")
    p.write_bytes(text)
    return str(p)


def test_get_csv_metadata_rejects_path_outside_tmp(client):
    import anki.import_export_pb2 as ie
    req = ie.CsvMetadataRequest(path="/etc/hostname")
    r = client.post("/_anki/getCsvMetadata", content=req.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 500   # rejected before the backend (path not allowed)


def test_get_csv_metadata_accepts_path_in_tmp(client):
    import anki.import_export_pb2 as ie
    path = _write_csv_in_tmp(client)
    req = ie.CsvMetadataRequest(path=path)
    r = client.post("/_anki/getCsvMetadata", content=req.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 200


def test_import_csv_round_trip_imports_notes(client):
    import anki.import_export_pb2 as ie
    svc = client.app.state.service
    path = _write_csv_in_tmp(client)
    before = client.portal.call(svc.run, lambda col: col.note_count())
    meta = client.portal.call(svc.run, lambda col: col.get_csv_metadata(path=path, delimiter=None))
    del meta.preview[:]
    req = ie.ImportCsvRequest(path=path, metadata=meta)
    r = client.post("/_anki/importCsv", content=req.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 200
    after = client.portal.call(svc.run, lambda col: col.note_count())
    assert after > before


def test_import_csv_rejects_path_outside_tmp(client):
    import anki.import_export_pb2 as ie
    req = ie.ImportCsvRequest(path="/etc/passwd", metadata=ie.CsvMetadata())
    r = client.post("/_anki/importCsv", content=req.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 500
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_import_rpc.py -v` → FAIL.

- [ ] **Step 3: Extend the passthrough** — in `ankiweb/anki_rpc/passthrough.py`, add to `PASSTHROUGH`:
```python
    "get_deck_names", "get_field_names", "get_import_anki_package_presets",
```

- [ ] **Step 4: Add the CUSTOM import handlers** — in `ankiweb/anki_rpc/handlers.py`:
```python
async def _emit_import_changes(service, out: bytes) -> None:
    try:
        import anki.import_export_pb2 as ie
        from ankiweb.collection_service import op_changes_to_flags
        resp = ie.ImportResponse()
        resp.ParseFromString(bytes(out))
        flags = op_changes_to_flags(resp.changes)
        if any(flags.values()):
            await service.emit(flags, "import")
    except Exception:
        pass


async def get_csv_metadata(service, body: bytes, hub) -> bytes:
    import anki.import_export_pb2 as ie
    from ankiweb import import_tmp
    req = ie.CsvMetadataRequest()
    req.ParseFromString(bytes(body))
    if req.path and not import_tmp.is_within(service.settings, req.path):
        raise ValueError("import path not allowed")
    return await service.backend_raw("get_csv_metadata", body)


async def import_csv(service, body: bytes, hub) -> bytes:
    import anki.import_export_pb2 as ie
    from ankiweb import import_tmp
    req = ie.ImportCsvRequest()
    req.ParseFromString(bytes(body))
    if not import_tmp.is_within(service.settings, req.path):
        raise ValueError("import path not allowed")
    out = await service.backend_raw("import_csv", body)
    await _emit_import_changes(service, out)
    return out


async def import_anki_package(service, body: bytes, hub) -> bytes:
    import anki.import_export_pb2 as ie
    from ankiweb import import_tmp
    req = ie.ImportAnkiPackageRequest()
    req.ParseFromString(bytes(body))
    if not import_tmp.is_within(service.settings, req.package_path):
        raise ValueError("import path not allowed")
    out = await service.backend_raw("import_anki_package", body)
    await _emit_import_changes(service, out)
    return out


CUSTOM["getCsvMetadata"] = get_csv_metadata
CUSTOM["importCsv"] = import_csv
CUSTOM["importAnkiPackage"] = import_anki_package
CUSTOM["importDone"] = _noop
```
(`_noop` already exists in `handlers.py` from E2. The dispatch returns 500 + str(exc) when `ValueError` is raised, which the SvelteKit page surfaces.)

- [ ] **Step 5: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_import_rpc.py -v`, then regression: `conda run -n ankiweb python -m pytest tests/test_anki_rpc.py tests/test_deck_options.py tests/test_change_notetype.py -q`.

- [ ] **Step 6: Commit**
```bash
git add ankiweb/anki_rpc/passthrough.py ankiweb/anki_rpc/handlers.py tests/test_import_rpc.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(import): path-confined import RPC handlers (getCsvMetadata/importCsv/importAnkiPackage) + importDone no-op"
```

## Context
The page's read RPCs are passthrough except `getCsvMetadata` (carries a path → CUSTOM read that confines it). The write RPCs `importCsv`/`importAnkiPackage` confine their path (`ImportCsvRequest.path` / `ImportAnkiPackageRequest.package_path`), call the backend, and broadcast the returned `ImportLogWithChanges.changes`. `importDone` is the existing `_noop` (it raises via passthrough). Path-confinement rejects any path outside `import_tmp_dir` with a 500 before the backend runs.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 3: Playwright — the import-csv SPA boots + loads through our routes

**Files:** Create `tests/test_import_integration.py`.

- [ ] **Step 1: Write the test** — mirror the E1–E5 `live_server` (uvicorn thread, fresh port 8135, `pytest.importorskip`, inline `sync_playwright`). Pre-write a CSV INTO the server's `import_tmp_dir`, then open `/import-csv/<encoded path>` and assert the SPA boots + `getCsvMetadata` POST fired + no errors:
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


@pytest.fixture
def live_server_imp(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    Collection(str(col_path)).close()
    tmp_dir = tmp_path / "import-tmp"
    tmp_dir.mkdir()
    csv = tmp_dir / "notes.csv"
    csv.write_text("front,back\nhello,world\nfoo,bar\n")
    settings = Settings(collection_path=col_path, port=8135, import_tmp_dir=tmp_dir)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8135, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8135", str(csv)
    server.should_exit = True
    t.join(timeout=5)


def test_import_csv_spa_boots(live_server_imp):
    url, csv_path = live_server_imp
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed",
                lambda r: errors.append("REQFAIL " + r.url) if ("/_app/" in r.url or "/_anki/" in r.url) else None)
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/_anki/" in r.url else None)
        page.goto(f"{url}/import-csv/{quote(csv_path, safe='')}")
        page.wait_for_function("document.querySelectorAll('select,button,table,input').length>2", timeout=10000)
        page.wait_for_function("document.body.innerText.length>30", timeout=10000)
        assert not errors, errors
        assert any("get_csv_metadata" in u.lower() or "getcsvmetadata" in u.lower() for u in posts), posts
        browser.close()
```
(NOTE: pick the most stable mount selector by inspecting the rendered import-csv page — it has the field-mapping table + notetype/deck `<select>`s + an import button. Load-bearing asserts: no `/_app/`-or-`/_anki/` request failed, no page error, and the `getCsvMetadata` POST fired through our route. If a benign error appears, narrow the filter with a comment; never weaken the load-bearing asserts.)

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_import_integration.py -v` (PASS if chromium available; SKIPS if not). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_import_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(import): Playwright — the import-csv SPA boots + loads through our routes"
```

## Context
End-to-end proof the real import-csv SvelteKit page boots through ankiweb's routes: fetches its `/_app/` chunks, POSTs `getCsvMetadata` (path-confined) to `/_anki/`, and renders its mapping UI with zero errors. The upload mechanism is proven by Task 1; the actual import write path by Task 2's round-trip.

## Report Format
Status, pytest summary (Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (E6a = GUI import):** `POST /import/upload` → temp + route detection + lazy GC (Task 1); `Settings.import_tmp_dir` + `service.settings` (Task 1); import SPA routes `/import-csv/{path}` + `/import-anki-package/{path}` (Task 1); deck-browser Import button + `ankiwebImportFile` (Task 1); passthrough `get_deck_names`/`get_field_names`/`get_import_anki_package_presets` (Task 2); CUSTOM path-confined `getCsvMetadata` (read), `importCsv`/`importAnkiPackage` (write + broadcast `.changes`), `importDone` no-op (Task 2); path-confinement on all three path fields (Task 2, tested in/out of tmp); Playwright boot+load (Task 3). Mnemosyne/JSON import-page is out of scope (deferred).

**2. Placeholder scan:** No TBD/TODO. `import_tmp.py` is complete (allocate/is_within/gc). The `from_env` change is spelled out. The Playwright mount selector is confirmed-by-inspection (load-bearing asserts = no-errors + getCsvMetadata POST fired).

**3. Type/name consistency:** `Settings.import_tmp_dir: Path`; `CollectionService.settings` property → `service.settings.import_tmp_dir`; `import_tmp.{dir,allocate,is_within,gc}(settings, …)`. RPC: passthrough adds the 3 read methods; CUSTOM adds `getCsvMetadata`/`importCsv`/`importAnkiPackage` (handlers parse `anki.import_export_pb2.{CsvMetadataRequest,ImportCsvRequest,ImportAnkiPackageRequest}`, confine `req.path`/`req.package_path` via `import_tmp.is_within(service.settings, …)`, `service.backend_raw(...)`, `_emit_import_changes` parses `ImportResponse.changes` via `op_changes_to_flags` + `service.emit`), `importDone`→existing `_noop`. `build_sveltekit_router` adds the 2 `{path:path}` routes. `ankiwebImportFile` in `bootstrap.ts` (recompiled). All handlers use the `(service, body, hub)` signature (E3).

**4. Risks:** path-confinement MUST run before the backend touches the path (tested with in-tmp + out-of-tmp paths → 200 vs 500). `getCsvMetadata` moved from "passthrough" (spec) to CUSTOM because it carries a path — documented here. `bootstrap.js` is regenerated from `bootstrap.ts` and git-tracked (Task 1 commits both). Route ordering: the 2 import routes live in `build_sveltekit_router` (already before the media catch-all). The lazy GC runs on each upload (cheap; 60-min TTL). The CSV round-trip imports the header row as a note too (no header detection in the default metadata) — the test only asserts the count increased, which is correct. `python-multipart` is already a dep (D6). Large uploads load fully into memory (`await file.read()`) — acceptable for local single-user.
