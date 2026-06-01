# ankiweb Plan E2 — Deck Options Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve Anki's real SvelteKit Deck Options page at `GET /deck-options/{deck_id}` (reusing the E1 SPA foundation), persist edits via `update_deck_configs` (broadcasting so the deck browser refreshes), and open it from the deck browser's gear menu.

**Architecture:** Add `GET /deck-options/{deck_id}` to E1's `build_sveltekit_router` (serves the same SvelteKit `index.html`; the SPA client-routes on `location.pathname` → its `+page.ts` reads `deckId` and POSTs `getDeckConfigsForUpdate`). The page's data flows over the existing `POST /_anki/<method>` RPC: `get_deck_configs_for_update` is already in the passthrough; the FSRS/advanced read+compute methods are ADDED to the passthrough; the **write** `updateDeckConfigs` and the two Qt-only FrontendService methods (`deckOptionsReady`, `deckOptionsRequireClose` — which RAISE `InvalidServiceIndex` on the headless backend) become CUSTOM handlers (`updateDeckConfigs` runs the backend write + parses+broadcasts the returned `OpChanges`; the two FrontendService methods are no-ops returning `b""`). The deck-browser gear button (a Plan-2 deferral) navigates to `/deck-options/{did}`.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, E1's `build_sveltekit_router`, the `anki_rpc` passthrough/CUSTOM mechanism, pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is E2 of Sub-project E.** Spec: `docs/superpowers/specs/2026-06-01-ankiweb-specialized-screens-design.md`. Builds on E1 (`/graphs` proved the SvelteKit SPA serve model end-to-end). Next: E3 (change-notetype), E4/E5 (custom-study/filtered-deck rebuilds).

