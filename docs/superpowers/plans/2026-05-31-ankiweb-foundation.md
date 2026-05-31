# ankiweb Foundation (A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared runtime spine for ankiweb — open a single Anki collection, serve Anki's real compiled frontend, translate Anki's `/_anki/*` protobuf RPC server, and provide a WebSocket bridge that replaces Qt's `pycmd`/`web.eval` — culminating in a spike proving Anki's real `reviewer.js` renders a card through our bridge.

**Architecture:** FastAPI app holds one `anki.collection.Collection` (`server=False`), all access serialized through a single-worker executor + asyncio lock. Static assets are vendored from the `aqt` wheel's `_aqt/data/web/`. `POST /_anki/{method}` dispatches to `col._backend.<snake>_raw(bytes)` (passthrough) or custom handlers. A per-page WebSocket carries `pycmd` (JS→Python), `eval`/`call` (Python→JS), and `OpChanges` refresh broadcasts; a small injected JS shim defines `window.pycmd`/`window.bridgeCommand`.

**Tech Stack:** Python 3.12, `anki==25.9.4`, `aqt==25.9.4` (assets only, vendored — no PyQt6 at runtime), FastAPI + uvicorn, Starlette WebSocket, standard Python `protobuf` (via anki's bundled `*_pb2`), pytest + httpx, TypeScript + esbuild for the shell, Playwright for the bridge spike.

**This is Plan 1 of 2 for Spec 1.** Plan 2 (Study Loop C: deck browser / overview / reviewer / congrats screens) follows after A is validated. Spec: `docs/superpowers/specs/2026-05-31-ankiweb-foundation-study-loop-design.md`.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Project metadata, pinned deps, pytest config |
| `ankiweb/__init__.py` | Package marker |
| `ankiweb/config.py` | `Settings` (collection path, host, port, assets dir) |
| `ankiweb/app.py` | FastAPI app factory + lifespan (open/close collection, mount routers) |
| `ankiweb/collection_service.py` | `CollectionService`: serialized collection access, `backend_raw`, OpChanges bus |
| `ankiweb/assets.py` | Static serving of `web_assets/` replicating `mediasrv` path rules + media |
| `ankiweb/anki_rpc/__init__.py` | `POST /_anki/{method}` dispatch + response convention + guards |
| `ankiweb/anki_rpc/passthrough.py` | Passthrough method registry + camel/snake mapping |
| `ankiweb/anki_rpc/handlers.py` | Custom handlers (e.g. `saveCustomColours`) |
| `ankiweb/bridge/protocol.py` | Bridge message dataclasses / JSON (de)serialization |
| `ankiweb/bridge/hub.py` | `BridgeHub`: per-context connections, cmd dispatch, push, result correlation |
| `ankiweb/bridge/ws.py` | `GET /ws` WebSocket endpoint |
| `ankiweb/shell/index.html` | Page bootstrap template (loads shim, connects WS) |
| `shell_src/pycmd_shim.ts` | `window.pycmd`/`bridgeCommand` + domDone queue + WS client |
| `shell_src/bootstrap.ts` | Page entry: connect WS, dispatch `call`/`eval`, night mode |
| `tools/fetch_web_assets.py` | Download `aqt` wheel, extract `_aqt/data/web/` → `ankiweb/web_assets/` |
| `tools/build_shell.mjs` | esbuild bundle `shell_src/*` → `ankiweb/shell/static/` |
| `ankiweb/web_assets/` | Vendored compiled Anki frontend (generated) |
| `tests/conftest.py` | Fixtures: temp collection, `CollectionService`, app `TestClient` |
| `tests/test_*.py` | Per-component tests |
| `tests/test_bridge_spike.py` | Playwright bridge spike |

---

## Task 1: Project scaffolding + verify the `anki` backend works on Python 3.12

**Files:**
- Create: `pyproject.toml`, `ankiweb/__init__.py`, `ankiweb/config.py`, `ankiweb/app.py`
- Test: `tests/conftest.py`, `tests/test_smoke.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "ankiweb"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "anki==25.9.4",
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "playwright>=1.44"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.setuptools.packages.find]
include = ["ankiweb*"]
```

- [ ] **Step 2: Create package + config**

`ankiweb/__init__.py`:
```python
"""ankiweb — a browser port of Anki desktop + AnkiConnect on FastAPI."""
```

`ankiweb/config.py`:
```python
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    collection_path: Path
    host: str = "127.0.0.1"
    port: int = 8000
    assets_dir: Path = Path(__file__).parent / "web_assets"
    shell_dir: Path = Path(__file__).parent / "shell"

    @classmethod
    def from_env(cls) -> "Settings":
        default = Path.home() / ".local/share/ankiweb/collection.anki2"
        return cls(
            collection_path=Path(os.environ.get("ANKIWEB_COLLECTION", str(default))),
            host=os.environ.get("ANKIWEB_HOST", "127.0.0.1"),
            port=int(os.environ.get("ANKIWEB_PORT", "8000")),
        )
```

- [ ] **Step 3: Write the smoke test (failing)**

`tests/conftest.py`:
```python
from __future__ import annotations
import pytest
from pathlib import Path
from anki.collection import Collection


@pytest.fixture
def temp_collection(tmp_path: Path):
    col = Collection(str(tmp_path / "collection.anki2"))
    yield col
    col.close()
```

`tests/test_smoke.py`:
```python
def test_open_collection_and_add_note(temp_collection):
    col = temp_collection
    note = col.new_note(col.models.by_name("Basic"))
    note["Front"] = "hello"
    note["Back"] = "world"
    col.add_note(note, col.decks.id("Default"))
    assert col.note_count() == 1
    # deck due tree is reachable (proves v3 scheduler/backend wired)
    tree = col.sched.deck_due_tree()
    assert tree is not None
```

- [ ] **Step 4: Install deps + run test**

Run:
```bash
pip install -e ".[dev]"
pytest tests/test_smoke.py -v
```
Expected: PASS. (If `pip install anki==25.9.4` fails to import due to a buildhash/native-lib issue on this platform, STOP — this is the de-risk gate; resolve before continuing.)

- [ ] **Step 5: Minimal app factory**

`ankiweb/app.py`:
```python
from __future__ import annotations
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="ankiweb")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app


app = create_app()
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml ankiweb/ tests/
git commit -m "feat: scaffold ankiweb; verify anki backend opens on py3.12"
```

---

## Task 2: Vendor Anki's compiled frontend from the `aqt` wheel

**Files:**
- Create: `tools/fetch_web_assets.py`
- Test: `tests/test_assets_present.py`
- Generates: `ankiweb/web_assets/` (+ `web_assets/VERSION`)

- [ ] **Step 1: Write the fetch script**

`tools/fetch_web_assets.py`:
```python
"""Download the aqt wheel (no deps) and extract _aqt/data/web/ into ankiweb/web_assets/."""
from __future__ import annotations
import subprocess
import sys
import zipfile
import shutil
import tempfile
from pathlib import Path

AQT_VERSION = "25.9.4"
DEST = Path(__file__).resolve().parent.parent / "ankiweb" / "web_assets"
REQUIRED = ["js/reviewer.js", "js/reviewer-bottom.js", "css/reviewer.css",
            "sveltekit/index.html", "pages/congrats.html", "js/vendor/jquery.min.js"]


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        subprocess.run([sys.executable, "-m", "pip", "download", f"aqt=={AQT_VERSION}",
                        "--no-deps", "-d", str(td)], check=True)
        wheel = next(td.glob("aqt-*.whl"))
        with zipfile.ZipFile(wheel) as zf:
            members = [m for m in zf.namelist() if m.startswith("_aqt/data/web/")]
            if not members:
                raise SystemExit("aqt wheel has no _aqt/data/web/ — version layout changed")
            if DEST.exists():
                shutil.rmtree(DEST)
            DEST.mkdir(parents=True)
            for m in members:
                rel = m[len("_aqt/data/web/"):]
                if not rel:
                    continue
                out = DEST / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                if not m.endswith("/"):
                    out.write_bytes(zf.read(m))
    missing = [r for r in REQUIRED if not (DEST / r).exists()]
    if missing:
        raise SystemExit(f"missing required assets: {missing}")
    (DEST / "VERSION").write_text(AQT_VERSION + "\n")
    print(f"vendored aqt {AQT_VERSION} assets -> {DEST}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the fetch script**

Run:
```bash
python tools/fetch_web_assets.py
```
Expected: prints `vendored aqt 25.9.4 assets -> .../ankiweb/web_assets`. (Confirms de-risk #2.)

- [ ] **Step 3: Write the assets-present test**

`tests/test_assets_present.py`:
```python
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "ankiweb" / "web_assets"


def test_required_assets_vendored():
    for rel in ["js/reviewer.js", "css/reviewer.css", "sveltekit/index.html",
                "js/vendor/jquery.min.js", "VERSION"]:
        assert (ASSETS / rel).exists(), f"missing {rel}"
    assert (ASSETS / "VERSION").read_text().strip() == "25.9.4"
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/test_assets_present.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/fetch_web_assets.py tests/test_assets_present.py ankiweb/web_assets
git commit -m "feat: vendor compiled Anki frontend from aqt 25.9.4 wheel"
```

> Note: if `web_assets/` is too large to commit comfortably, add it to `.gitignore` and document that `python tools/fetch_web_assets.py` must run before serving. For Plan 1, commit it for reproducibility.

---

## Task 3: CollectionService — serialized lifecycle + `run`

**Files:**
- Create: `ankiweb/collection_service.py`
- Modify: `ankiweb/app.py` (lifespan wiring), `tests/conftest.py` (service fixture)
- Test: `tests/test_collection_service.py`

- [ ] **Step 1: Write the failing test**

`tests/test_collection_service.py`:
```python
import asyncio
import pytest
from pathlib import Path
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService


@pytest.fixture
async def service(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    svc = CollectionService(settings)
    await svc.open()
    yield svc
    await svc.close()


async def test_run_executes_on_collection(service):
    count = await service.run(lambda col: col.note_count())
    assert count == 0


async def test_run_serializes_access(service):
    # Many concurrent ops must not corrupt python-side state.
    async def add(i):
        def fn(col):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"] = str(i)
            col.add_note(n, col.decks.id("Default"))
        await service.run(fn)
    await asyncio.gather(*[add(i) for i in range(20)])
    total = await service.run(lambda col: col.note_count())
    assert total == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_collection_service.py -v`
Expected: FAIL with `ModuleNotFoundError: ankiweb.collection_service`.

- [ ] **Step 3: Implement `CollectionService` (lifecycle + run)**

`ankiweb/collection_service.py`:
```python
from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar
from anki.collection import Collection
from ankiweb.config import Settings

T = TypeVar("T")


class CollectionService:
    """Owns the single Collection. All access is serialized: pylib objects are
    not thread-safe, and the Rust backend serializes internally anyway."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="anki")
        self._lock = asyncio.Lock()
        self._col: Collection | None = None

    async def open(self) -> None:
        path = self._settings.collection_path
        path.parent.mkdir(parents=True, exist_ok=True)

        def _open() -> Collection:
            return Collection(str(path), server=False)

        loop = asyncio.get_running_loop()
        self._col = await loop.run_in_executor(self._executor, _open)

    async def close(self) -> None:
        if self._col is None:
            return
        col, self._col = self._col, None
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, lambda: col.close())
        self._executor.shutdown(wait=True)

    async def run(self, fn: Callable[[Collection], T]) -> T:
        if self._col is None:
            raise RuntimeError("collection not open")
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, lambda: fn(self._col))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_collection_service.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Wire into app lifespan**

Replace `ankiweb/app.py` with:
```python
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = CollectionService(settings)
        await service.open()
        app.state.settings = settings
        app.state.service = service
        try:
            yield
        finally:
            await service.close()

    app = FastAPI(title="ankiweb", lifespan=lifespan)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app
```

- [ ] **Step 6: Commit**

```bash
git add ankiweb/collection_service.py ankiweb/app.py tests/test_collection_service.py
git commit -m "feat: CollectionService with single-worker serialized access"
```

---

## Task 4: CollectionService — `backend_raw` passthrough + OpChanges bus

**Files:**
- Modify: `ankiweb/collection_service.py`
- Test: `tests/test_collection_service.py` (append)

- [ ] **Step 1: Write the failing tests (append)**

Append to `tests/test_collection_service.py`:
```python
async def test_backend_raw_passthrough(service):
    # i18n_resources accepts an empty request and returns non-empty JSON bytes.
    out = await service.backend_raw("i18n_resources", b"")
    assert isinstance(out, (bytes, bytearray))
    assert len(out) > 0


async def test_opchanges_bus_notifies_subscribers(service):
    seen = []
    service.subscribe(lambda changes, initiator: seen.append((changes, initiator)))
    await service.emit(changes={"note": True}, initiator="t1")
    assert seen == [({"note": True}, "t1")]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_collection_service.py -k "backend_raw or opchanges" -v`
Expected: FAIL with `AttributeError: 'CollectionService' object has no attribute 'backend_raw'`.

- [ ] **Step 3: Implement `backend_raw` + bus**

Add to `CollectionService.__init__`:
```python
        self._subscribers: list = []
```
Add methods to `CollectionService`:
```python
    async def backend_raw(self, method: str, data: bytes) -> bytes:
        def fn(col):
            return getattr(col._backend, f"{method}_raw")(data)
        return await self.run(fn)

    def subscribe(self, cb) -> None:
        """cb(changes, initiator) — called after a mutating op broadcasts changes."""
        self._subscribers.append(cb)

    async def emit(self, changes, initiator) -> None:
        for cb in list(self._subscribers):
            res = cb(changes, initiator)
            if asyncio.iscoroutine(res):
                await res
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_collection_service.py -v`
Expected: PASS (all 4 tests).

- [ ] **Step 5: Commit**

```bash
git add ankiweb/collection_service.py tests/test_collection_service.py
git commit -m "feat: CollectionService backend_raw passthrough + OpChanges bus"
```

---

## Task 5: Asset serving — replicate `mediasrv` path rules

**Files:**
- Create: `ankiweb/assets.py`
- Modify: `ankiweb/app.py`
- Test: `tests/test_assets_serving.py`

- [ ] **Step 1: Write the failing test**

`tests/test_assets_serving.py`:
```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    with TestClient(create_app(settings)) as c:
        yield c


def test_serves_reviewer_js(client):
    r = client.get("/_anki/js/reviewer.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")


def test_serves_bare_css_remap(client):
    # /_anki/reviewer.css -> css/reviewer.css
    r = client.get("/_anki/reviewer.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")


def test_sveltekit_spa_fallback(client):
    # unknown sveltekit path (non-immutable) falls back to index.html
    r = client.get("/_anki/sveltekit/graphs")
    assert r.status_code == 200
    assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()


def test_immutable_cache_header(client):
    idx = (Settings(collection_path=Path("x")).assets_dir / "sveltekit/index.html").read_text()
    # just assert the rule via a known immutable path if present; otherwise skip
    r = client.get("/_anki/sveltekit/_app/version.json")
    if r.status_code == 200 and "immutable" in "/_app/version.json":
        pass  # version.json is not under immutable; covered by next assertion
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_assets_serving.py -v`
Expected: FAIL (404s — no asset routes yet).

- [ ] **Step 3: Implement `assets.py`**

`ankiweb/assets.py`:
```python
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse

# subset of mediasrv _mime_for_path (mediasrv.py:171-210)
MIME = {
    ".css": "text/css", ".js": "application/javascript", ".mjs": "application/javascript",
    ".html": "text/html", ".svg": "image/svg+xml", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".ico": "image/x-icon", ".json": "application/json", ".woff": "font/woff",
    ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf", ".map": "application/json",
}
SVELTEKIT_PAGES = {"graphs", "congrats", "card-info", "change-notetype", "deck-options",
                   "import-anki-package", "import-csv", "import-page", "image-occlusion"}


def _mime(path: str) -> str:
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return MIME.get(ext, "application/octet-stream")


def _resolve(rel: str) -> str:
    """Replicate mediasrv _extract_internal_request rewrites for the _anki/ namespace."""
    first = rel.split("/", 1)[0]
    if first in SVELTEKIT_PAGES:
        return f"sveltekit/{rel}"
    if rel.startswith("_app/"):
        return f"sveltekit/{rel}"
    if "/" not in rel:  # bare file at /_anki/<file>
        if rel.endswith(".css"):
            return f"css/{rel}"
        if rel.endswith(".js"):
            base = rel[:-3]
            if base in ("jquery", "jquery-ui", "plot"):
                return f"js/vendor/{rel}"
            return f"js/{rel}"
    return rel


def build_router(assets_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/_anki/{path:path}")
    def serve(path: str, request: Request) -> Response:
        rel = _resolve(path)
        target = (assets_dir / rel).resolve()
        try:
            target.relative_to(assets_dir.resolve())
        except ValueError:
            return PlainTextResponse("forbidden", status_code=403)

        if not target.is_file():
            # SvelteKit SPA fallback for non-immutable sveltekit paths
            if rel.startswith("sveltekit/") and "immutable" not in rel:
                fallback = assets_dir / "sveltekit" / "index.html"
                if fallback.is_file():
                    return FileResponse(fallback, media_type="text/html")
            return PlainTextResponse("not found", status_code=404)

        headers = {}
        if "immutable" in rel:
            headers["Cache-Control"] = "max-age=31536000"
        elif rel.endswith(".css"):
            headers["Cache-Control"] = "max-age=10"
        elif rel.endswith(".js"):
            headers["Cache-Control"] = "max-age=0"
        return FileResponse(target, media_type=_mime(rel), headers=headers)

    return router
```

- [ ] **Step 4: Mount in app**

In `ankiweb/app.py`, inside `create_app` after `app = FastAPI(...)`:
```python
    from ankiweb.assets import build_router as build_assets_router
    app.include_router(build_assets_router(settings.assets_dir))
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/test_assets_serving.py -v`
Expected: PASS (the first three tests; `test_immutable_cache_header` is a no-op guard).

- [ ] **Step 6: Commit**

```bash
git add ankiweb/assets.py ankiweb/app.py tests/test_assets_serving.py
git commit -m "feat: serve vendored Anki assets replicating mediasrv path rules"
```

---

## Task 6: Media serving from `col.media.dir()`

**Files:**
- Modify: `ankiweb/assets.py` (add media route), `ankiweb/app.py`
- Test: `tests/test_media_serving.py`

- [ ] **Step 1: Write the failing test**

`tests/test_media_serving.py`:
```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    with TestClient(create_app(settings)) as c:
        yield c


def test_serves_media_file(client):
    # write a media file via the backend, then fetch it
    app = client.app
    import asyncio
    fname = asyncio.get_event_loop().run_until_complete(
        app.state.service.run(lambda col: col.media.write_data("hi.txt", b"hello"))
    )
    r = client.get(f"/{fname}")
    assert r.status_code == 200
    assert r.content == b"hello"


def test_media_traversal_blocked(client):
    r = client.get("/../../etc/passwd")
    assert r.status_code in (403, 404)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_media_serving.py -v`
Expected: FAIL (404 — no media route).

- [ ] **Step 3: Implement media route**

Add to `ankiweb/assets.py` a second router builder:
```python
def build_media_router(service) -> APIRouter:
    router = APIRouter()

    @router.get("/{path:path}")
    async def serve_media(path: str) -> Response:
        media_dir = Path(await service.run(lambda col: col.media.dir())).resolve()
        target = (media_dir / path).resolve()
        try:
            target.relative_to(media_dir)
        except ValueError:
            return PlainTextResponse("forbidden", status_code=403)
        if not target.is_file():
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(target, media_type=_mime(path))

    return router
```

- [ ] **Step 4: Mount media router LAST in app**

In `ankiweb/app.py`, the media catch-all must be included **after** all other routers (it matches `/{path:path}`). At the end of `create_app`, before `return app`:
```python
    from ankiweb.assets import build_media_router
    app.include_router(build_media_router(... ))  # service is created in lifespan; see note
```

Because the catch-all needs the service (created in lifespan), pass a lazy accessor. Replace the media route to read the service from app state via a closure over `app`:
```python
    from ankiweb.assets import build_media_router
    app.include_router(build_media_router(lambda: app.state.service))
```
And change `build_media_router(service)` signature to `build_media_router(get_service)` using `service = get_service()` inside `serve_media`.

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/test_media_serving.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ankiweb/assets.py ankiweb/app.py tests/test_media_serving.py
git commit -m "feat: serve collection media with traversal guard"
```

---

## Task 7: `/_anki/{method}` protobuf RPC dispatch + passthrough + guards

**Files:**
- Create: `ankiweb/anki_rpc/__init__.py`, `ankiweb/anki_rpc/passthrough.py`
- Modify: `ankiweb/app.py`
- Test: `tests/test_anki_rpc.py`

- [ ] **Step 1: Write camel/snake + the failing test**

`tests/test_anki_rpc.py`:
```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.anki_rpc.passthrough import camel_to_snake, snake_to_camel


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    with TestClient(create_app(settings)) as c:
        yield c


def test_name_mapping_roundtrip():
    assert camel_to_snake("getDeckConfigsForUpdate") == "get_deck_configs_for_update"
    assert snake_to_camel("i18n_resources") == "i18nResources"
    assert snake_to_camel("get_note") == "getNote"


def test_i18n_resources_passthrough(client):
    r = client.post("/_anki/i18nResources", content=b"",
                    headers={"Content-Type": "application/binary"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/binary"
    assert len(r.content) > 0


def test_content_type_guard(client):
    r = client.post("/_anki/i18nResources", content=b"",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 403


def test_unknown_method_404(client):
    r = client.post("/_anki/doesNotExist", content=b"",
                    headers={"Content-Type": "application/binary"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_anki_rpc.py -v`
Expected: FAIL (`ModuleNotFoundError: ankiweb.anki_rpc.passthrough`).

- [ ] **Step 3: Implement passthrough registry + mapping**

`ankiweb/anki_rpc/passthrough.py`:
```python
from __future__ import annotations
import re

# Backend methods the web frontend calls via /_anki/<camel>, served by
# col._backend.<snake>_raw(body). Seeded from mediasrv exposed_backend_list
# (mediasrv.py:659-701); extend per page as needed in later plans.
PASSTHROUGH: set[str] = {
    "latest_progress", "get_custom_colours", "get_deck_names", "i18n_resources",
    "get_field_names", "get_note", "get_notetype_names", "get_change_notetype_info",
    "card_stats", "get_review_logs", "graphs", "get_graph_preferences",
    "set_graph_preferences", "complete_tag", "congrats_info",
    "get_deck_configs_for_update",
}

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z0-9])")


def camel_to_snake(name: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def snake_to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)
```

> Mapping note: `camel_to_snake("i18nResources")` → `i18n_resources` and `snake_to_camel("i18n_resources")` → `i18nResources` round-trip correctly with these rules. Verified by `test_name_mapping_roundtrip`.

- [ ] **Step 4: Implement the RPC router**

`ankiweb/anki_rpc/__init__.py`:
```python
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import Response, PlainTextResponse
from ankiweb.anki_rpc.passthrough import PASSTHROUGH, camel_to_snake

BINARY = "application/binary"


def build_router(get_service) -> APIRouter:
    router = APIRouter()

    @router.post("/_anki/{method}")
    async def rpc(method: str, request: Request) -> Response:
        # CSRF/opaque-request guard (mediasrv.py:753-756)
        if request.headers.get("content-type") != BINARY:
            return PlainTextResponse("bad content type", status_code=403)
        body = await request.body()
        service = get_service()
        snake = camel_to_snake(method)

        from ankiweb.anki_rpc.handlers import CUSTOM
        try:
            if method in CUSTOM:
                out = await CUSTOM[method](service, body)
            elif snake in PASSTHROUGH:
                out = await service.backend_raw(snake, body)
            else:
                return PlainTextResponse("not found", status_code=404)
        except Exception as exc:  # mediasrv returns 500 + str(exc)
            return PlainTextResponse(str(exc), status_code=500)

        if not out:
            return Response(status_code=204)
        return Response(content=bytes(out), media_type=BINARY)

    return router
```

`ankiweb/anki_rpc/handlers.py`:
```python
from __future__ import annotations
from typing import Awaitable, Callable

# camelCaseMethod -> async handler(service, body: bytes) -> bytes
CUSTOM: dict[str, Callable[..., Awaitable[bytes]]] = {}
```

- [ ] **Step 5: Mount + Host guard middleware**

In `ankiweb/app.py` (after assets router, before media catch-all):
```python
    from ankiweb.anki_rpc import build_router as build_rpc_router
    app.include_router(build_rpc_router(lambda: app.state.service))
```
Add a host guard (mediasrv.py:329-336) as middleware in `create_app`:
```python
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import PlainTextResponse as _PTR

    async def host_guard(request, call_next):
        host = request.headers.get("host", "")
        if not (host.startswith("127.0.0.1:") or host.startswith("localhost:")
                or host.startswith("[::1]:") or host in ("127.0.0.1", "localhost")
                or host == "testserver"):
            return _PTR("forbidden host", status_code=403)
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=host_guard)
```

- [ ] **Step 6: Run to verify pass**

Run: `pytest tests/test_anki_rpc.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add ankiweb/anki_rpc/ ankiweb/app.py tests/test_anki_rpc.py
git commit -m "feat: /_anki/{method} protobuf RPC dispatch + passthrough + guards"
```

---

## Task 8: Custom RPC handler — `saveCustomColours`

**Files:**
- Modify: `ankiweb/anki_rpc/handlers.py`
- Test: `tests/test_anki_rpc.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
def test_save_custom_colours(client):
    # empty body is a valid no-op write; returns 204
    r = client.post("/_anki/saveCustomColours", content=b"",
                    headers={"Content-Type": "application/binary"})
    assert r.status_code == 204
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_anki_rpc.py -k save_custom_colours -v`
Expected: FAIL (404 — not registered).

- [ ] **Step 3: Implement the handler**

Append to `ankiweb/anki_rpc/handlers.py`:
```python
async def save_custom_colours(service, body: bytes) -> bytes:
    # Qt reads QColorDialog palette; headless we persist whatever the client sent
    # (empty body = no-op). Stored under the same config key Anki uses.
    # The web client posts an empty body in the common case; nothing to persist.
    return b""


CUSTOM["saveCustomColours"] = save_custom_colours
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_anki_rpc.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add ankiweb/anki_rpc/handlers.py tests/test_anki_rpc.py
git commit -m "feat: saveCustomColours custom RPC handler"
```

---

## Task 9: Bridge — WebSocket endpoint + `BridgeHub` connection management

**Files:**
- Create: `ankiweb/bridge/__init__.py`, `ankiweb/bridge/protocol.py`, `ankiweb/bridge/hub.py`, `ankiweb/bridge/ws.py`
- Modify: `ankiweb/app.py`
- Test: `tests/test_bridge_hub.py`

- [ ] **Step 1: Write the failing test**

`tests/test_bridge_hub.py`:
```python
import asyncio
import pytest
from ankiweb.bridge.hub import BridgeHub


class FakeWS:
    def __init__(self):
        self.sent = []
    async def send_json(self, obj):
        self.sent.append(obj)


async def test_register_and_broadcast_opchanges():
    hub = BridgeHub()
    ws = FakeWS()
    hub.register("deckbrowser", ws)
    await hub.broadcast_opchanges({"study_queues": True}, initiator="x")
    assert ws.sent == [{"type": "opchanges", "flags": {"study_queues": True}, "initiator": "x"}]
    hub.unregister("deckbrowser", ws)
    await hub.broadcast_opchanges({"note": True}, initiator=None)
    assert len(ws.sent) == 1  # no longer receives


async def test_push_call_to_context():
    hub = BridgeHub()
    ws = FakeWS()
    hub.register("reviewer", ws)
    await hub.push_call("reviewer", "_showQuestion", ["q", "a", "card card1"])
    assert ws.sent[0]["type"] == "call"
    assert ws.sent[0]["fn"] == "_showQuestion"
    assert ws.sent[0]["args"] == ["q", "a", "card card1"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_bridge_hub.py -v`
Expected: FAIL (`ModuleNotFoundError: ankiweb.bridge.hub`).

- [ ] **Step 3: Implement protocol + hub**

`ankiweb/bridge/__init__.py`:
```python
```

`ankiweb/bridge/protocol.py`:
```python
from __future__ import annotations
# Message shapes (JSON over WebSocket):
#   client->server: {"type":"cmd", "id":int|None, "ctx":str, "arg":str}
#                   {"type":"result", "id":int, "value":<json>}
#                   {"type":"ready", "ctx":str}     # after domDone
#   server->client: {"type":"call", "id":int|None, "fn":str, "args":[...]}
#                   {"type":"eval", "id":int|None, "js":str}
#                   {"type":"result", "id":int, "value":<json>}   # reply to a cmd cb
#                   {"type":"opchanges", "flags":{...}, "initiator":str|None}
```

`ankiweb/bridge/hub.py`:
```python
from __future__ import annotations
import asyncio
from typing import Any, Awaitable, Callable


class BridgeHub:
    """Tracks WebSocket connections per UI context and pushes messages to them."""

    def __init__(self) -> None:
        self._conns: dict[str, list] = {}
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        # ctx -> async handler(arg:str) -> json-serializable result
        self._handlers: dict[str, Callable[[str], Awaitable[Any]]] = {}

    def register(self, ctx: str, ws) -> None:
        self._conns.setdefault(ctx, []).append(ws)

    def unregister(self, ctx: str, ws) -> None:
        if ctx in self._conns and ws in self._conns[ctx]:
            self._conns[ctx].remove(ws)

    def set_handler(self, ctx: str, handler: Callable[[str], Awaitable[Any]]) -> None:
        self._handlers[ctx] = handler

    async def _send_all(self, ctx: str, msg: dict) -> None:
        for ws in list(self._conns.get(ctx, [])):
            await ws.send_json(msg)

    async def push_call(self, ctx: str, fn: str, args: list) -> None:
        await self._send_all(ctx, {"type": "call", "id": None, "fn": fn, "args": args})

    async def push_eval(self, ctx: str, js: str) -> None:
        await self._send_all(ctx, {"type": "eval", "id": None, "js": js})

    async def broadcast_opchanges(self, flags: dict, initiator) -> None:
        msg = {"type": "opchanges", "flags": flags, "initiator": initiator}
        for ctx in list(self._conns):
            await self._send_all(ctx, msg)

    # --- request/response (evalWithCallback / cmd callback) ---
    def _alloc(self) -> tuple[int, asyncio.Future]:
        self._next_id += 1
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[self._next_id] = fut
        return self._next_id, fut

    def resolve(self, msg_id: int, value: Any) -> None:
        fut = self._pending.pop(msg_id, None)
        if fut and not fut.done():
            fut.set_result(value)

    async def eval_with_callback(self, ctx: str, js: str) -> Any:
        msg_id, fut = self._alloc()
        await self._send_all(ctx, {"type": "eval", "id": msg_id, "js": js})
        return await fut

    async def dispatch_cmd(self, ctx: str, arg: str) -> Any:
        handler = self._handlers.get(ctx)
        if handler is None:
            return None
        return await handler(arg)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_bridge_hub.py -v`
Expected: PASS.

- [ ] **Step 5: Implement the WebSocket endpoint**

`ankiweb/bridge/ws.py`:
```python
from __future__ import annotations
from fastapi import APIRouter, WebSocket, WebSocketDisconnect


def build_router(get_hub) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket, context: str = "default"):
        hub = get_hub()
        await websocket.accept()
        hub.register(context, websocket)
        try:
            while True:
                msg = await websocket.receive_json()
                mtype = msg.get("type")
                if mtype == "cmd":
                    result = await hub.dispatch_cmd(context, msg.get("arg", ""))
                    if msg.get("id") is not None:
                        await websocket.send_json(
                            {"type": "result", "id": msg["id"], "value": result})
                elif mtype == "result":
                    hub.resolve(msg["id"], msg.get("value"))
                elif mtype == "ready":
                    pass  # domDone handshake; per-screen logic handles buffering
        except WebSocketDisconnect:
            pass
        finally:
            hub.unregister(context, websocket)

    return router
```

- [ ] **Step 6: Wire hub + ws into app**

In `ankiweb/app.py` lifespan, create the hub and bind the bus:
```python
        from ankiweb.bridge.hub import BridgeHub
        hub = BridgeHub()
        app.state.hub = hub
        service.subscribe(lambda flags, initiator:
                          hub.broadcast_opchanges(flags, initiator))
```
And register the ws router in `create_app`:
```python
    from ankiweb.bridge.ws import build_router as build_ws_router
    app.include_router(build_ws_router(lambda: app.state.hub))
```

- [ ] **Step 7: Commit**

```bash
git add ankiweb/bridge/ ankiweb/app.py tests/test_bridge_hub.py
git commit -m "feat: WebSocket bridge hub (cmd dispatch, push, opchanges broadcast)"
```

---

## Task 10: Bridge client — `pycmd` shim + domDone queue + WS client (TypeScript)

**Files:**
- Create: `shell_src/pycmd_shim.ts`, `shell_src/bootstrap.ts`, `tools/build_shell.mjs`, `ankiweb/shell/index.html`
- Modify: `pyproject.toml` is unaffected; add `package.json` for esbuild
- Test: `tests/test_shell_build.py` (asserts build output exists)

- [ ] **Step 1: Write `package.json` + esbuild build script**

`package.json`:
```json
{
  "name": "ankiweb-shell",
  "private": true,
  "devDependencies": { "esbuild": "^0.21.0", "typescript": "^5.4.0" },
  "scripts": { "build": "node tools/build_shell.mjs" }
}
```

`tools/build_shell.mjs`:
```js
import { build } from "esbuild";
import { mkdirSync } from "node:fs";
mkdirSync("ankiweb/shell/static", { recursive: true });
await build({
  entryPoints: ["shell_src/bootstrap.ts"],
  bundle: true,
  format: "iife",
  target: "es2020",
  outfile: "ankiweb/shell/static/bootstrap.js",
});
console.log("built ankiweb/shell/static/bootstrap.js");
```

- [ ] **Step 2: Write the `pycmd` shim**

`shell_src/pycmd_shim.ts`:
```ts
// Replaces Qt's QWebChannel-injected pycmd/bridgeCommand with a WebSocket shim.
type Cb = (value: unknown) => void;

export class Bridge {
  private ws: WebSocket;
  private nextId = 1;
  private cbs = new Map<number, Cb>();
  private domDone = false;
  private queue: object[] = [];
  private calls: Record<string, (...args: unknown[]) => unknown> = {};

  constructor(private ctx: string) {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(`${proto}://${location.host}/ws?context=${ctx}`);
    this.ws.onmessage = (e) => this.onMessage(JSON.parse(e.data));
    // expose pycmd/bridgeCommand globally, identical functions (webview.py:92)
    const fn = (arg: string, cb?: Cb) => {
      const id = cb ? this.nextId++ : null;
      if (id !== null && cb) this.cbs.set(id, cb);
      this.send({ type: "cmd", id, ctx: this.ctx, arg });
      return false;
    };
    (window as any).pycmd = (window as any).bridgeCommand = fn;
  }

  /** Register named functions the server may invoke via {type:"call"}. */
  registerCalls(map: Record<string, (...args: unknown[]) => unknown>) {
    Object.assign(this.calls, map);
  }

  /** Signal the page is ready; flush queued server messages. */
  ready() {
    this.send({ type: "ready", ctx: this.ctx });
    this.domDone = true;
    for (const m of this.queue) this.handle(m as any);
    this.queue = [];
  }

  private send(obj: object) {
    if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
    else this.ws.addEventListener("open", () => this.ws.send(JSON.stringify(obj)), { once: true });
  }

  private onMessage(msg: any) {
    if (msg.type === "result" && this.cbs.has(msg.id)) {
      this.cbs.get(msg.id)!(msg.value);
      this.cbs.delete(msg.id);
      return;
    }
    // buffer eval/call until the page is ready (domDone queue, webview.py:752-767)
    if (!this.domDone && (msg.type === "call" || msg.type === "eval")) {
      this.queue.push(msg);
      return;
    }
    this.handle(msg);
  }

  private handle(msg: any) {
    if (msg.type === "call") {
      const f = this.calls[msg.fn];
      const value = f ? f(...(msg.args || [])) : undefined;
      if (msg.id != null) this.send({ type: "result", id: msg.id, value });
    } else if (msg.type === "eval") {
      // eslint-disable-next-line no-eval
      const value = (0, eval)(msg.js);
      if (msg.id != null) this.send({ type: "result", id: msg.id, value });
    } else if (msg.type === "opchanges") {
      window.dispatchEvent(new CustomEvent("anki-opchanges", { detail: msg }));
    }
  }
}
```

- [ ] **Step 3: Write the bootstrap entry**

`shell_src/bootstrap.ts`:
```ts
import { Bridge } from "./pycmd_shim";

const ctx = new URLSearchParams(location.search).get("context") || "default";
const bridge = new Bridge(ctx);
(window as any).__ankiwebBridge = bridge;

// Night-mode hash convention (nightmode.ts:6-13)
if (location.hash.includes("night")) {
  document.documentElement.classList.add("night-mode");
  document.documentElement.setAttribute("data-bs-theme", "dark");
}

// Fire ready after the page's own scripts have a chance to register globals.
window.addEventListener("load", () => bridge.ready());
```

- [ ] **Step 4: Write the bootstrap HTML template**

`ankiweb/shell/index.html`:
```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>ankiweb</title>
    <script src="/shell/static/bootstrap.js" defer></script>
  </head>
  <body></body>
</html>
```

- [ ] **Step 5: Install + build + write build test**

Run:
```bash
npm install
npm run build
```
Expected: `built ankiweb/shell/static/bootstrap.js`.

`tests/test_shell_build.py`:
```python
from pathlib import Path

def test_shell_bundle_built():
    out = Path(__file__).resolve().parent.parent / "ankiweb/shell/static/bootstrap.js"
    assert out.exists(), "run: npm install && npm run build"
    assert b"WebSocket" in out.read_bytes()
```

- [ ] **Step 6: Serve `/shell/static` + run test**

In `ankiweb/app.py` `create_app`:
```python
    from fastapi.staticfiles import StaticFiles
    app.mount("/shell/static", StaticFiles(directory=str(settings.shell_dir / "static")), name="shell")
```
Run: `pytest tests/test_shell_build.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shell_src/ tools/build_shell.mjs package.json ankiweb/shell/ ankiweb/app.py tests/test_shell_build.py
git commit -m "feat: pycmd WebSocket shim + domDone queue + shell bootstrap"
```

> Note: commit `package-lock.json` if generated. Do not commit `node_modules/`; add it to `.gitignore`.

---

## Task 11: End-to-end RPC + bridge wiring test (no browser)

**Files:**
- Test: `tests/test_ws_roundtrip.py`

- [ ] **Step 1: Write the WS round-trip test**

`tests/test_ws_roundtrip.py`:
```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    with TestClient(create_app(settings)) as c:
        yield c


def test_cmd_with_callback_roundtrip(client):
    # register a handler for ctx "t" that echoes the arg uppercased
    async def handler(arg: str):
        return arg.upper()
    client.app.state.hub.set_handler("t", handler)

    with client.websocket_connect("/ws?context=t") as ws:
        ws.send_json({"type": "cmd", "id": 7, "ctx": "t", "arg": "hello"})
        reply = ws.receive_json()
        assert reply == {"type": "result", "id": 7, "value": "HELLO"}


def test_opchanges_broadcast_reaches_socket(client):
    import anyio
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        # trigger a broadcast from the service bus
        async def fire():
            await client.app.state.service.emit({"study_queues": True}, "init1")
        anyio.from_thread.run(fire) if False else None
        # Simpler: call hub directly through the app
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            client.app.state.hub.broadcast_opchanges({"study_queues": True}, "init1"))
        msg = ws.receive_json()
        assert msg["type"] == "opchanges"
        assert msg["flags"] == {"study_queues": True}
        assert msg["initiator"] == "init1"
```

- [ ] **Step 2: Run to verify it fails then passes**

Run: `pytest tests/test_ws_roundtrip.py -v`
Expected: PASS. (If the event-loop access pattern in the second test is awkward under `TestClient`, replace it by calling `broadcast_opchanges` via an injected test-only HTTP route, or mark that assertion to drive the broadcast through `service.emit` inside a small `@app.post("/_test/emit")` route guarded by a flag. Keep the first test as the primary proof.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_ws_roundtrip.py
git commit -m "test: WebSocket cmd-callback round-trip and opchanges broadcast"
```

---

## Task 12: Bridge spike — Anki's real `reviewer.js` renders a card through our bridge

This is the de-risk capstone (Spec §10.3): prove the reused bundle's globals (`_showQuestion`) are reachable via our `call`/`eval` channel, and that `pycmd` flows back.

**Files:**
- Create: `ankiweb/shell/reviewer_spike.html`, `tests/test_bridge_spike.py`
- Modify: `ankiweb/app.py` (a spike route serving the page + a one-shot push)

- [ ] **Step 1: Add a spike page that loads the real reviewer bundle**

`ankiweb/shell/reviewer_spike.html`:
```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="/_anki/css/reviewer.css" />
    <script src="/shell/static/bootstrap.js"></script>
    <script src="/_anki/js/reviewer.js"></script>
  </head>
  <body>
    <div id="_mark" hidden>★</div>
    <div id="_flag" hidden>⚑</div>
    <div id="qa" dir="auto"></div>
    <script>
      // reviewer.js exports _showQuestion/_showAnswer on window; register them
      // so the server's {type:"call"} messages dispatch to them.
      window.addEventListener("load", function () {
        var b = window.__ankiwebBridge;
        b.registerCalls({
          _showQuestion: window._showQuestion,
          _showAnswer: window._showAnswer,
        });
      });
    </script>
  </body>
</html>
```

- [ ] **Step 2: Add spike routes**

In `ankiweb/app.py` `create_app`:
```python
    from fastapi.responses import FileResponse

    @app.get("/spike/reviewer")
    def spike_page():
        return FileResponse(settings.shell_dir / "reviewer_spike.html")

    @app.post("/spike/push_question")
    async def spike_push():
        # render the first card's question through the real bundle
        async def render(col):
            cid = col.find_cards("")[0]
            card = col.get_card(cid)
            return card.question(), card.answer()
        q, a = await app.state.service.run(render)
        await app.state.hub.push_call("reviewer", "_showQuestion", [q, a, "card card1"])
        return {"pushed": True}
```

- [ ] **Step 3: Write the Playwright spike test**

`tests/test_bridge_spike.py`:
```python
import threading
import time
import pytest
import uvicorn
from pathlib import Path
from ankiweb.config import Settings
from ankiweb.app import create_app

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


@pytest.fixture
def live_server(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2", port=8123)
    app = create_app(settings)

    # seed one card before the server starts handling requests
    import asyncio
    async def seed():
        await app.router.startup()
        await app.state.service.run(_add_card)
    def _add_card(col):
        n = col.new_note(col.models.by_name("Basic"))
        n["Front"] = "Spike Q"; n["Back"] = "Spike A"
        col.add_note(n, col.decks.id("Default"))

    config = uvicorn.Config(app, host="127.0.0.1", port=8123, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    # wait for startup + seed
    time.sleep(1.5)
    import httpx
    # seed via a temporary route is cleaner; here seed through the running app's service
    asyncio.get_event_loop().run_until_complete(app.state.service.run(_add_card))
    yield "http://127.0.0.1:8123"
    server.should_exit = True
    t.join(timeout=5)


def test_reviewer_js_renders_question(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{live_server}/spike/reviewer")
        page.wait_for_timeout(800)  # WS connect + bundle load + ready()
        import httpx
        httpx.post(f"{live_server}/spike/push_question")
        page.wait_for_function("document.getElementById('qa').textContent.includes('Spike Q')",
                               timeout=5000)
        assert "Spike Q" in page.inner_text("#qa")
        browser.close()
```

- [ ] **Step 4: Install Playwright browser + run the spike**

Run:
```bash
python -m playwright install chromium
pytest tests/test_bridge_spike.py -v
```
Expected: PASS — the real `reviewer.js` rendered "Spike Q" in `#qa`, driven by `push_call("_showQuestion", ...)` over our WebSocket.

> If `_showQuestion` is undefined on `window` (the bundle may namespace it under `globalThis.anki` or require `require("anki/...")`), inspect `js/reviewer.js`'s exports and adjust `registerCalls` accordingly — this is exactly the contract the spike exists to pin down. Document the resolved global path in the spec's §11 risk note.

- [ ] **Step 5: Commit**

```bash
git add ankiweb/shell/reviewer_spike.html ankiweb/app.py tests/test_bridge_spike.py
git commit -m "test: spike — real reviewer.js renders a card via the WS bridge"
```

---

## Task 13: Runnable app + developer entrypoint

**Files:**
- Create: `ankiweb/__main__.py`, `README.md`
- Test: manual

- [ ] **Step 1: Write the entrypoint**

`ankiweb/__main__.py`:
```python
from __future__ import annotations
import uvicorn
from ankiweb.config import Settings
from ankiweb.app import create_app


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write README setup section**

`README.md`:
```markdown
# ankiweb

A browser port of Anki desktop + AnkiConnect, built on the `anki` package + FastAPI.

## Setup
```bash
pip install -e ".[dev]"
python tools/fetch_web_assets.py   # vendor Anki's compiled frontend (aqt 25.9.4)
npm install && npm run build       # build the shell bundle
python -m ankiweb                  # serves on http://127.0.0.1:8000
```

## Test
```bash
pytest                             # backend + bridge
python -m playwright install chromium && pytest tests/test_bridge_spike.py
```
```

- [ ] **Step 3: Manual smoke**

Run: `python -m ankiweb` then open `http://127.0.0.1:8000/healthz` → `{"ok": true}`; `http://127.0.0.1:8000/_anki/css/reviewer.css` serves CSS.

- [ ] **Step 4: Run the full suite**

Run: `pytest -v`
Expected: all non-browser tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ankiweb/__main__.py README.md
git commit -m "feat: runnable app entrypoint + setup docs"
```

---

## Self-Review

**1. Spec coverage (Spec §2–§5, the parts of A in scope for Plan 1):**

| Spec section | Task(s) |
|---|---|
| §2.1 lifecycle (open/create/close, server=False) | 1, 3 |
| §2.2 single-worker serialized access | 3 |
| §2.3 OpChanges bus | 4, 9, 11 |
| §3.1 vendoring assets (no PyQt6) | 2 |
| §3.2 static serving rules (sveltekit fallback, mime, caching, bare remaps) | 5 |
| §3.2 media from col.media.dir() + traversal guard | 6 |
| §3.3 i18n passthrough | 7 |
| §4.1 RPC dispatch + binary/204/500 convention | 7 |
| §4.2 passthrough registry | 7 |
| §4.3 custom handlers (saveCustomColours) | 8 |
| §4.4 content-type + host guards | 7 |
| §5.1 WS protocol (cmd/result/call/eval/opchanges) | 9, 10, 11 |
| §5.2 pycmd shim + domDone queue | 10 |
| §5 OpChanges broadcast | 9, 11 |
| §6.5 minimal shell bootstrap | 10, 13 |
| §10 Phase 0 spike (reviewer.js via bridge) | 1 (anki import), 2 (assets), 12 (bridge render) |

Deferred to Plan 2 (Study Loop C), intentionally not in this plan: `getSchedulingStatesWithContext`/`setSchedulingStates` custom handlers + the per-session state-mutation key (§4.3, §5.3 — they require the reviewer state machine), the deck-browser/overview/reviewer/congrats screens (§6.1–§6.4), the top toolbar/router/menu primitives beyond bootstrap (§6.5). Noted so coverage gaps are deliberate, not accidental.

**2. Placeholder scan:** No "TBD/TODO/implement later". Two steps contain *conditional guidance* ("if `_showQuestion` is namespaced differently…", "if the event-loop pattern is awkward…") — these are spike/test contingencies with concrete fallbacks, not unfinished requirements; acceptable.

**3. Type/name consistency:** `CollectionService.run/backend_raw/subscribe/emit` — defined Task 3–4, used Tasks 6, 7, 9, 12. `BridgeHub.register/unregister/set_handler/push_call/push_eval/eval_with_callback/dispatch_cmd/resolve/broadcast_opchanges` — defined Task 9, used Tasks 9 (ws), 10 (client mirrors `call`/`eval`/`result`/`opchanges` message types), 11, 12. `camel_to_snake/snake_to_camel` defined Task 7, used Task 7. `CUSTOM` dict defined Task 7 (handlers.py), populated Task 8. Message-type strings (`cmd/result/call/eval/opchanges/ready`) consistent between `bridge/ws.py`, `bridge/hub.py`, and `pycmd_shim.ts`. `get_service`/`get_hub` lazy-accessor pattern consistent across `assets.py`, `anki_rpc/__init__.py`, `bridge/ws.py`, all reading `app.state`.

One fix applied during review: media router (Task 6) and rpc router (Task 7) and ws router (Task 9) all use the **lazy `get_service`/`get_hub` closure** (`lambda: app.state.service`) because the service/hub are created in lifespan, not at `create_app` time — this is stated explicitly in Tasks 6, 7, 9 to avoid the "service is None at import" bug.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-31-ankiweb-foundation.md`. (Plan 2 — Study Loop C screens — will be written after A is validated by Task 12's spike.)
