# ankiweb Plan E3 — Change Notetype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve Anki's real SvelteKit Change-Notetype page at `GET /change-notetype/{ids}` (reusing the E1/E2 SPA foundation), convert the selected notes via `change_notetype` (broadcasting so the browser/UI refresh), and open it from the browser's "Change Notetype" action.

**Architecture:** Add `GET /change-notetype/{ids:path}` to `build_sveltekit_router` (serves the same SvelteKit `index.html`; the SPA client-routes on `location.pathname` — its `[...notetypeIds]/+page.ts` splits the path on `/` into `oldNotetypeId` and optional `newNotetypeId`). The page's load RPCs (`getNotetypeNames`, `getChangeNotetypeInfo`) are **already in PASSTHROUGH** (read-only). The **write** `changeNotetype` becomes a CUSTOM handler. **Crucial wrinkle (recon-confirmed):** the SvelteKit `dataForSaving()` builds a `ChangeNotetypeRequest` with **empty `note_ids`** — in Qt, `ChangeNotetypeDialog.save()` injects `input.note_ids.extend(self._note_ids)` server-side from the dialog's stored selection. So the headless `changeNotetype` handler must likewise inject the note ids: it reads `hub.ui_state.selected_note_ids` (the browser's current selection, persisted on the singleton hub), falls back to **all notes of the old notetype** (`col.models.nids(old_notetype_id)`) when there is no selection (so a directly-opened page still works), parses+re-serializes the request with `note_ids` set, runs `change_notetype_raw`, and parses+broadcasts the returned `OpChanges`. Giving the handler the selection requires the RPC dispatch to pass the hub to CUSTOM handlers — a small signature change (`CUSTOM[method](service, body, hub)`). The browser's "Change Notetype" action derives the single old notetype id from the selected notes (`get_single_notetype_of_notes`) and navigates to `/change-notetype/{old_id}`.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the E1 `build_sveltekit_router`, the `anki_rpc` passthrough/CUSTOM mechanism, the `BridgeHub`/`UiState`, pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is E3 of Sub-project E.** Spec: `docs/superpowers/specs/2026-06-01-ankiweb-specialized-screens-design.md`. Builds on E1 (`/graphs` SPA serve foundation) + E2 (`/deck-options` CUSTOM write+broadcast pattern). Next: E4/E5 (custom-study/filtered-deck REBUILDs).

**Grounded facts (live-probed + source-read against `/mnt/sda/git/tools/anki`):**
- Backend `*_raw` all exist: `get_change_notetype_info_raw`, `change_notetype_raw`, `get_notetype_names_raw`. `get_notetype_names` AND `get_change_notetype_info` are **already in PASSTHROUGH** (`ankiweb/anki_rpc/passthrough.py:9`).
- `change_notetype_raw(req)` MUTATES (Basic→Cloze proven) and returns `OpChanges` with `note=True` (so `op_changes_to_flags` yields a truthy flag → broadcast fires). `from anki.collection_pb2 import OpChanges` works.
- `GetChangeNotetypeInfoRequest` fields: `old_notetype_id`, `new_notetype_id`. `ChangeNotetypeInfo` fields: `old_field_names`, `old_template_names`, `new_field_names`, `new_template_names`, `input` (a prefilled `ChangeNotetypeRequest`), `old_notetype_name`.
- `ChangeNotetypeRequest` fields: `note_ids`, `new_fields`, `new_templates`, `old_notetype_id`, `new_notetype_id`, `current_schema`, `old_notetype_name`, `is_cloze`. The page's `dataForSaving()` sets everything **except `note_ids`** (confirmed: Qt's `save()` does `input.note_ids.extend(self._note_ids)`).
- `col.models.nids(old_notetype_id)` returns all note ids of that notetype (accepts an int id OR a model dict). `col.models.get_single_notetype_of_notes([nids])` returns the single notetype id (raises if the notes span multiple types).
- The SvelteKit route is `ts/routes/change-notetype/[...notetypeIds]/`; `+page.ts` does `const [fromIdStr, toIdStr] = params.notetypeIds.split("/")` → `oldNotetypeId = BigInt(fromIdStr)`, `newNotetypeId = toIdStr ? BigInt(toIdStr) : oldNotetypeId`. So `/change-notetype/{old}` (one id; new defaults to old) and `/change-notetype/{old}/{new}` both work. **OLD id first.** Qt launches `load_sveltekit_page(f"change-notetype/{notetype_id}")` (single old id).
- **No host-bridge coupling:** the change-notetype page has NO `*Ready`/`*RequireClose`/pycmd calls (unlike deck-options). The only "close" signal in Qt is the save completing (Python closes the QDialog). So E3 needs NO no-op FrontendService handlers.
- The anki_rpc dispatch: `POST /_anki/{method}` → `if method in CUSTOM` (camelCase key) → handler; `elif camel_to_snake(method) in PASSTHROUGH` → `service.backend_raw(snake, body)`; else 404. `service.backend_raw(snake, body)` runs `col._backend.<snake>_raw(body)`; `service.emit(flags, initiator)` broadcasts. `hub.ui_state.selected_note_ids` is maintained by the browser screen's `select` cmd (`ankiweb/screens/browser.py:190-191`).