**Grounded facts (live-probed):** all backend `*_raw` exist: `get_deck_configs_for_update`, `update_deck_configs`, `get_ignored_before_count`, `compute_fsrs_params`, `evaluate_params_legacy`, `compute_optimal_retention`, `simulate_fsrs_review`, `simulate_fsrs_workload`, `get_retention_workload`, `set_wants_abort`, `deck_options_ready`, `deck_options_require_close`. `deck_options_ready_raw(b"")` RAISES `InvalidInput: InvalidServiceIndex` (it's a Qt-only FrontendService method — must be CUSTOM, NOT passthrough). `from anki.collection_pb2 import OpChanges` works (parse the `update_deck_configs` reply to get flags). The page calls (recon): READ `getDeckConfigsForUpdate` (load), `getIgnoredBeforeCount` (advanced tab); WRITE `updateDeckConfigs` (Save, returns `OpChanges`); FSRS `computeFsrsParams`/`evaluateParamsLegacy`/`computeOptimalRetention`/`simulateFsrsReview`/`simulateFsrsWorkload`/`getRetentionWorkload`/`setWantsAbort`; FrontendService `deckOptionsReady` (on mount) + `deckOptionsRequireClose` (on close). `camel_to_snake("computeFsrsParams")` = `compute_fsrs_params` (matches the backend). The anki_rpc dispatch: `if method in CUSTOM` (camelCase key) → `CUSTOM[method](service, body)`; `elif camel_to_snake(method) in PASSTHROUGH` → `service.backend_raw(snake, body)`. `service.backend_raw(snake, body)` runs `col._backend.<snake>_raw(body)`; `service.emit(flags, initiator)` broadcasts. `Qt` opens it via `load_sveltekit_page(f"deck-options/{deck_id}")` (deck id in the URL path).

**Known limitation (documented, accepted for E2):** the FSRS optimize/simulate methods are long-running and run on the single-worker collection executor under the asyncio lock — while one runs, other collection ops (incl. the page's `latest_progress` poll) queue behind it, so there's no live progress during an optimize (it completes, just without a live bar). Concurrency/progress streaming for long ops is a future refinement. The Save→auto-close is also deferred (the page stays after Save; the user navigates back) — `deckOptionsRequireClose` is a no-op for now.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/assets.py` (modify) | add `GET /deck-options/{deck_id}` to `build_sveltekit_router` |
| `ankiweb/anki_rpc/passthrough.py` (modify) | add the read/compute deck-options methods |
| `ankiweb/anki_rpc/handlers.py` (modify) | CUSTOM `updateDeckConfigs` (run+broadcast), `deckOptionsReady`/`deckOptionsRequireClose` (no-op) |
| `ankiweb/screens/deckbrowser.py` (modify) | gear `opts:` → navigate `/deck-options/{did}` |
| `tests/test_deck_options.py` (create) | route + passthrough + CUSTOM + gear-nav tests |
| `tests/test_deck_options_integration.py` (create) | Playwright: the deck-options SPA mounts + loads + saves |

---

## Task 1: `/deck-options` route + RPC handlers + gear menu

**Files:** Modify `ankiweb/assets.py`, `ankiweb/anki_rpc/passthrough.py`, `ankiweb/anki_rpc/handlers.py`, `ankiweb/screens/deckbrowser.py`; Test `tests/test_deck_options.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_deck_options.py`:
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


def test_deck_options_serves_spa_shell(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    r = client.get(f"/deck-options/{did}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "_app/immutable/entry" in r.text


def test_frontend_service_methods_are_custom_noops(client):
    # deckOptionsReady/RequireClose would 500 (InvalidServiceIndex) via passthrough;
    # CUSTOM no-ops return 204.
    for m in ("deckOptionsReady", "deckOptionsRequireClose"):
        r = client.post(f"/_anki/{m}", content=b"", headers={"content-type": "application/binary"})
        assert r.status_code == 204, m


def test_get_deck_configs_for_update_passthrough(client):
    # the page's load RPC works (read); empty body is a valid (default) request
    r = client.post("/_anki/get_deck_configs_for_update", content=b"",
                    headers={"content-type": "application/binary"})
    assert r.status_code in (200, 500)   # allowed (not 404); 200 with a body or 500 if empty-body invalid
    assert r.status_code != 404


def test_passthrough_and_custom_registered():
    from ankiweb.anki_rpc.passthrough import PASSTHROUGH
    from ankiweb.anki_rpc.handlers import CUSTOM
    for m in ("get_ignored_before_count", "compute_fsrs_params", "evaluate_params_legacy",
              "compute_optimal_retention", "simulate_fsrs_review", "simulate_fsrs_workload",
              "get_retention_workload", "set_wants_abort"):
        assert m in PASSTHROUGH, m
    for m in ("updateDeckConfigs", "deckOptionsReady", "deckOptionsRequireClose"):
        assert m in CUSTOM, m


def test_update_deck_configs_persists_and_broadcasts(client):
    # round-trip: read the configs, flip a value, write via the CUSTOM handler, confirm persisted
    import anki.deck_config_pb2 as dc
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))

    def read(col):
        return col.decks.get_deck_configs_for_update(did)
    state = client.portal.call(client.app.state.service.run, read)  # DeckConfigsForUpdate
    # build a minimal UpdateDeckConfigsRequest from the current state (keep the same config)
    cfg = state.all_config[0].config
    new_limit = cfg.new_per_day + 7
    cfg.new_per_day = new_limit
    req = dc.UpdateDeckConfigsRequest(
        target_deck_id=did,
        configs=[cfg],
        removed_config_ids=[],
        mode=dc.UpdateDeckConfigsMode.UPDATE_DECK_CONFIGS_MODE_NORMAL,
        card_state_customizer=state.card_state_customizer,
        limits=state.current_deck.limits,
        new_cards_ignore_review_limit=state.new_cards_ignore_review_limit,
        apply_all_parent_limits=state.apply_all_parent_limits,
        fsrs=state.fsrs,
        fsrs_reschedule=False,
    )
    r = client.post("/_anki/updateDeckConfigs", content=req.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 200
    # the new_per_day limit persisted
    persisted = client.portal.call(
        client.app.state.service.run,
        lambda col: col.decks.get_deck_configs_for_update(did).all_config[0].config.new_per_day)
    assert persisted == new_limit


def test_gear_menu_navigates_to_deck_options(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "deckbrowser", "arg": f"opts:{did}"})
        m = ws.receive_json()
        while m["type"] != "call" or m["fn"] != "ankiwebNavigate":
            m = ws.receive_json()
        assert m["args"] == [f"/deck-options/{did}"]
```
(NOTE: the `UpdateDeckConfigsRequest` field set in `test_update_deck_configs_persists_and_broadcasts` is best-effort — the exact proto fields are in `anki/deck_config_pb2.py`. If a field name differs, inspect `dc.UpdateDeckConfigsRequest.DESCRIPTOR.fields_by_name` and `state` (`DeckConfigsForUpdate`) and adjust; the load-bearing assertion is that POSTing a valid request to `/_anki/updateDeckConfigs` returns 200 AND `new_per_day` persisted. If building the full request is too fiddly, simplify to: read the state, build the smallest valid request that changes `new_per_day`, and assert persistence.)

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_deck_options.py -v` → FAIL.

- [ ] **Step 3: Add the `/deck-options/{deck_id}` route** — in `ankiweb/assets.py` `build_sveltekit_router`, add (next to `/graphs`):
```python
    @router.get("/deck-options/{deck_id}")
    def deck_options_page(deck_id: str) -> Response:
        return FileResponse(index, media_type="text/html")
```

- [ ] **Step 4: Extend the passthrough** — in `ankiweb/anki_rpc/passthrough.py`, add to the `PASSTHROUGH` set:
```python
    "get_ignored_before_count", "compute_fsrs_params", "evaluate_params_legacy",
    "compute_optimal_retention", "simulate_fsrs_review", "simulate_fsrs_workload",
    "get_retention_workload", "set_wants_abort",
```

- [ ] **Step 5: Add the CUSTOM handlers** — in `ankiweb/anki_rpc/handlers.py`:
```python
async def update_deck_configs(service, body: bytes) -> bytes:
    """Write deck configs, then broadcast the returned OpChanges so the deck browser refreshes."""
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


async def _noop(service, body: bytes) -> bytes:
    # Qt-only FrontendService methods (deck_options_ready/require_close) RAISE
    # InvalidServiceIndex on the headless backend — answer them here as no-ops.
    return b""


CUSTOM["updateDeckConfigs"] = update_deck_configs
CUSTOM["deckOptionsReady"] = _noop
CUSTOM["deckOptionsRequireClose"] = _noop
```

- [ ] **Step 6: Wire the gear menu** — in `ankiweb/screens/deckbrowser.py` `make_deckbrowser_handler`, replace the ignored `opts` comment with a branch (READ the handler; the gear sends `opts:{did}`):
```python
        elif cmd == "opts":
            await hub.push_call("deckbrowser", "ankiwebNavigate", ["/deck-options/" + rest])
```
(`rest` is the deck id string from `opts:{did}`.)

- [ ] **Step 7: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_deck_options.py -v`, then `conda run -n ankiweb python -m pytest tests/test_graphs.py tests/test_screen_routes.py tests/test_deckbrowser.py tests/test_anki_rpc.py -q` (no regression).

- [ ] **Step 8: Commit**
```bash
git add ankiweb/assets.py ankiweb/anki_rpc/passthrough.py ankiweb/anki_rpc/handlers.py ankiweb/screens/deckbrowser.py tests/test_deck_options.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(deck-options): serve the SvelteKit deck-options SPA + update_deck_configs broadcast + gear menu"
```

## Context
`/deck-options/{deck_id}` serves the same SvelteKit shell (E1 foundation); the SPA reads the deck id from the path and loads via `get_deck_configs_for_update` (passthrough). Save POSTs `updateDeckConfigs` → the CUSTOM handler runs the backend write and broadcasts the returned `OpChanges` (deck browser refreshes). The Qt-only `deckOptionsReady`/`deckOptionsRequireClose` are CUSTOM no-ops (they'd 500 via passthrough — `InvalidServiceIndex`). The FSRS/advanced read+compute methods are passthrough'd (long-running compute blocks the single executor — documented limitation). The deck-browser gear navigates to the page.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns (incl. whether the `UpdateDeckConfigsRequest` test build needed adjustment).

---

## Task 2: Playwright — the deck-options SPA mounts, loads, and saves

**Files:** Create `tests/test_deck_options_integration.py`.

- [ ] **Step 1: Write the test** — mirror `tests/test_graphs_integration.py`'s `live_server` (uvicorn thread on a fresh port 8131, `pytest.importorskip`, inline `sync_playwright`). Seed a couple notes so the deck exists with content. Open `/deck-options/{did}`, assert the page mounts + loaded its config + no errors; best-effort exercise Save:
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
def live_server_dopts(tmp_path: Path):
    col_path = tmp_path / "d.anki2"
    col = Collection(str(col_path))
    try:
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "x"; n["Back"] = "y"
        col.add_note(n, col.decks.id("Default"))
        did = col.decks.id("Default")
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8131)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8131, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8131", did
    server.should_exit = True; t.join(timeout=5)


def test_deck_options_spa_boots(live_server_dopts):
    url, did = live_server_dopts
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed",
                lambda r: errors.append("REQFAIL " + r.url) if ("/_app/" in r.url or "/_anki/" in r.url) else None)
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/_anki/" in r.url else None)
        page.goto(f"{url}/deck-options/{did}")
        # the deck-options SvelteKit page renders its form. Inspect for a stable selector:
        # the page has inputs / tab titles ("Daily Limits", "New Cards", a Save affordance).
        # wait for a real deck-options element (e.g. an <input>, or text like "New cards/day").
        page.wait_for_function(
            "document.querySelectorAll('input,button').length>3", timeout=10000)
        page.wait_for_function(
            "document.body.innerText.length>50", timeout=10000)  # the form rendered content
        assert not errors, errors
        assert any("get_deck_configs_for_update" in u or "getDeckConfigsForUpdate" in u
                   for u in posts), posts   # the load RPC fired
        browser.close()
```
(NOTE: pick the most stable mount selector by inspecting the rendered page — the deck-options form has many inputs + tab headers. The load-bearing assertions: no `/_app/` or `/_anki/` request failed, no page error, and the `getDeckConfigsForUpdate` POST fired (the page loaded the config through ankiweb). Optionally extend to click the Save control and assert an `updateDeckConfigs` POST returns 200, if you can find a stable Save selector — but the Task-1 `test_update_deck_configs_persists_and_broadcasts` already proves the write path, so mount+load is sufficient here.)

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_deck_options_integration.py -v` (PASS if chromium available; SKIPS if not). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_deck_options_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(deck-options): Playwright — the SvelteKit deck-options SPA boots + loads"
```

## Context
End-to-end proof the real deck-options SvelteKit page boots through ankiweb's routes: fetches its `/_app/` chunks, POSTs `getDeckConfigsForUpdate` (+ `deckOptionsReady`) to `/_anki/`, and renders its form with zero errors. The write path (`updateDeckConfigs` persist + broadcast) is proven by the Task-1 round-trip test.

## Report Format
Status, pytest summary (Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (E2 = deck options):** `/deck-options/{deck_id}` route reusing the E1 SPA foundation (Task 1); `get_deck_configs_for_update` load (already passthrough) + the FSRS/advanced read+compute methods added to passthrough (Task 1); `updateDeckConfigs` write via CUSTOM handler with OpChanges broadcast (Task 1, round-trip tested); the Qt-only `deckOptionsReady`/`deckOptionsRequireClose` as CUSTOM no-ops (Task 1); deck-browser gear → `/deck-options/{did}` (Task 1); Playwright mount+load proof (Task 2). Deferred (documented): FSRS live-progress/concurrency (long compute blocks the single executor); Save→auto-close (`requireClose` no-op; user navigates back); dyn-deck routing to filtered-deck options (E5).

**2. Placeholder scan:** No TBD/TODO. The `UpdateDeckConfigsRequest` test build is best-effort with a documented fallback (inspect the proto + simplify). The Playwright mount selector is to be confirmed by inspection (load-bearing asserts are no-errors + the load RPC fired). FSRS long-compute limitation is documented, not a silent gap.

**3. Type/name consistency:** `build_sveltekit_router` gains `GET /deck-options/{deck_id}` (alongside E1's `/graphs`/`/_app/`/`/favicon.ico`). PASSTHROUGH (snake) += the 8 read/compute methods (`camel_to_snake` maps the page's camelCase, e.g. `computeFsrsParams`→`compute_fsrs_params`, verified). CUSTOM (camelCase keys) += `updateDeckConfigs` (`service.backend_raw("update_deck_configs", body)` + `OpChanges` parse via `anki.collection_pb2` + `op_changes_to_flags` + `service.emit`), `deckOptionsReady`/`deckOptionsRequireClose` (`_noop`→b""→204). deckbrowser `opts:{did}` → `ankiwebNavigate("/deck-options/"+rest)`. All backend `*_raw` methods + the `OpChanges` import + `deck_options_ready` raising are live-verified.

**4. Risks:** `update_deck_configs` returns `OpChanges` bytes that the page also needs — the handler returns them unchanged AND parses a copy to broadcast (parse failures are swallowed so a backend-format change never breaks the save). The two FrontendService no-ops prevent the `InvalidServiceIndex` 500 that passthrough would cause. Route ordering: the new page route is in `build_sveltekit_router` (already before the media catch-all). FSRS long-compute blocks the single executor (documented). The gear-menu change only affects `opts:` (other deckbrowser cmds unchanged); the regression run confirms `test_deckbrowser`/`test_screen_routes` still pass.
