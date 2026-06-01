# ankiweb Plan E1 — Statistics / Graphs (SvelteKit SPA serve foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve Anki's real compiled SvelteKit statistics page at `GET /graphs` — establishing the reusable SvelteKit-SPA serve foundation (the root `/_app/` asset route + the SPA page route) that E2/E3 (deck-options, change-notetype) build on — plus a "Stats" link from the deck browser.

**Architecture:** aqt 25.9.4 ships ONE SvelteKit SPA (already fully vendored at `web_assets/sveltekit/` — `index.html` + `_app/immutable/{entry,chunks,nodes,assets}`). The SPA's `index.html` imports `/_app/immutable/entry/start.*.mjs` at ABSOLUTE-root and client-routes by `location.pathname`; its data calls POST to `/_anki/<camelMethod>` (ankiweb's existing `anki_rpc` already serves these). ankiweb already serves these files under `/_anki/` (via `assets._resolve`/`_mime` + an SPA fallback), but the running SPA fetches them at ROOT `/_app/...` — which ankiweb serves nothing at. E1 adds a small **root** router: `GET /graphs` → the SPA shell `index.html`; `GET /_app/{path}` → the immutable assets (reusing `assets._resolve`/`_mime`); `GET /favicon.ico`. All registered BEFORE the media catch-all. Graphs is read-only — all its RPC methods (`graphs`, `get_graph_preferences`, `set_graph_preferences`, `i18n_resources`) are ALREADY in the passthrough; no bridge/close needed.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the vendored `web_assets/sveltekit/`, the existing `assets.py`/`anki_rpc`, pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is E1 of Sub-project E (the foundation + first specialized screen).** Spec: `docs/superpowers/specs/2026-06-01-ankiweb-browser-editor-design.md` does not cover E; design is in this plan + the recon. **A spike PROVED the graphs SPA boots + renders end-to-end** (`/tmp/graphs_spike.py`: 46 `/_app/` assets all 200, the `graphs`/`getGraphPreferences`/`i18nResources` POSTs all 200, 10 SVG charts rendered, zero page errors). Next: E2 (deck-options — reuses this foundation + adds `update_deck_configs` run_op + `deckOptionsReady`/`RequireClose` custom handlers), E3 (change-notetype), E4/E5 (custom-study / filtered-deck rebuilds), E6/E7 deferred (import/export, image-occlusion).

