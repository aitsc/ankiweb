# ankiweb AnkiConnect B1 — Infrastructure + Decks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the AnkiConnect-compatible HTTP API on port 8765 (faithful JSON-RPC envelope/version/multi/apiReflect/CORS/apiKey) sharing the one open collection, plus the deck-management actions — so an existing AnkiConnect client can ping `version`, list/create/delete decks, and batch via `multi`.

**Architecture:** A second FastAPI app (`create_ankiconnect_app`) on 8765 with a single `POST /` JSON-RPC endpoint, its own CORS/auth (NOT the web UI's host-guard), dispatching `{action, version, params, key}` through a flat action registry against the shared `CollectionService`. `create_app` is refactored so both apps can share one externally-owned `CollectionService`; `python -m ankiweb` runs both uvicorn servers in one asyncio loop. Actions are thin async wrappers over the collection.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, FastAPI, the existing `CollectionService`, pytest+httpx. Run everything via `conda run -n ankiweb ...`.

**This is Plan B1 of 4 for Sub-project B.** B2 = Notes+Cards, B3 = Models+Media, B4 = gui* (+ Stats/export folded into B2/B3). Spec: `docs/superpowers/specs/2026-06-01-ankiweb-ankiconnect-api-design.md`.

**Deliberate deferrals (NOT defects):** Statistics actions, `exportPackage`/`importPackage` (need the keyword-only `col.export_anki_package(out_path, options, limit)` with proto options — fiddly), Notes/Cards/Models/Media/gui* (later B plans). `sync` returns an error (no sync). Profiles return single-profile constants. `requestPermission` auto-grants (no Qt dialog). API mutations that return `OpChanges` go through `run_op` (so an open web UI refreshes); ones that don't (e.g. `col.decks.id`) use `run`.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/ankiconnect/__init__.py` (create) | package marker |
| `ankiweb/ankiconnect/config.py` (create) | `AnkiConnectConfig` (apiKey, corsOriginList, bind port, ignoreOriginList) loaded from JSON |
| `ankiweb/ankiconnect/runtime.py` (create) | `Runtime` context (`service`, `config`, `hub`, `ui_state`) passed to every action |
| `ankiweb/ankiconnect/registry.py` (create) | `ACTIONS` dict + `@action` decorator |
| `ankiweb/ankiconnect/dispatch.py` (create) | `dispatch_one(rt, req)` — version envelope, error wrapping, `multi`, apiKey gate |
| `ankiweb/ankiconnect/cors.py` (create) | `allow_origin(origin, cors_list)` → (allowed, header) |
| `ankiweb/ankiconnect/app.py` (create) | `create_ankiconnect_app(settings, service=None, config=None, hub=None)` — POST/GET/OPTIONS `/` |
| `ankiweb/ankiconnect/actions/__init__.py` (create) | imports the action modules so they register |
| `ankiweb/ankiconnect/actions/meta.py` (create) | `version`, `apiReflect`, `requestPermission`, `reloadCollection`, profiles, `sync`(error) |
| `ankiweb/ankiconnect/actions/decks.py` (create) | the 13 deck actions |
| `ankiweb/app.py` (modify) | `create_app(settings, service=None, hub=None)` injection support |
| `ankiweb/__main__.py` (modify) | run both servers (web UI + ankiconnect) sharing one service |
| `tests/ankiconnect/test_*.py` (create) | per-component tests |

---

## Task 1: AnkiConnect config + Runtime context

**Files:**
- Create: `ankiweb/ankiconnect/__init__.py`, `ankiweb/ankiconnect/config.py`, `ankiweb/ankiconnect/runtime.py`
- Test: `tests/ankiconnect/__init__.py`, `tests/ankiconnect/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/ankiconnect/__init__.py`:
```python
```
(empty)

`tests/ankiconnect/test_config.py`:
```python
import json
from pathlib import Path
from ankiweb.ankiconnect.config import AnkiConnectConfig


def test_defaults_when_no_file(tmp_path: Path):
    cfg = AnkiConnectConfig.load(tmp_path / "missing.json")
    assert cfg.api_key is None
    assert cfg.cors_origin_list == ["http://localhost"]
    assert cfg.bind_port == 8765
    assert cfg.ignore_origin_list == []


def test_loads_overrides(tmp_path: Path):
    p = tmp_path / "ac.json"
    p.write_text(json.dumps({"apiKey": "secret", "webCorsOriginList": ["*"], "webBindPort": 9000}))
    cfg = AnkiConnectConfig.load(p)
    assert cfg.api_key == "secret"
    assert cfg.cors_origin_list == ["*"]
    assert cfg.bind_port == 9000
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`ankiweb/ankiconnect/__init__.py`:
```python
"""AnkiConnect-compatible HTTP API."""
```

`ankiweb/ankiconnect/config.py`:
```python
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AnkiConnectConfig:
    api_key: str | None = None
    cors_origin_list: list = field(default_factory=lambda: ["http://localhost"])
    bind_address: str = "127.0.0.1"
    bind_port: int = 8765
    ignore_origin_list: list = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "AnkiConnectConfig":
        data = {}
        if Path(path).exists():
            data = json.loads(Path(path).read_text() or "{}")
        return cls(
            api_key=data.get("apiKey"),
            cors_origin_list=data.get("webCorsOriginList", ["http://localhost"]),
            bind_address=data.get("webBindAddress", "127.0.0.1"),
            bind_port=int(data.get("webBindPort", 8765)),
            ignore_origin_list=data.get("ignoreOriginList", []),
        )
```

`ankiweb/ankiconnect/runtime.py`:
```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class Runtime:
    """Context passed to every AnkiConnect action handler."""
    service: Any                 # CollectionService
    config: Any                  # AnkiConnectConfig
    hub: Any = None              # BridgeHub (for gui* in B4)
    ui_state: Any = None         # reviewer/browser UI mirror (B4)
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ankiweb/ankiconnect/__init__.py ankiweb/ankiconnect/config.py ankiweb/ankiconnect/runtime.py tests/ankiconnect/
git commit -m "feat(ankiconnect): config + runtime context"
```

## Context
Config mirrors AnkiConnect's keys (`apiKey`/`webCorsOriginList`/`webBindAddress`/`webBindPort`/`ignoreOriginList`) but from a plain JSON file (no add-on manager). `Runtime` is the per-request context every action receives; `hub`/`ui_state` are None until B4 (gui*).

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 2: Action registry + dispatcher

**Files:**
- Create: `ankiweb/ankiconnect/registry.py`, `ankiweb/ankiconnect/dispatch.py`
- Test: `tests/ankiconnect/test_dispatch.py`

- [ ] **Step 1: Write the failing test**

`tests/ankiconnect/test_dispatch.py`:
```python
import pytest
from ankiweb.ankiconnect.registry import ACTIONS, action
from ankiweb.ankiconnect.dispatch import dispatch_one
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.ankiconnect.runtime import Runtime


@pytest.fixture
def rt():
    return Runtime(service=None, config=AnkiConnectConfig())


@pytest.fixture(autouse=True)
def _register():
    @action("echo")
    async def echo(rt, value=None):
        return value
    @action("boom")
    async def boom(rt):
        raise ValueError("kaboom")
    yield
    ACTIONS.pop("echo", None)
    ACTIONS.pop("boom", None)


async def test_v6_success_enveloped(rt):
    reply = await dispatch_one(rt, {"action": "echo", "version": 6, "params": {"value": 7}})
    assert reply == {"result": 7, "error": None}


async def test_v4_success_is_bare(rt):
    reply = await dispatch_one(rt, {"action": "echo", "version": 4, "params": {"value": 7}})
    assert reply == 7


async def test_default_version_is_4_bare(rt):
    reply = await dispatch_one(rt, {"action": "echo", "params": {"value": "x"}})
    assert reply == "x"


async def test_error_always_enveloped_even_v4(rt):
    reply = await dispatch_one(rt, {"action": "boom", "version": 4})
    assert reply == {"result": None, "error": "kaboom"}


async def test_unknown_action_errors(rt):
    reply = await dispatch_one(rt, {"action": "nope", "version": 6})
    assert reply["result"] is None and "nope" in reply["error"]


async def test_multi_returns_list_of_replies(rt):
    reply = await dispatch_one(rt, {"action": "multi", "version": 6, "params": {"actions": [
        {"action": "echo", "version": 6, "params": {"value": 1}},
        {"action": "boom", "version": 6},
    ]}})
    assert reply["result"][0] == {"result": 1, "error": None}
    assert reply["result"][1] == {"result": None, "error": "kaboom"}


async def test_apikey_gate(rt):
    rt.config.api_key = "s3cret"
    bad = await dispatch_one(rt, {"action": "echo", "version": 6, "key": "wrong", "params": {"value": 1}})
    assert bad["result"] is None and "key" in bad["error"].lower()
    ok = await dispatch_one(rt, {"action": "echo", "version": 6, "key": "s3cret", "params": {"value": 1}})
    assert ok == {"result": 1, "error": None}
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_dispatch.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement registry + dispatcher**

`ankiweb/ankiconnect/registry.py`:
```python
from __future__ import annotations
from typing import Awaitable, Callable

# action name -> async handler(rt, **params)
ACTIONS: dict[str, Callable[..., Awaitable]] = {}


def action(name: str):
    def deco(fn):
        ACTIONS[name] = fn
        return fn
    return deco
```

`ankiweb/ankiconnect/dispatch.py`:
```python
from __future__ import annotations
from typing import Any
from ankiweb.ankiconnect.registry import ACTIONS


def _envelope(version: int, result: Any) -> Any:
    # success: version<=4 → bare value; version>=5 → {result, error:None}
    if version <= 4:
        return result
    return {"result": result, "error": None}


async def dispatch_one(rt, req: dict) -> Any:
    """Dispatch a single AnkiConnect request object → its reply (enveloped per version)."""
    version = req.get("version", 4)
    try:
        action_name = req.get("action") or ""
        params = req.get("params") or {}
        # apiKey gate (requestPermission is always exempt)
        if rt.config.api_key is not None and action_name != "requestPermission":
            if req.get("key") != rt.config.api_key:
                raise Exception("valid api key must be provided")
        if action_name == "multi":
            result = [await dispatch_one(rt, sub) for sub in (params.get("actions") or [])]
        elif action_name in ACTIONS:
            result = await ACTIONS[action_name](rt, **params)
        else:
            raise Exception(f"unsupported action: {action_name}")
        return _envelope(version, result)
    except Exception as exc:  # errors are ALWAYS enveloped, regardless of version
        return {"result": None, "error": str(exc)}
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_dispatch.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add ankiweb/ankiconnect/registry.py ankiweb/ankiconnect/dispatch.py tests/ankiconnect/test_dispatch.py
git commit -m "feat(ankiconnect): action registry + JSON-RPC dispatcher (envelope/version/multi/apiKey)"
```

## Context
The dispatcher is pure (no HTTP) and fully unit-tested. It replicates AnkiConnect's exact envelope asymmetry (success bare for v≤4, enveloped for v≥5; errors ALWAYS enveloped), the `multi` batch (each sub-reply enveloped per its own version, per-item error capture), and the apiKey gate (requestPermission exempt). `params` splat as kwargs.

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 3: CORS helper + the FastAPI app

**Files:**
- Create: `ankiweb/ankiconnect/cors.py`, `ankiweb/ankiconnect/app.py`, `ankiweb/ankiconnect/actions/__init__.py`
- Test: `tests/ankiconnect/test_cors.py`, `tests/ankiconnect/test_app.py`

- [ ] **Step 1: Write the failing tests**

`tests/ankiconnect/test_cors.py`:
```python
from ankiweb.ankiconnect.cors import allow_origin


def test_star_allows_all():
    allowed, header = allow_origin("https://evil.example", ["*"])
    assert allowed and header == "*"


def test_exact_match():
    allowed, header = allow_origin("http://localhost", ["http://localhost"])
    assert allowed and header == "http://localhost"


def test_localhost_implies_127():
    allowed, header = allow_origin("http://127.0.0.1:5000", ["http://localhost"])
    assert allowed and header == "http://127.0.0.1:5000"


def test_localhost_with_port_and_https_allowed():
    assert allow_origin("http://localhost:8080", ["http://localhost"])[0]
    assert allow_origin("https://localhost", ["http://localhost"])[0]


def test_extension_origins_allowed_when_localhost_listed():
    allowed, _ = allow_origin("chrome-extension://abc", ["http://localhost"])
    assert allowed


def test_no_origin_allowed():
    allowed, _ = allow_origin(None, ["http://localhost"])
    assert allowed


def test_disallowed():
    allowed, _ = allow_origin("https://evil.example", ["http://localhost"])
    assert not allowed
```

`tests/ankiconnect/test_app.py`:
```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.ankiconnect.app import create_ankiconnect_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(collection_path=tmp_path / "collection.anki2")
    with TestClient(create_ankiconnect_app(settings)) as c:
        yield c


def test_version_action(client):
    r = client.post("/", json={"action": "version", "version": 6})
    assert r.status_code == 200
    assert r.json() == {"result": 6, "error": None}


def test_empty_get_is_probe(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"apiVersion": "AnkiConnect v.6"}


def test_disallowed_origin_403(client):
    r = client.post("/", json={"action": "version", "version": 6},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_localhost_origin_ok_with_acao(client):
    r = client.post("/", json={"action": "version", "version": 6},
                    headers={"Origin": "http://localhost"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost"


def test_options_preflight(client):
    r = client.options("/", headers={"Origin": "http://localhost"})
    assert r.status_code == 200
    assert "access-control-allow-origin" in r.headers
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_cors.py tests/ankiconnect/test_app.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement cors + app**

`ankiweb/ankiconnect/cors.py`:
```python
from __future__ import annotations

_EXTENSION_SCHEMES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


def allow_origin(origin: str | None, cors_list: list) -> tuple[bool, str]:
    """Replicate AnkiConnect's allowOrigin. Returns (allowed, ACAO-header-value)."""
    if "*" in cors_list:
        return True, "*"
    if origin is None:  # curl / server-to-server (no Origin) is allowed
        return True, (cors_list[0] if cors_list else "*")
    if origin in cors_list:
        return True, origin
    if "http://localhost" in cors_list:
        # AnkiConnect treats localhost and 127.0.0.1 symmetrically, any scheme/port.
        if origin.startswith(("http://localhost", "https://localhost",
                              "http://127.0.0.1", "https://127.0.0.1")):
            return True, origin
        if origin.startswith(_EXTENSION_SCHEMES):
            return True, origin
    return False, origin
```

`ankiweb/ankiconnect/actions/__init__.py`:
```python
# Importing the action modules registers their handlers in the ACTIONS registry.
from ankiweb.ankiconnect.actions import meta, decks  # noqa: F401
```

`ankiweb/ankiconnect/app.py`:
```python
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.ankiconnect.runtime import Runtime
from ankiweb.ankiconnect.cors import allow_origin
from ankiweb.ankiconnect.dispatch import dispatch_one
import ankiweb.ankiconnect.actions  # noqa: F401 — registers actions


def create_ankiconnect_app(
    settings: Settings | None = None,
    service: CollectionService | None = None,
    config: AnkiConnectConfig | None = None,
    hub=None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    config = config or AnkiConnectConfig()
    owns_service = service is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = service
        if owns_service:
            svc = CollectionService(settings)
            await svc.open()
        app.state.service = svc
        app.state.config = config
        app.state.hub = hub
        try:
            yield
        finally:
            if owns_service:
                await svc.close()

    app = FastAPI(title="ankiweb-ankiconnect", lifespan=lifespan)

    def _cors_headers(origin):
        allowed, header = allow_origin(origin, config.cors_origin_list)
        return allowed, {"Access-Control-Allow-Origin": header,
                         "Access-Control-Allow-Headers": "*"}

    @app.options("/")
    async def preflight(request: Request):
        _, headers = _cors_headers(request.headers.get("origin"))
        if request.headers.get("access-control-request-private-network") == "true":
            headers["Access-Control-Allow-Private-Network"] = "true"
        return Response(status_code=200, headers=headers)

    @app.get("/")
    async def probe():
        return JSONResponse({"apiVersion": "AnkiConnect v.6"})

    @app.post("/")
    async def rpc(request: Request):
        origin = request.headers.get("origin")
        allowed, headers = _cors_headers(origin)
        try:
            req = await request.json()
        except Exception:
            req = {}
        if not req:  # empty body → liveness probe
            return JSONResponse({"apiVersion": "AnkiConnect v.6"}, headers=headers)
        action_name = req.get("action") or ""
        if not allowed and action_name != "requestPermission":
            return JSONResponse({"result": None, "error": "origin not allowed"},
                                status_code=403, headers=headers)
        rt = Runtime(service=app.state.service, config=app.state.config, hub=app.state.hub)
        if action_name == "requestPermission":  # inject CORS result + origin
            req.setdefault("params", {})
            req["params"]["allowed"] = allowed
            req["params"]["origin"] = origin
        reply = await dispatch_one(rt, req)
        return JSONResponse(reply, headers=headers)

    return app
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_cors.py tests/ankiconnect/test_app.py -v`
Expected: PASS. (`version`, `requestPermission` come from `actions/meta.py` in Task 4 — if `test_version_action` fails with "unsupported action: version" because meta isn't implemented yet, that is expected ordering; do Task 4 then re-run. To keep this task self-contained, you MAY implement the trivial `version` action now in `actions/meta.py` per Task 4 Step 3 and the `decks`/`meta` imports — but the canonical home is Task 4. Simplest: implement Task 4's `meta.py` and a stub `decks.py` (empty) here so the imports resolve, then flesh out decks in Task 5.)

> **Ordering / imports (IMPORTANT):** `app.py` runs a top-level `import ankiweb.ankiconnect.actions`, and `actions/__init__.py` imports BOTH `meta` and `decks` — so both module files MUST exist in THIS task (before the app imports them). Create them now as stubs:
>
> `ankiweb/ankiconnect/actions/meta.py` — minimal, just `version` (so `test_version_action` passes); Task 4 appends the rest:
> ```python
> from __future__ import annotations
> from ankiweb.ankiconnect.registry import action
>
>
> @action("version")
> async def version(rt):
>     return 6
> ```
>
> `ankiweb/ankiconnect/actions/decks.py` — an empty module (a docstring only); Task 5 fills it:
> ```python
> """AnkiConnect deck actions (filled in Task 5)."""
> ```

- [ ] **Step 5: Commit**

```bash
git add ankiweb/ankiconnect/cors.py ankiweb/ankiconnect/app.py ankiweb/ankiconnect/actions/ tests/ankiconnect/test_cors.py tests/ankiconnect/test_app.py
git commit -m "feat(ankiconnect): CORS helper + FastAPI app (POST/GET/OPTIONS, requestPermission injection)"
```

## Context
The 8765 app: `POST /` reads JSON, runs the CORS gate (403 for disallowed non-`requestPermission` origins), injects `allowed`/`origin` for `requestPermission`, dispatches, and returns the reply with ACAO headers. `GET /` and empty-body POST are the liveness probe. Lifespan supports injected (shared) or owned (standalone/test) service. Errors are in-band (200) per the dispatcher; only disallowed-origin is 403.

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 4: Meta actions (version, apiReflect, requestPermission, reloadCollection, profiles, sync)

**Files:**
- Modify: `ankiweb/ankiconnect/actions/meta.py` (replace the Task-3 `version`-only stub with the full implementation below)
- Test: `tests/ankiconnect/test_meta_actions.py`

- [ ] **Step 1: Write the failing test**

`tests/ankiconnect/test_meta_actions.py`:
```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.ankiconnect.app import create_ankiconnect_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_ankiconnect_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _call(client, action, **params):
    r = client.post("/", json={"action": action, "version": 6, "params": params})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None, body["error"]
    return body["result"]


def test_version(client):
    assert _call(client, "version") == 6


def test_api_reflect_lists_actions(client):
    res = _call(client, "apiReflect", scopes=["actions"])
    assert res["scopes"] == ["actions"]
    # deckNames isn't registered until Task 5 (decks); assert meta actions here
    assert "version" in res["actions"] and "requestPermission" in res["actions"]
    assert "multi" in res["actions"]


def test_request_permission_granted_for_localhost(client):
    r = client.post("/", json={"action": "requestPermission", "version": 6},
                    headers={"Origin": "http://localhost"})
    res = r.json()["result"]
    assert res["permission"] == "granted"


def test_get_profiles(client):
    assert _call(client, "getProfiles") == ["User 1"]
    assert _call(client, "getActiveProfile") == "User 1"


def test_reload_collection(client):
    assert _call(client, "reloadCollection") is None


def test_sync_excluded(client):
    r = client.post("/", json={"action": "sync", "version": 6})
    assert r.json()["error"] is not None  # sync is out of scope
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_meta_actions.py -v`
Expected: FAIL (actions not registered).

- [ ] **Step 3: Implement**

`ankiweb/ankiconnect/actions/meta.py`:
```python
from __future__ import annotations
from ankiweb.ankiconnect.registry import action, ACTIONS


@action("version")
async def version(rt):
    return 6


@action("apiReflect")
async def api_reflect(rt, scopes=None, actions=None):
    scopes = scopes or []
    out = {"scopes": [], "actions": []}
    if "actions" in scopes:
        out["scopes"] = ["actions"]
        names = sorted(ACTIONS.keys()) + ["multi"]
        if actions is not None:
            names = [n for n in names if n in actions]
        out["actions"] = names
    return out


@action("requestPermission")
async def request_permission(rt, allowed=False, origin=None):
    # CORS result is injected by the app. Single-user local → auto-grant when allowed.
    if not allowed:
        return {"permission": "denied"}
    return {"permission": "granted",
            "requireApikey": rt.config.api_key is not None,
            "version": 6}


@action("reloadCollection")
async def reload_collection(rt):
    # col.reset() is a deprecated no-op in anki 25.9.4; the single shared collection is
    # always live, so there's nothing to reload. Return None (AnkiConnect returns null).
    return None


@action("getProfiles")
async def get_profiles(rt):
    return ["User 1"]


@action("getActiveProfile")
async def get_active_profile(rt):
    return "User 1"


@action("loadProfile")
async def load_profile(rt, name=None):
    return True


@action("sync")
async def sync(rt):
    raise Exception("sync is not supported by ankiweb")
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_meta_actions.py -v`
Expected: PASS (also re-run `tests/ankiconnect/test_app.py` — `test_version_action` now passes).

- [ ] **Step 5: Commit**

```bash
git add ankiweb/ankiconnect/actions/meta.py tests/ankiconnect/test_meta_actions.py
git commit -m "feat(ankiconnect): meta actions (version/apiReflect/requestPermission/profiles/reload/sync)"
```

## Context
`apiReflect` lists the registry keys plus `multi` (which lives in the dispatcher, not the registry). `requestPermission` auto-grants on an allowed origin (no Qt dialog). Profiles are single-profile constants. `sync` raises (out of scope). `multi` is intentionally NOT registered here — it's handled in `dispatch_one`.

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 5: Deck actions

**Files:**
- Modify: `ankiweb/ankiconnect/actions/decks.py` (the stub created in Task 3)
- Test: `tests/ankiconnect/test_deck_actions.py`

- [ ] **Step 1: Write the failing test**

`tests/ankiconnect/test_deck_actions.py`:
```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.ankiconnect.app import create_ankiconnect_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_ankiconnect_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _call(client, action, **params):
    r = client.post("/", json={"action": action, "version": 6, "params": params})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None, body["error"]
    return body["result"]


def test_deck_names_has_default(client):
    assert "Default" in _call(client, "deckNames")


def test_create_and_list_deck(client):
    did = _call(client, "createDeck", deck="French")
    assert isinstance(did, int)
    names = _call(client, "deckNames")
    assert "French" in names
    nai = _call(client, "deckNamesAndIds")
    assert nai["French"] == did


def test_deck_name_from_id(client):
    did = _call(client, "createDeck", deck="Spanish")
    assert _call(client, "deckNameFromId", deckId=did) == "Spanish"


def test_delete_decks(client):
    _call(client, "createDeck", deck="Temp")
    assert _call(client, "deleteDecks", decks=["Temp"], cardsToo=True) is None
    assert "Temp" not in _call(client, "deckNames")


def test_delete_decks_requires_cards_too(client):
    _call(client, "createDeck", deck="Temp2")
    r = client.post("/", json={"action": "deleteDecks", "version": 6,
                               "params": {"decks": ["Temp2"]}})
    assert r.json()["error"] is not None  # cardsToo must be true


def test_get_deck_config(client):
    cfg = _call(client, "getDeckConfig", deck="Default")
    assert isinstance(cfg, dict) and "id" in cfg


def test_clone_and_remove_deck_config(client):
    new_id = _call(client, "cloneDeckConfigId", name="MyPreset")
    assert isinstance(new_id, int)
    assert _call(client, "removeDeckConfigId", configId=new_id) is True


def test_get_deck_stats(client):
    stats = _call(client, "getDeckStats", decks=["Default"])
    # keyed by deck id (as string in JSON); each entry has name + counts
    entry = list(stats.values())[0]
    assert entry["name"] == "Default"
    assert "new_count" in entry and "total_in_deck" in entry


def test_remove_unknown_or_default_config_returns_false(client):
    # get_config(missing) returns the Default config in 25.9.4, so the guard must
    # reject by id-mismatch; and the Default config (id 1) is never removable.
    assert _call(client, "removeDeckConfigId", configId=999999) is False
    assert _call(client, "removeDeckConfigId", configId=1) is False


def test_get_deck_config_missing_deck_does_not_create(client):
    assert _call(client, "getDeckConfig", deck="NoSuchDeck") is False
    assert "NoSuchDeck" not in _call(client, "deckNames")  # a read query must not create it
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_deck_actions.py -v`
Expected: FAIL (deck actions not registered).

- [ ] **Step 3: Implement (replace the `ankiweb/ankiconnect/actions/decks.py` stub)**

```python
from __future__ import annotations
from ankiweb.ankiconnect.registry import action


def _config_exists(col, conf_id) -> bool:
    """In anki 25.9.4 col.decks.get_config(missing) returns the DEFAULT config (id=1),
    NOT None — so an `is None` guard is a dead branch. Check existence by matching the
    returned dict's id to the requested id."""
    try:
        c = col.decks.get_config(int(conf_id))
    except Exception:
        return False
    return c is not None and int(c["id"]) == int(conf_id)


@action("deckNames")
async def deck_names(rt):
    return await rt.service.run(lambda col: [d.name for d in col.decks.all_names_and_ids()])


@action("deckNamesAndIds")
async def deck_names_and_ids(rt):
    return await rt.service.run(
        lambda col: {d.name: d.id for d in col.decks.all_names_and_ids()})


@action("getDecks")
async def get_decks(rt, cards=None):
    cards = cards or []

    def fn(col):
        out: dict[str, list] = {}
        for cid in cards:
            name = col.decks.name(col.get_card(cid).did)
            out.setdefault(name, []).append(cid)
        return out
    return await rt.service.run(fn)


@action("createDeck")
async def create_deck(rt, deck=None):
    # get-or-create; returns the deck id (AnkiConnect semantics)
    return await rt.service.run(lambda col: col.decks.id(deck))


@action("changeDeck")
async def change_deck(rt, cards=None, deck=None):
    cards = cards or []

    def fn(col):
        did = col.decks.id(deck)  # create target if missing
        return col.set_deck(cards, did)
    await rt.service.run_op(fn, initiator="ankiconnect")
    return None


@action("deleteDecks")
async def delete_decks(rt, decks=None, cardsToo=False):
    if not cardsToo:
        raise Exception("deleteDecks requires cardsToo=true (ankiweb won't keep orphan cards)")
    decks = decks or []

    def fn(col):
        ids = [col.decks.id_for_name(name) for name in decks]  # read-only: don't create
        ids = [i for i in ids if i is not None]
        return col.decks.remove(ids)
    await rt.service.run_op(fn, initiator="ankiconnect")
    return None


@action("getDeckConfig")
async def get_deck_config(rt, deck=None):
    def fn(col):
        did = col.decks.id_for_name(deck)  # read-only: don't create the deck on a query
        if did is None:
            return False
        return col.decks.config_dict_for_deck_id(did)
    return await rt.service.run(fn)


@action("saveDeckConfig")
async def save_deck_config(rt, config=None):
    def fn(col):
        if not config or not _config_exists(col, config.get("id")):
            return False
        col.decks.update_config(config)
        return True
    return await rt.service.run(fn)


@action("setDeckConfigId")
async def set_deck_config_id(rt, decks=None, configId=None):
    decks = decks or []

    def fn(col):
        if not _config_exists(col, configId):
            return False
        for name in decks:
            did = col.decks.id_for_name(name)  # read-only: skip missing decks
            if did is None:
                continue
            d = col.decks.get(did)
            d["conf"] = int(configId)
            col.decks.save(d)
        return True
    return await rt.service.run(fn)


@action("cloneDeckConfigId")
async def clone_deck_config_id(rt, name=None, cloneFrom="1"):
    def fn(col):
        if not _config_exists(col, cloneFrom):
            return False
        clone = col.decks.get_config(int(cloneFrom))
        return col.decks.add_config_returning_id(name, clone)
    return await rt.service.run(fn)


@action("removeDeckConfigId")
async def remove_deck_config_id(rt, configId=None):
    def fn(col):
        # refuse the Default config (id 1 → backend raises) and unknown ids
        if int(configId) == 1 or not _config_exists(col, configId):
            return False
        col.decks.remove_config(int(configId))
        return True
    return await rt.service.run(fn)


@action("getDeckStats")
async def get_deck_stats(rt, decks=None):
    names = decks or []

    def fn(col):
        # deck_due_tree() nodes carry LEAF names, so match by id (not name): resolve each
        # requested full name → id (read-only), then find its node in the tree.
        tree = col.sched.deck_due_tree()
        out: dict[str, dict] = {}
        for name in names:
            did = col.decks.id_for_name(name)  # read-only: don't create unknown decks
            if did is None:
                continue
            node = col.decks.find_deck_in_tree(tree, did)
            if node is None:  # exists but pruned from the due-tree (e.g. empty) → zeros
                out[str(did)] = {"deck_id": did, "name": name, "new_count": 0,
                                 "learn_count": 0, "review_count": 0, "total_in_deck": 0}
            else:
                out[str(did)] = {"deck_id": did, "name": name,
                                 "new_count": node.new_count, "learn_count": node.learn_count,
                                 "review_count": node.review_count,
                                 "total_in_deck": node.total_in_deck}
        return out
    return await rt.service.run(fn)


@action("deckNameFromId")
async def deck_name_from_id(rt, deckId=None):
    return await rt.service.run(lambda col: col.decks.name(deckId))
```

> **NOTE:** the deck-config existence guards use `_config_exists` because `col.decks.get_config(missing)` returns the Default config (id=1) in 25.9.4, not `None`. The read actions (`getDeckConfig`/`getDeckStats`) use `col.decks.id_for_name` (read-only) instead of `col.decks.id` (get-or-create) so a query never silently creates a deck. `getDeckStats` matches tree nodes by id via `find_deck_in_tree` (nodes carry leaf names), correct for sub-decks too.

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_deck_actions.py -v`
Expected: PASS (8 tests). Adjust `getDeckStats` per the NOTE if needed so the `Default` test passes.

- [ ] **Step 5: Commit**

```bash
git add ankiweb/ankiconnect/actions/decks.py tests/ankiconnect/test_deck_actions.py
git commit -m "feat(ankiconnect): deck actions (names/create/change/delete/config/stats)"
```

## Context
13 deck actions, thin wrappers over `col.decks`/`col.set_deck` verified live: `all_names_and_ids()`→DeckNameId(.name/.id); `id(name)` get-or-create; `config_dict_for_deck_id`/`get_config`/`update_config`/`add_config_returning_id`/`remove_config`/`save`; `set_deck`/`decks.remove` return OpChanges → use `run_op` (web UI refreshes). `deleteDecks` requires `cardsToo`. `getDeckStats` walks `col.sched.deck_due_tree()`.

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 6: Shared-service wiring + dual-server entrypoint

**Files:**
- Modify: `ankiweb/app.py` (inject service/hub), `ankiweb/__main__.py`
- Test: `tests/ankiconnect/test_shared_service.py`

- [ ] **Step 1: Write the failing test**

`tests/ankiconnect/test_shared_service.py`:
```python
import inspect
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.app import create_app
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.ankiconnect.runtime import Runtime
from ankiweb.ankiconnect.actions.decks import create_deck
from ankiweb.screens.deckbrowser import render_deckbrowser_html


async def test_both_layers_share_one_service(tmp_path: Path):
    # Prove the API action layer and the web renderer operate on the SAME collection,
    # all on ONE event loop (the test's). NOTE: do NOT use two TestClients sharing one
    # service — each TestClient runs on its own loop and the service's asyncio.Lock would
    # bind to the first and raise on the second. The production dual-server path is fine
    # because both uvicorn servers run in one asyncio.gather loop (see __main__.py).
    settings = Settings(collection_path=tmp_path / "c.anki2")
    service = CollectionService(settings)
    await service.open()
    try:
        rt = Runtime(service=service, config=AnkiConnectConfig())
        did = await create_deck(rt, deck="Shared")          # AnkiConnect action layer
        assert isinstance(did, int)
        html = await service.run(render_deckbrowser_html)    # web UI renderer, same service
        assert "Shared" in html
    finally:
        await service.close()


def test_create_app_accepts_injection_kwargs():
    # the dual-server entrypoint calls create_app(settings, service=, hub=)
    params = inspect.signature(create_app).parameters
    assert "service" in params and "hub" in params


def test_create_app_standalone_still_opens_own_service(tmp_path: Path):
    # injecting nothing → app owns its service (existing behavior, all other tests rely on it)
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as w:
        assert w.get("/healthz").json() == {"ok": True}
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_shared_service.py -v`
Expected: FAIL (`create_app()` doesn't accept `service=`).

- [ ] **Step 3: Refactor `create_app` for injection**

In `ankiweb/app.py`, change `create_app` to accept an optional shared service/hub and only own them when not injected. Replace the signature + lifespan:
```python
def create_app(settings: Settings | None = None, service: CollectionService | None = None,
               hub=None) -> FastAPI:
    settings = settings or Settings.from_env()
    owns = service is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = service
        h = hub
        if owns:
            svc = CollectionService(settings)
            await svc.open()
        if h is None:
            h = BridgeHub()
        svc.subscribe(lambda flags, initiator: h.broadcast_opchanges(flags, initiator))
        register_screen_handlers(svc, h)
        app.state.settings = settings
        app.state.service = svc
        app.state.hub = h
        try:
            yield
        finally:
            if owns:
                await svc.close()
    ...
```
(Keep the rest of `create_app` — middleware, routes, includes — unchanged. The only changes are the signature, the `owns`/injected service, and a hub created if not supplied. Note: when a service is injected and shared, the subscribe-binding registers an additional OpChanges subscriber each time an app is created — acceptable here since the test creates each app once; the entrypoint creates each once too.)

- [ ] **Step 4: Dual-server entrypoint**

Replace `ankiweb/__main__.py`:
```python
from __future__ import annotations
import asyncio
import uvicorn
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.bridge.hub import BridgeHub
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.app import create_app
from ankiweb.ankiconnect.app import create_ankiconnect_app


async def _serve() -> None:
    settings = Settings.from_env()
    ac_config = AnkiConnectConfig.load(settings.collection_path.parent / "ankiconnect.json")
    service = CollectionService(settings)
    await service.open()
    hub = BridgeHub()
    web = create_app(settings, service=service, hub=hub)
    api = create_ankiconnect_app(settings, service=service, config=ac_config, hub=hub)
    web_server = uvicorn.Server(uvicorn.Config(web, host=settings.host, port=settings.port,
                                               log_level="info"))
    api_server = uvicorn.Server(uvicorn.Config(api, host=ac_config.bind_address,
                                               port=ac_config.bind_port, log_level="info"))
    try:
        await asyncio.gather(web_server.serve(), api_server.serve())
    finally:
        await service.close()


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
```

> Note: both apps are created with `service`/`hub` injected, so their lifespans do NOT open/close the service (the entrypoint owns it). Running both `uvicorn.Server.serve()` in one `asyncio.gather` keeps them on one event loop, so the service's `asyncio.Lock` is shared correctly. The web UI app, given an injected service, must still create/run its lifespan for routes/hub wiring — the injected-service branch handles that.

- [ ] **Step 5: Run to verify pass + manual dual-server smoke**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_shared_service.py -v`
Then the full suite: `conda run -n ankiweb python -m pytest -q`.
Manual smoke (temp collection so the real home isn't touched):
```bash
ANKIWEB_COLLECTION=/tmp/ankiweb_b1/c.anki2 ANKIWEB_PORT=8061 conda run -n ankiweb python -m ankiweb &
SRV=$!; sleep 4
curl -s http://127.0.0.1:8061/healthz                                  # web UI: {"ok":true}
curl -s -X POST http://127.0.0.1:8765/ -d '{"action":"version","version":6}'  # API: {"result":6,"error":null}
curl -s -X POST http://127.0.0.1:8765/ -d '{"action":"deckNames","version":6}'
kill $SRV; rm -rf /tmp/ankiweb_b1
```
Expected: web UI healthz ok on the chosen port AND the AnkiConnect API answers on 8765.

- [ ] **Step 6: Commit**

```bash
git add ankiweb/app.py ankiweb/__main__.py tests/ankiconnect/test_shared_service.py
git commit -m "feat(ankiconnect): share one collection across web UI + API; run both servers"
```

## Context
Both apps share one externally-owned `CollectionService` so API writes are visible in the web UI immediately (proven by the shared-service test creating a deck via the API and seeing it in `/deckbrowser`). The entrypoint runs both uvicorn servers in one event loop. `create_app` stays backward-compatible (standalone when no service injected — all existing tests unaffected).

## Report Format
Report: Status, test results (shared-service + full suite), the manual-smoke curl outputs, files changed, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (B1 portion of the B spec §1–§2):** §1.1 separate 8765 app + shared service (T3, T6); §1.2 JSON-RPC contract/envelope/version/multi/apiReflect/empty-probe (T2, T3, T4); §1.3 auth+CORS+requestPermission (T2 apiKey, T3 CORS+requestPermission injection, T4 requestPermission action); §2 Decks group (T5) + meta/profiles (T4). Stats, export/import, Notes/Cards/Models/Media/gui* → later plans (documented).

**2. Placeholder scan:** No TBD/TODO. The `getDeckStats` sub-deck NOTE is an explicit verify-and-adjust instruction with a concrete fallback (`find_deck_in_tree`), not a placeholder. The `decks.py` stub in Task 3 is created-then-filled in Task 5 (explicit).

**3. Type/name consistency:** `Runtime(service, config, hub, ui_state)` (T1) used everywhere; `ACTIONS`/`action` (T2) used by all action modules + apiReflect; `dispatch_one(rt, req)` (T2) used by app (T3) and multi (recursive); `allow_origin(origin, cors_list)->(bool,str)` (T3) used by app; `create_ankiconnect_app(settings, service, config, hub)` (T3) used by tests + entrypoint; `create_app(settings, service, hub)` injection (T6) used by entrypoint + shared test. Action handlers are `async def(rt, **params)` and registered via `@action("name")`. `rt.service.run`/`run_op(fn, initiator)` are existing CollectionService APIs.