**Known limitation (documented, accepted for E3):** the converted note set is the browser's current selection (`hub.ui_state.selected_note_ids`), snapshotted implicitly via the singleton hub; if the user changes the browser selection while the change-notetype page is open, the new selection is what gets converted. When there is NO selection (page opened directly), the handler converts ALL notes of the old notetype (the only well-defined interpretation). This matches Anki's "convert the notes you came in with" semantics for the common browser-launched path.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/assets.py` (modify) | add `GET /change-notetype/{ids:path}` to `build_sveltekit_router` |
| `ankiweb/anki_rpc/__init__.py` (modify) | dispatch passes the hub to CUSTOM handlers: `build_router(get_service, get_hub)`, `CUSTOM[method](service, body, hub)` |
| `ankiweb/anki_rpc/handlers.py` (modify) | all handlers gain a `hub` param; add CUSTOM `changeNotetype` (inject note_ids → run + broadcast) |
| `ankiweb/app.py` (modify) | `build_rpc_router(lambda: app.state.service, lambda: app.state.hub)` |
| `ankiweb/screens/browser.py` (modify) | `changenotetype` cmd → derive old notetype id → navigate `/change-notetype/{old_id}` |
| `tests/test_change_notetype.py` (create) | route + CUSTOM + inject/round-trip + browser-nav tests |
| `tests/test_change_notetype_integration.py` (create) | Playwright: the change-notetype SPA mounts + loads |

---

## Task 1: `/change-notetype` route + hub-aware CUSTOM `changeNotetype` + browser deep-link

**Files:** Modify `ankiweb/assets.py`, `ankiweb/anki_rpc/__init__.py`, `ankiweb/anki_rpc/handlers.py`, `ankiweb/app.py`, `ankiweb/screens/browser.py`; Test `tests/test_change_notetype.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_change_notetype.py`:
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


def _basic_cloze(client):
    def ids(col):
        return col.models.by_name("Basic")["id"], col.models.by_name("Cloze")["id"]
    return client.portal.call(client.app.state.service.run, ids)


def test_change_notetype_serves_spa_shell_one_id(client):
    old, _new = _basic_cloze(client)
    r = client.get(f"/change-notetype/{old}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "_app/immutable/entry" in r.text


def test_change_notetype_serves_spa_shell_two_ids(client):
    old, new = _basic_cloze(client)
    r = client.get(f"/change-notetype/{old}/{new}")
    assert r.status_code == 200
    assert "_app/immutable/entry" in r.text


def test_changenotetype_registered_custom():
    from ankiweb.anki_rpc.handlers import CUSTOM
    assert "changeNotetype" in CUSTOM


def test_get_change_notetype_info_passthrough(client):
    # the page's load RPC is reachable (read); not 404
    r = client.post("/_anki/get_change_notetype_info", content=b"",
                    headers={"content-type": "application/binary"})
    assert r.status_code != 404


def test_change_notetype_converts_selected_notes_and_broadcasts(client):
    # mirror the page: build a ChangeNotetypeRequest from info.input with EMPTY note_ids;
    # the handler must inject hub.ui_state.selected_note_ids and convert just those.
    import anki.notetypes_pb2 as nt
    old, new = _basic_cloze(client)
    svc = client.app.state.service

    def seed(col):
        n1 = col.new_note(col.models.get(old)); n1["Front"] = "a"; n1["Back"] = "b"
        col.add_note(n1, col.decks.id("Default"))
        n2 = col.new_note(col.models.get(old)); n2["Front"] = "c"; n2["Back"] = "d"
        col.add_note(n2, col.decks.id("Default"))
        return n1.id, n2.id
    nid1, nid2 = client.portal.call(svc.run, seed)

    # select only nid1 in the (server-side) ui_state, as the browser would
    client.app.state.hub.ui_state.selected_note_ids = [nid1]

    info = client.portal.call(svc.run, lambda col: col.models.change_notetype_info(old, new))
    req = info.input            # prefilled ChangeNotetypeRequest, note_ids EMPTY
    assert list(req.note_ids) == []
    r = client.post("/_anki/changeNotetype", content=req.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 200
    mids = client.portal.call(
        svc.run, lambda col: (col.get_note(nid1).mid, col.get_note(nid2).mid))
    assert mids[0] == new          # nid1 converted (it was selected)
    assert mids[1] == old          # nid2 untouched (not selected)


def test_change_notetype_falls_back_to_all_notes_when_no_selection(client):
    import anki.notetypes_pb2 as nt
    old, new = _basic_cloze(client)
    svc = client.app.state.service

    def seed(col):
        n = col.new_note(col.models.get(old)); n["Front"] = "x"; n["Back"] = "y"
        col.add_note(n, col.decks.id("Default"))
        return n.id
    nid = client.portal.call(svc.run, seed)
    client.app.state.hub.ui_state.selected_note_ids = []     # no selection

    info = client.portal.call(svc.run, lambda col: col.models.change_notetype_info(old, new))
    r = client.post("/_anki/changeNotetype", content=info.input.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 200
    assert client.portal.call(svc.run, lambda col: col.get_note(nid).mid) == new


def test_browser_change_notetype_navigates(client):
    old, _new = _basic_cloze(client)
    svc = client.app.state.service

    def seed(col):
        n = col.new_note(col.models.get(old)); n["Front"] = "q"; n["Back"] = "r"
        col.add_note(n, col.decks.id("Default"))
        return col.find_cards("")[0]
    cid = client.portal.call(svc.run, seed)
    with client.websocket_connect("/ws?context=browser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": f"select:{cid}"})
        ws.send_json({"type": "cmd", "id": None, "ctx": "browser", "arg": "changenotetype:"})
        m = ws.receive_json()
        while not (m["type"] == "call" and m["fn"] == "ankiwebNavigate"):
            m = ws.receive_json()
        assert m["args"] == [f"/change-notetype/{old}"]
```
(NOTE: `col.models.change_notetype_info(old, new)` is the pylib wrapper for `get_change_notetype_info` and returns a `ChangeNotetypeInfo` whose `.input` is the prefilled `ChangeNotetypeRequest` with empty `note_ids` — exactly what the SvelteKit `dataForSaving()` produces, so it's the faithful test fixture. If the wrapper name differs, build the request via `anki.notetypes_pb2.GetChangeNotetypeInfoRequest(old_notetype_id=old, new_notetype_id=new)` through `service.backend_raw("get_change_notetype_info", req.SerializeToString())` and parse `ChangeNotetypeInfo`. The load-bearing assertions are the per-note `mid` conversions.)

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_change_notetype.py -v` → FAIL.

- [ ] **Step 3: Add the route** — in `ankiweb/assets.py` `build_sveltekit_router`, next to `/graphs` and `/deck-options/{deck_id}`:
```python
    @router.get("/change-notetype/{ids:path}")
    def change_notetype_page(ids: str) -> Response:
        return FileResponse(index, media_type="text/html")
```
(`{ids:path}` matches both `change-notetype/{old}` and `change-notetype/{old}/{new}`.)

- [ ] **Step 4: Pass the hub to CUSTOM handlers** — in `ankiweb/anki_rpc/__init__.py`, change `build_router` to also take `get_hub` and pass the hub as a 3rd handler arg:
```python
def build_router(get_service, get_hub) -> APIRouter:
    router = APIRouter()

    @router.post("/_anki/{method}")
    async def rpc(method: str, request: Request) -> Response:
        if request.headers.get("content-type") != BINARY:
            return PlainTextResponse("bad content type", status_code=403)
        body = await request.body()
        service = get_service()
        snake = camel_to_snake(method)

        from ankiweb.anki_rpc.handlers import CUSTOM
        try:
            if method in CUSTOM:
                out = await CUSTOM[method](service, body, get_hub())
            elif snake in PASSTHROUGH:
                out = await service.backend_raw(snake, body)
            else:
                return PlainTextResponse("not found", status_code=404)
        except Exception as exc:
            return PlainTextResponse(str(exc), status_code=500)

        if not out:
            return Response(status_code=204)
        return Response(content=bytes(out), media_type=BINARY)

    return router
```

- [ ] **Step 5: Update all CUSTOM handlers to the `(service, body, hub)` signature + add `changeNotetype`** — in `ankiweb/anki_rpc/handlers.py`. Add `hub` to the existing three (they ignore it), then add the new handler:
```python
from __future__ import annotations
from typing import Awaitable, Callable

# camelCaseMethod -> async handler(service, body: bytes, hub) -> bytes
CUSTOM: dict[str, Callable[..., Awaitable[bytes]]] = {}


async def save_custom_colours(service, body: bytes, hub) -> bytes:
    return b""


CUSTOM["saveCustomColours"] = save_custom_colours


async def update_deck_configs(service, body: bytes, hub) -> bytes:
    out = await service.backend_raw("update_deck_configs", body)
    try:
        from anki.collection_pb2 import OpChanges
        from ankiweb.collection_service import op_changes_to_flags
        op = OpChanges()
        op.ParseFromString(bytes(out))
        flags = op_changes_to_flags(op)
        if any(flags.values()):
            await service.emit(flags, "deck-options")
    except Exception:
        pass
    return out


async def _noop(service, body: bytes, hub) -> bytes:
    return b""


async def change_notetype(service, body: bytes, hub) -> bytes:
    """Convert notes to a new notetype. The SvelteKit page's request has EMPTY note_ids
    (Qt injects them server-side from the dialog's selection); inject the browser's
    current selection here, falling back to ALL notes of the old notetype."""
    import anki.notetypes_pb2 as nt
    req = nt.ChangeNotetypeRequest()
    req.ParseFromString(bytes(body))
    if not list(req.note_ids):
        nids = list(getattr(hub.ui_state, "selected_note_ids", []) or [])
        if not nids:
            nids = await service.run(lambda col: list(col.models.nids(req.old_notetype_id)))
        req.note_ids.extend(nids)
    out = await service.backend_raw("change_notetype", req.SerializeToString())
    try:
        from anki.collection_pb2 import OpChanges
        from ankiweb.collection_service import op_changes_to_flags
        op = OpChanges()
        op.ParseFromString(bytes(out))
        flags = op_changes_to_flags(op)
        if any(flags.values()):
            await service.emit(flags, "change-notetype")
    except Exception:
        pass
    return out


CUSTOM["updateDeckConfigs"] = update_deck_configs
CUSTOM["deckOptionsReady"] = _noop
CUSTOM["deckOptionsRequireClose"] = _noop
CUSTOM["changeNotetype"] = change_notetype
```
(Before editing, `grep -rn "CUSTOM\[" tests/ ankiweb/` and `grep -rn "save_custom_colours\|update_deck_configs\|_noop(" tests/` to confirm no test calls these handler functions directly with the old 2-arg signature; they're invoked over HTTP, so the dispatch change covers them. If a direct-call test exists, update it to pass a hub (or `None`).)

- [ ] **Step 6: Wire the RPC router with the hub** — in `ankiweb/app.py`, update the include:
```python
    app.include_router(build_rpc_router(lambda: app.state.service, lambda: app.state.hub))  # POST /_anki/{method}
```

- [ ] **Step 7: Wire the browser deep-link** — in `ankiweb/screens/browser.py` `handler`, add a `changenotetype` branch (place it among the other `elif cmd ==` branches, e.g. after `changedeck`):
```python
        elif cmd == "changenotetype":
            cids = list(hub.ui_state.selected_card_ids or [])
            nids = list(hub.ui_state.selected_note_ids or [])
            if not nids and cids:
                nids = await service.run(lambda col: _nids(col, cids))
            if nids:
                try:
                    old = await service.run(
                        lambda col: col.models.get_single_notetype_of_notes(nids))
                except Exception:
                    return None
                await hub.push_call("browser", "ankiwebNavigate",
                                    ["/change-notetype/" + str(old)])
```
(`_nids` is the existing helper in this file. `get_single_notetype_of_notes` raises if the selection spans multiple notetypes — swallow and no-op, matching Qt's "showWarning + return".)

- [ ] **Step 8: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_change_notetype.py -v`, then regression:
`conda run -n ankiweb python -m pytest tests/test_deck_options.py tests/test_graphs.py tests/test_anki_rpc.py tests/test_browser.py tests/test_screen_routes.py -q`.

- [ ] **Step 9: Commit**
```bash
git add ankiweb/assets.py ankiweb/anki_rpc/__init__.py ankiweb/anki_rpc/handlers.py ankiweb/app.py ankiweb/screens/browser.py tests/test_change_notetype.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(change-notetype): serve the SvelteKit change-notetype SPA + note_ids-injecting changeNotetype handler + browser deep-link"
```

## Context
`/change-notetype/{ids}` serves the same SvelteKit shell (E1 foundation); the SPA reads the old/new ids from the path and loads via `getNotetypeNames` + `getChangeNotetypeInfo` (both already passthrough). Save POSTs `changeNotetype` with EMPTY note_ids → the CUSTOM handler injects `hub.ui_state.selected_note_ids` (browser selection; falls back to all notes of the old notetype), runs the backend write, and broadcasts the returned `OpChanges` (browser/deck-browser refresh). The handler now receives the hub because the dispatch passes it. The browser's "Change Notetype" action derives the single old notetype id and navigates to the page. No host-bridge/close RPCs (the change-notetype page has none).

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns (incl. whether `col.models.change_notetype_info` existed as the test fixture or you fell back to the raw path, and whether any direct-call test needed the new signature).

---

## Task 2: Playwright — the change-notetype SPA mounts + loads

**Files:** Create `tests/test_change_notetype_integration.py`.

- [ ] **Step 1: Write the test** — mirror `tests/test_deck_options_integration.py`'s `live_server` (uvicorn thread, fresh port 8132, `pytest.importorskip`, inline `sync_playwright`, the `pageerror`/`requestfailed`/`request` instrumentation). Seed a Basic note so the notetype exists with content; open `/change-notetype/{old_id}`; assert it mounts, the load RPC fired, no errors:
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
def live_server_cnt(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    col = Collection(str(col_path))
    try:
        old = col.models.by_name("Basic")["id"]
        n = col.new_note(col.models.get(old))
        n["Front"] = "x"
        n["Back"] = "y"
        col.add_note(n, col.decks.id("Default"))
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8132)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8132, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8132", old
    server.should_exit = True
    t.join(timeout=5)


def test_change_notetype_spa_boots(live_server_cnt):
    url, old = live_server_cnt
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed",
                lambda r: errors.append("REQFAIL " + r.url) if ("/_app/" in r.url or "/_anki/" in r.url) else None)
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/_anki/" in r.url else None)
        page.goto(f"{url}/change-notetype/{old}")
        page.wait_for_function("document.querySelectorAll('select,button,table').length>1", timeout=10000)
        page.wait_for_function("document.body.innerText.length>20", timeout=10000)
        assert not errors, errors
        assert any("get_change_notetype_info" in u.lower() or "getchangenotetypeinfo" in u.lower()
                   for u in posts), posts
        browser.close()