**Grounded facts (spike + code read):**
- `ankiweb/assets.py`: `_resolve(rel)` maps `_app/x`→`sveltekit/_app/x` and SvelteKit page names→`sveltekit/{rel}`; `_mime(path)` returns `application/javascript` for `.mjs`/`.js` (MANDATORY — `text/plain` HARD-fails the SPA's strict module-MIME check), `text/css`, etc. `build_router` serves `/_anki/{path}` + the SPA fallback + immutable `Cache-Control: max-age=31536000`. `build_media_router` is the LAST catch-all `GET /{path:path}`.
- The SPA's only absolute-root traffic is `/_app/...` (assets) + `/_anki/...` (RPC POSTs) + a lazy `/favicon.ico`. No fonts/other root prefixes. `.mjs` must be `application/javascript`.
- favicon is at `web_assets/imgs/favicon.ico` (NOT `web_assets/favicon.ico`); it's non-load-bearing (a 204 works).
- `#night` hash is optional (page renders in light mode without it).
- `create_app` (`ankiweb/app.py`) includes routers in order: assets (`/_anki/`), anki_rpc (`POST /_anki/{method}`), ws (`/ws`), screens (`build_screen_router`), media (LAST catch-all). The new SvelteKit router MUST be included BEFORE the media catch-all (route-ordering trap — else `/graphs` + `/_app/` get swallowed → 404).
- All graphs RPC methods are already in `PASSTHROUGH` (`graphs`, `get_graph_preferences`, `set_graph_preferences`, `i18n_resources`); `set_graph_preferences` writes a config pref returning no deck/card OpChanges → no broadcast needed.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/assets.py` (modify) | add `build_sveltekit_router(assets_dir)`: `GET /graphs`, `GET /_app/{path}`, `GET /favicon.ico` |
| `ankiweb/app.py` (modify) | include `build_sveltekit_router` before the media catch-all |
| `ankiweb/screens/deckbrowser.py` (modify) | add a "Stats" link → `/graphs` |
| `tests/test_graphs.py` (create) | TestClient route + RPC tests |
| `tests/test_graphs_integration.py` (create) | Playwright: the real graphs SPA boots + renders |

---

## Task 1: SvelteKit root router (`/graphs` + `/_app/` + favicon) + Stats link

**Files:** Modify `ankiweb/assets.py`, `ankiweb/app.py`, `ankiweb/screens/deckbrowser.py`; Test `tests/test_graphs.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_graphs.py`:
```python
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app

_APP = Path("ankiweb/web_assets/sveltekit/_app")


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_graphs_serves_spa_shell(client):
    r = client.get("/graphs")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "_app/immutable/entry" in r.text       # the SPA shell imports the entry


def test_app_asset_served_as_js_module_with_cache(client):
    entry = next(_APP.glob("immutable/entry/start.*.mjs"))   # glob the hashed name from disk
    rel = entry.relative_to(_APP).as_posix()                 # immutable/entry/start.<hash>.mjs
    r = client.get(f"/_app/{rel}")
    assert r.status_code == 200
    assert r.headers["content-type"] in ("application/javascript", "text/javascript")
    assert "max-age=31536000" in r.headers.get("cache-control", "")


def test_app_asset_css_served(client):
    css = next(_APP.glob("immutable/assets/*.css"))
    rel = css.relative_to(_APP).as_posix()
    r = client.get(f"/_app/{rel}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/css")


def test_app_asset_traversal_blocked(client):
    r = client.get("/_app/../../../etc/passwd")
    assert r.status_code in (403, 404)


def test_favicon(client):
    r = client.get("/favicon.ico")
    assert r.status_code in (200, 204)


def test_graphs_rpc_passthrough(client):
    # the graphs page POSTs protobuf to /_anki/<method>; get_graph_preferences takes an empty body
    r = client.post("/_anki/get_graph_preferences", content=b"",
                    headers={"content-type": "application/binary"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/binary")


def test_deckbrowser_has_stats_link(client):
    assert "/graphs" in client.get("/deckbrowser").text
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_graphs.py -v` → FAIL (`/graphs` + `/_app/` 404 via the media catch-all; no Stats link).

- [ ] **Step 3: Add `build_sveltekit_router` to `ankiweb/assets.py`** (reuse `_resolve`/`_mime`):
```python
from fastapi.responses import HTMLResponse


def build_sveltekit_router(assets_dir: Path) -> APIRouter:
    """Serve the vendored SvelteKit SPA at ROOT paths (the SPA's index.html imports
    /_app/... and client-routes by location.pathname). E2/E3 add more page routes here."""
    router = APIRouter()
    index = assets_dir / "sveltekit" / "index.html"

    @router.get("/graphs", response_class=HTMLResponse)
    def graphs_page() -> Response:
        return FileResponse(index, media_type="text/html")

    @router.get("/_app/{path:path}")
    def app_asset(path: str) -> Response:
        rel = _resolve("_app/" + path)                       # -> sveltekit/_app/<path>
        target = (assets_dir / rel).resolve()
        try:
            target.relative_to(assets_dir.resolve())
        except ValueError:
            return PlainTextResponse("forbidden", status_code=403)
        if not target.is_file():
            return PlainTextResponse("not found", status_code=404)
        headers = {"Cache-Control": "max-age=31536000"} if "immutable" in rel else {}
        return FileResponse(target, media_type=_mime(rel), headers=headers)

    @router.get("/favicon.ico")
    def favicon() -> Response:
        f = assets_dir / "imgs" / "favicon.ico"
        if f.is_file():
            return FileResponse(f, media_type="image/x-icon")
        return Response(status_code=204)

    return router
```

- [ ] **Step 4: Wire it into `ankiweb/app.py`** — import `build_sveltekit_router` and `include_router` it BEFORE the media catch-all. READ the router-include order in `create_app`; add the line right before `app.include_router(build_media_router(...))`:
```python
    app.include_router(build_sveltekit_router(settings.assets_dir))   # SvelteKit SPA at root
    app.include_router(build_media_router(lambda: app.state.service))  # GET /{path} — LAST
```
(Update the existing assets import line to also import `build_sveltekit_router`.)

- [ ] **Step 5: Add a "Stats" link in `ankiweb/screens/deckbrowser.py`** — in `render_deckbrowser_html`, add a plain link next to the "Create Deck" button (full-page navigation; no bridge needed):
```python
    create = ("<button onclick='ankiwebCreateDeck()'>Create Deck</button>"
              " <a href='/graphs'>Stats</a>")
```
(Match the existing `create = ...` line; keep the Create Deck button.)

- [ ] **Step 6: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_graphs.py -v`, then `conda run -n ankiweb python -m pytest tests/test_screen_routes.py tests/test_deckbrowser.py tests/test_assets_serving.py tests/test_media_serving.py -q` (no regression — the new root routes must not break the `/_anki/` or media serving).

- [ ] **Step 7: Commit**
```bash
git add ankiweb/assets.py ankiweb/app.py ankiweb/screens/deckbrowser.py tests/test_graphs.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(graphs): serve the SvelteKit /graphs SPA (root /_app/ + /graphs + favicon)"
```

## Context
`build_sveltekit_router` serves the vendored SvelteKit SPA at the ROOT paths the bundle actually fetches: `/graphs` → the shared `index.html` shell (the client router takes over), `/_app/{path}` → the immutable chunks/nodes/css (via the existing `_resolve`/`_mime`, `.mjs`=`application/javascript`, immutable cache), `/favicon.ico` → `imgs/favicon.ico` or 204. Registered before the media catch-all so they aren't swallowed. The graphs page's backend POSTs (`graphs`/`get_graph_preferences`/`i18n_resources`) already route through the existing `anki_rpc` passthrough. A plain `<a href='/graphs'>` from the deck browser opens it. This router is the foundation E2/E3 extend with `/deck-options/{id}` and `/change-notetype/{ids}`.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 2: Playwright — the real graphs SPA boots + renders

**Files:** Create `tests/test_graphs_integration.py`.

- [ ] **Step 1: Write the test** — mirror `tests/test_reviewer_integration.py`'s `live_server` (uvicorn thread on a fresh port, `pytest.importorskip("playwright.sync_api")`, inline `sync_playwright`). Seed a few notes + answer one so the graphs have data:
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
def live_server_graphs(tmp_path: Path):
    col_path = tmp_path / "g.anki2"
    col = Collection(str(col_path))
    try:
        for q in ("a", "b", "c"):
            n = col.new_note(col.models.by_name("Basic")); n["Front"] = q; n["Back"] = q
            col.add_note(n, col.decks.id("Default"))
        from anki.scheduler.v3 import CardAnswer
        queued = col.sched.get_queued_cards(fetch_limit=1)
        if queued.cards:
            top = queued.cards[0]; c = col.get_card(top.card.id); c.start_timer()
            ans = col.sched.build_answer(card=c, states=top.states, rating=CardAnswer.Rating.GOOD)
            col.sched.answer_card(ans)
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8130)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8130, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8130"
    server.should_exit = True; t.join(timeout=5)


def test_graphs_spa_boots(live_server_graphs):
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed",
                lambda r: errors.append("REQFAIL " + r.url) if ("/_app/" in r.url or "/_anki/" in r.url) else None)
        page.goto(f"{live_server_graphs}/graphs")
        # the real graphs SvelteKit page renders its container + at least one svg chart
        page.wait_for_selector(".graphs-container", timeout=10000)
        page.wait_for_function(
            "document.querySelectorAll('.graphs-container svg').length>=1", timeout=10000)
        assert not errors, errors
        browser.close()
```
(If `.graphs-container` is not the exact selector in this bundle, the spike `/tmp/graphs_spike.py` confirmed `.graphs-container` + `.graphs-container svg` work; adjust only if needed. The load-bearing assertions: the SPA renders a graph AND no `/_app/` or `/_anki/` request failed AND no page error.)

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_graphs_integration.py -v` (PASS if chromium available; SKIPS if not). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_graphs_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(graphs): Playwright — the real SvelteKit graphs SPA boots + renders"
```

## Context
End-to-end proof that the real 25.9.4 graphs SPA boots through ankiweb's routes: fetches its `/_app/` chunks (as JS modules), POSTs `graphs`/`getGraphPreferences`/`i18nResources` to `/_anki/`, and renders the charts — with zero page errors and no failed asset/RPC requests. This is the exact de-risking pattern used for the reviewer and editor, and it validates the SPA-serve foundation E2/E3 reuse.

## Report Format
Status, pytest summary (Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (E1 = graphs + SPA foundation):** `GET /graphs` serves the SvelteKit shell (Task 1); `GET /_app/{path}` serves the immutable assets at root (Task 1 — the load-bearing gap); `GET /favicon.ico` (Task 1); a Stats link from the deck browser (Task 1); the graphs RPC methods already pass through (verified); Playwright boot+render proof (Task 2). Deferred to E2+: deck-options/change-notetype (write RPCs + close bridge), custom-study/filtered-deck (rebuilds), import/export + image-occlusion (later).

**2. Placeholder scan:** No TBD/TODO. The `/_app/` route reuses `_resolve`/`_mime` (no duplicated logic). The Playwright test SKIPS cleanly without playwright. favicon → 204 if the file is absent (non-load-bearing). The fetch_web_assets REQUIRED-list hardening (assert the `sveltekit/_app` dirs) is a noted minor follow-up, not blocking.

**3. Type/name consistency:** `build_sveltekit_router(assets_dir)` in `assets.py` (reuses `_resolve`/`_mime`/`FileResponse`/`PlainTextResponse`); `create_app` includes it before `build_media_router`. Routes: `GET /graphs`→`sveltekit/index.html`, `GET /_app/{path}`→`_resolve("_app/"+path)` (immutable cache), `GET /favicon.ico`→`imgs/favicon.ico`|204. The deck browser link is a plain `<a href='/graphs'>`. The graphs RPC methods (`graphs`/`get_graph_preferences`/`set_graph_preferences`/`i18n_resources`) are all already in `PASSTHROUGH` — NO `anki_rpc`/passthrough change. `.mjs`→`application/javascript` (already in the MIME map).

**4. Risks:** route ordering — the SvelteKit router MUST precede the media catch-all (Task 1 Step 4 + the regression run in Step 6 verify `/graphs` and `/_app/` resolve correctly and the existing `/_anki/`+media serving still works). Strict module MIME — `.mjs` must be `application/javascript` (already mapped; the Task-2 `requestfailed` listener + boot assertion would catch a regression loudly). The page is whole-collection (no URL param), so no parameterization risk. `set_graph_preferences` writes a pref but returns no deck/card OpChanges → no broadcast wiring needed. The existing `/_anki/sveltekit/` fallback in `assets.py` is unaffected (the SPA uses root `/_app/`, not `/_anki/sveltekit/_app/`).