```
(NOTE: pick the most stable mount selector by inspecting the rendered page — the change-notetype UI has a target-notetype `<select>` and a field/template mapping `<table>`. Load-bearing asserts: no `/_app/` or `/_anki/` request failed, no page error, and the `getChangeNotetypeInfo` POST fired. If a benign pageerror/requestfailed appears, narrow the filter with a comment explaining why it's benign — never weaken the load-bearing asserts. If the selector times out, dump `page.content()` to find a real element and adjust.)

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_change_notetype_integration.py -v` (PASS if chromium available; SKIPS if not). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_change_notetype_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(change-notetype): Playwright — the SvelteKit change-notetype SPA boots + loads"
```

## Context
End-to-end proof the real change-notetype SvelteKit page boots through ankiweb's routes: fetches its `/_app/` chunks, POSTs `getNotetypeNames` + `getChangeNotetypeInfo` to `/_anki/`, and renders its mapping UI with zero errors. The write path (`changeNotetype` inject + convert + broadcast) is proven by the Task-1 round-trip tests.

## Report Format
Status, pytest summary (Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (E3 = change notetype):** `/change-notetype/{ids}` route reusing the E1/E2 SPA foundation (Task 1, both 1-id and 2-id path forms); `getNotetypeNames` + `getChangeNotetypeInfo` load (already passthrough — verified at `passthrough.py:9`); `changeNotetype` write via a CUSTOM handler that injects note_ids (recon-confirmed Qt server-side injection) + broadcasts OpChanges (Task 1, round-trip + fallback tested); browser "Change Notetype" → `/change-notetype/{old_id}` deep-link (a D4 deferral) (Task 1); Playwright mount+load proof (Task 2). No host-bridge/close handlers (the change-notetype page has none — unlike deck-options). Deferred (documented): selection-snapshot timing; the all-notes fallback for directly-opened pages.

**2. Placeholder scan:** No TBD/TODO. The test fixture uses `col.models.change_notetype_info(old, new)` with a documented raw-path fallback. The Playwright mount selector is confirmed-by-inspection (load-bearing asserts = no-errors + the load RPC fired).

**3. Type/name consistency:** `build_sveltekit_router` gains `GET /change-notetype/{ids:path}` (alongside E1 `/graphs` + E2 `/deck-options/{deck_id}`). `build_router(get_service, get_hub)` (was `get_service` only) → `app.py` passes `lambda: app.state.hub`. ALL CUSTOM handlers gain a `hub` param (`save_custom_colours`, `update_deck_configs`, `_noop`, new `change_notetype`) — the dispatch calls `CUSTOM[method](service, body, get_hub())`. `change_notetype` parses `anki.notetypes_pb2.ChangeNotetypeRequest`, injects `hub.ui_state.selected_note_ids` (∪ fallback `col.models.nids(old_notetype_id)`), `service.backend_raw("change_notetype", ...)`, `OpChanges` parse via `anki.collection_pb2` + `op_changes_to_flags` + `service.emit`. browser `changenotetype:` → `get_single_notetype_of_notes(nids)` → `ankiwebNavigate("/change-notetype/"+str(old))`. All backend methods + `OpChanges` import + the empty-note_ids/Qt-injection behavior are live-verified.

**4. Risks:** The dispatch-signature change touches every CUSTOM handler — Step 5 updates all of them in one edit, and Step 8's regression run (`test_deck_options`/`test_anki_rpc`) confirms `saveCustomColours`/`updateDeckConfigs`/`deckOptionsReady`/`deckOptionsRequireClose` still answer correctly over HTTP. `change_notetype` re-serializes the request after injecting note_ids (preserves `current_schema`/`new_fields`/etc. from the page). The all-notes fallback only triggers with an empty selection (documented; the common browser path always has a selection). Route ordering: the new page route is in `build_sveltekit_router` (already before the media catch-all). The browser `changenotetype` no-ops (no nav) when the selection spans multiple notetypes (matches Qt's showWarning+return).
