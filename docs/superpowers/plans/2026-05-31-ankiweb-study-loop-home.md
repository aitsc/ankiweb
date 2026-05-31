# ankiweb Study Loop — Home & Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the navigable "home" of ankiweb's study loop — a server-rendered Deck Browser (deck tree + live due counts) and deck Overview (counts + Study Now), reusing Anki's real `deckbrowser.css`/`overview.css`, wired through the Foundation's WebSocket bridge, with cross-screen refresh via the OpChanges bus and a server-rendered Congrats screen.

**Architecture:** Each screen is a full HTML page served by FastAPI: it sets `window.__ankiwebContext`, links the screen's vendored CSS, and loads the Foundation's `bootstrap.js` (which defines `window.pycmd` over a WebSocket under that context). The page body is a server-rendered fragment built from `col.sched.deck_due_tree()` / `col.sched.counts()`. Bridge command handlers (registered per-context on the `BridgeHub`) run collection ops via a new `CollectionService.run_op` (which converts the returned `OpChanges` to a flags dict and `emit`s it on the bus), then push `ankiwebNavigate(url)` / `ankiwebReload()` calls to drive the browser. Other connected screens reload when a relevant OpChanges broadcast arrives (initiator-filtered).

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, FastAPI, the Foundation modules (`collection_service`, `bridge`, `assets`, shell `bootstrap.ts`/esbuild), pytest, Playwright.

**This is Plan 2 of 3 for Study Loop C.** Plan 3 (the Reviewer) follows. Spec: `docs/superpowers/specs/2026-05-31-ankiweb-foundation-study-loop-design.md` (§6.1 Deck Browser, §6.2 Overview, §6.4 Congrats). Run everything in the `ankiweb` conda env (e.g. `conda run -n ankiweb pytest`).

**Deliberate deferrals (NOT defects), to later plans:** deck drag-drop reparent + the gear "opts" context menu (Plan E / polish); the real SvelteKit congrats page (Plan E builds the shared SvelteKit-serving infra — Plan 2 renders a simple server-side congrats); full i18n (screens use plain English labels; the SvelteKit pages already i18n via `i18nResources`); the actual Reviewer screen (Plan 3 — Plan 2 serves a placeholder so "Study Now" doesn't 404); the overview **buried ±N** count annotation (§6.2 — needs `deck_due_tree(current_id)` buried-difference; Plan 2 shows raw `counts()` + the Unbury button); the overview `http*` external-link command and deck-browser shift-click `select` wiring (neither fragment emits these yet — the `select` handler branch is kept for when the renderer wires shift-click).

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/collection_service.py` (modify) | Add `op_changes_to_flags()` + `CollectionService.run_op()` (run a mutating op → emit flags on the bus) |
| `ankiweb/screens/__init__.py` (create) | Package marker |
| `ankiweb/screens/page.py` (create) | `render_page(context, body, css_files)` — wrap a fragment in a full shell HTML doc |
| `ankiweb/screens/deckbrowser.py` (create) | `render_deckbrowser_html(col)` + `make_deckbrowser_handler(service, hub)` |
| `ankiweb/screens/overview.py` (create) | `render_overview_html(col)` + `make_overview_handler(service, hub)` |
| `ankiweb/screens/congrats.py` (create) | `render_congrats_html(col)` (server-rendered finished screen) |
| `ankiweb/screens/routes.py` (create) | `build_screen_router(get_service)` (GET screen pages) + `register_screen_handlers(service, hub)` |
| `ankiweb/app.py` (modify) | Include screen router (before media catch-all); call `register_screen_handlers` in lifespan |
| `shell_src/bootstrap.ts` (modify) | Context from `__ankiwebContext`; register `ankiwebNavigate`/`ankiwebReload`; reload on relevant opchanges (initiator-filtered) |
| `tests/test_*` | Per-component tests |

---

## Task 1: `run_op` — convert OpChanges to flags and emit on the bus

**Files:**
- Modify: `ankiweb/collection_service.py`
- Test: `tests/test_collection_service.py` (append)

- [ ] **Step 1: Write the failing tests (append)**

```python
def test_op_changes_to_flags():
    from ankiweb.collection_service import op_changes_to_flags
    from anki.collection import Collection
    import tempfile, os
    col = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))
    try:
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "x"
        res = col.add_note(n, col.decks.id("Default"))  # OpChangesWithCount
        flags = op_changes_to_flags(res.changes)
        assert flags["note"] is True
        assert flags["card"] is True
        assert isinstance(flags.get("study_queues"), bool)
    finally:
        col.close()


async def test_run_op_emits_flags(service):
    seen = []
    service.subscribe(lambda flags, initiator: seen.append((flags, initiator)))

    def add(col):
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "y"
        return col.add_note(n, col.decks.id("Default"))

    res = await service.run_op(add, initiator="deckbrowser")
    assert res.count == 1                      # OpChangesWithCount passthrough return
    assert len(seen) == 1
    flags, initiator = seen[0]
    assert initiator == "deckbrowser"
    assert flags["note"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_collection_service.py -k "op_changes or run_op" -v`
Expected: FAIL (`ImportError: cannot import name 'op_changes_to_flags'`).

- [ ] **Step 3: Implement**

Add to `ankiweb/collection_service.py` (module-level, after imports):
```python
from google.protobuf.descriptor import FieldDescriptor


def op_changes_to_flags(changes) -> dict:
    """Convert an OpChanges proto into a {field_name: bool} dict (only its bool fields)."""
    return {
        f.name: getattr(changes, f.name)
        for f in changes.DESCRIPTOR.fields
        if f.type == FieldDescriptor.TYPE_BOOL
    }
```
Add this method to `CollectionService` (after `run`):
```python
    async def run_op(self, fn: Callable[[Collection], T], initiator: str | None = None) -> T:
        """Run a mutating op (fn returns OpChanges or an OpChanges* wrapper), then
        broadcast the change flags on the bus. Returns the op result unchanged."""
        result = await self.run(fn)
        changes = getattr(result, "changes", result)
        flags = op_changes_to_flags(changes)
        if any(flags.values()):  # skip no-op broadcasts (e.g. set_current returns all-False)
            await self.emit(flags, initiator)
        return result
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_collection_service.py -v`
Expected: PASS (all collection_service tests).

- [ ] **Step 5: Commit**

```bash
git add ankiweb/collection_service.py tests/test_collection_service.py
git commit -m "feat: CollectionService.run_op — emit OpChanges flags on the bus"
```

---

## Task 2: Shell — path-derived context, navigate/reload globals, opchanges reload

**Files:**
- Modify: `shell_src/bootstrap.ts`
- Rebuild: `npm run build`
- Test: `tests/test_shell_build.py` (append an assertion)

- [ ] **Step 1: Replace `shell_src/bootstrap.ts`**

```ts
import { Bridge } from "./pycmd_shim";

// Context resolution order: explicit page global, then ?context= (the spike), then "default".
const ctx =
  (window as any).__ankiwebContext ||
  new URLSearchParams(location.search).get("context") ||
  "default";

const bridge = new Bridge(ctx);
(window as any).__ankiwebBridge = bridge;

// Server-invokable navigation/reload helpers (called via {type:"call"}).
bridge.registerCalls({
  ankiwebNavigate: (url: unknown) => {
    location.href = String(url);
  },
  ankiwebReload: () => {
    location.reload();
  },
});

// Client-side helper for the "Create Deck" button (prompt then send create:<name>).
(window as any).ankiwebCreateDeck = () => {
  const name = window.prompt("Deck name:");
  if (name) (window as any).pycmd("create:" + name);
};

// Cross-screen refresh: reload when another screen's op changed our data.
// Skip our own changes (initiator === ctx) — self-initiated refreshes use ankiwebReload.
window.addEventListener("anki-opchanges", (e: Event) => {
  const detail = (e as CustomEvent).detail;
  const flags = detail.flags || {};
  if (detail.initiator !== ctx && (flags.study_queues || flags.deck || flags.card || flags.note)) {
    location.reload();
  }
});

// Night-mode hash convention.
if (location.hash.includes("night")) {
  document.documentElement.classList.add("night-mode");
  document.documentElement.setAttribute("data-bs-theme", "dark");
}

window.addEventListener("load", () => bridge.ready());
```

- [ ] **Step 2: Rebuild + extend the build test**

Run: `npm run build`
Expected: `built ankiweb/shell/static/bootstrap.js`.

Append to `tests/test_shell_build.py`:
```python
def test_shell_bundle_has_nav_helpers():
    out = Path(__file__).resolve().parent.parent / "ankiweb/shell/static/bootstrap.js"
    data = out.read_bytes()
    assert b"ankiwebNavigate" in data
    assert b"anki-opchanges" in data
```

- [ ] **Step 3: Run the build test**

Run: `conda run -n ankiweb python -m pytest tests/test_shell_build.py -v`
Expected: PASS (both tests).

- [ ] **Step 4: Commit**

```bash
git add shell_src/bootstrap.ts tests/test_shell_build.py
git commit -m "feat: shell context-from-page + navigate/reload + opchanges reload"
```

> Note: do NOT commit `ankiweb/shell/static/` (gitignored). The build runs as part of setup.

---

## Task 3: Page wrapper

**Files:**
- Create: `ankiweb/screens/__init__.py`, `ankiweb/screens/page.py`
- Test: `tests/test_screens_page.py`

- [ ] **Step 1: Write the failing test**

`tests/test_screens_page.py`:
```python
from ankiweb.screens.page import render_page


def test_render_page_structure():
    html = render_page("deckbrowser", "<div id=body>hi</div>", ["css/deckbrowser.css"])
    assert "<!doctype html>" in html.lower()
    assert 'window.__ankiwebContext="deckbrowser"' in html
    assert '/_anki/css/deckbrowser.css' in html
    assert '/shell/static/bootstrap.js' in html
    assert "<div id=body>hi</div>" in html
    # context script must come before the bootstrap script so the Bridge picks it up
    assert html.index("__ankiwebContext") < html.index("bootstrap.js")
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_screens_page.py -v`
Expected: FAIL (`ModuleNotFoundError: ankiweb.screens.page`).

- [ ] **Step 3: Implement**

`ankiweb/screens/__init__.py`:
```python
```
(empty)

`ankiweb/screens/page.py`:
```python
from __future__ import annotations
from typing import Sequence


def render_page(context: str, body: str, css_files: Sequence[str] = ()) -> str:
    """Wrap a server-rendered fragment in a full shell HTML document.

    Sets window.__ankiwebContext BEFORE loading bootstrap.js so the Bridge connects
    to /ws?context=<context>. Links the given vendored CSS (paths relative to /_anki/).
    """
    links = "".join(
        f'<link rel="stylesheet" href="/_anki/{c}">' for c in css_files
    )
    return (
        "<!doctype html>\n"
        '<html><head><meta charset="utf-8">'
        f'<script>window.__ankiwebContext="{context}"</script>'
        f"{links}"
        '<script src="/shell/static/bootstrap.js"></script>'
        "</head>"
        f"<body>{body}</body></html>"
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_screens_page.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ankiweb/screens/__init__.py ankiweb/screens/page.py tests/test_screens_page.py
git commit -m "feat: screens.page — shell HTML page wrapper"
```

---

## Task 4: Deck Browser HTML generator

**Files:**
- Create: `ankiweb/screens/deckbrowser.py`
- Test: `tests/test_deckbrowser.py`

- [ ] **Step 1: Write the failing test**

`tests/test_deckbrowser.py`:
```python
import tempfile, os
import pytest
from anki.collection import Collection
from anki.decks import DeckCollapseScope
from ankiweb.screens.deckbrowser import render_deckbrowser_html


@pytest.fixture
def col():
    c = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))
    yield c
    c.close()


def test_renders_default_deck_with_counts(col):
    # add one new card to the Default deck
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"
    col.add_note(n, col.decks.id("Default"))
    html = render_deckbrowser_html(col)
    assert "Default" in html
    # the Default deck row carries its deck id and the deck CSS class
    did = col.decks.id("Default")
    assert f"id='{did}'" in html or f'id="{did}"' in html
    assert "class='deck" in html or 'class="deck' in html
    # a new-count span exists (one new card)
    assert "new-count" in html
    assert "studiedToday" in html
    # open command wired
    assert f'pycmd(\'open:{did}\')' in html or f'open:{did}' in html


def test_subdeck_indented_and_nested(col):
    pid = col.decks.id("Parent")
    col.decks.id("Parent::Child")
    # newly-created parent decks default to collapsed=True (children hidden), like Anki;
    # expand it so the child row is rendered.
    col.decks.set_collapsed(pid, False, DeckCollapseScope.REVIEWER)
    html = render_deckbrowser_html(col)
    assert "Parent" in html and "Child" in html
    # child name is leaf-only
    assert ">Child<" in html
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_deckbrowser.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`ankiweb/screens/deckbrowser.py`:
```python
from __future__ import annotations
import html


def _count_span(n: int, cls: str) -> str:
    return f"<span class='{cls}'>{n}</span>" if n else "<span class='zero-count'>0</span>"


def _render_node(node, current_id: int, out: list) -> None:
    indent = "&nbsp;" * 6 * (node.level - 1)
    row_class = "deck current" if node.deck_id == current_id else "deck"
    if node.children:
        prefix = "+" if node.collapsed else "−"  # − minus sign
        collapse = (f"<a class='collapse' href='#' "
                    f"onclick='return pycmd(\"collapse:{node.deck_id}\")'>{prefix}</a>")
    else:
        collapse = "<span class='collapse'></span>"
    filtered = " filtered" if node.filtered else ""
    name = (f"<a class='deck{filtered}' href='#' "
            f"onclick=\"return pycmd('open:{node.deck_id}')\">{html.escape(node.name)}</a>")
    gears = (f"<a class='opts' href='#' onclick='return pycmd(\"opts:{node.deck_id}\")'>"
             f"<img src='/_anki/imgs/gears.svg' class='gears'></a>")
    out.append(
        f"<tr class='{row_class}' id='{node.deck_id}'>"
        f"<td class='decktd'>{indent}{collapse}{name}</td>"
        f"<td align='right' class='count'>{_count_span(node.new_count, 'new-count')}</td>"
        f"<td align='right' class='count'>{_count_span(node.learn_count, 'learn-count')}</td>"
        f"<td align='right' class='count'>{_count_span(node.review_count, 'review-count')}</td>"
        f"<td align='center' class='opts'>{gears}</td>"
        f"</tr>"
    )
    if not node.collapsed:
        for child in node.children:
            _render_node(child, current_id, out)


def render_deckbrowser_html(col) -> str:
    tree = col.sched.deck_due_tree()
    current_id = col.decks.get_current_id()
    rows = [
        "<tr><th colspan='1' align='left'>Decks</th>"
        "<th class='count'>New</th><th class='count'>Learn</th><th class='count'>Due</th>"
        "<th></th></tr>"
    ]
    if tree is not None:
        for child in tree.children:
            _render_node(child, current_id, rows)
    table = "<table cellspacing='0' cellpadding='3' class='decks'>" + "".join(rows) + "</table>"
    studied = f"<div id='studiedToday'><span>{html.escape(col.studied_today())}</span></div>"
    create = "<button onclick='ankiwebCreateDeck()'>Create Deck</button>"
    return f"<center>{table}{studied}<div class='dyn-buttons'>{create}</div></center>"
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_deckbrowser.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ankiweb/screens/deckbrowser.py tests/test_deckbrowser.py
git commit -m "feat: deck browser HTML generator (deck tree + counts)"
```

> Fidelity reference: `qt/aqt/deckbrowser.py:233-301` (`_render_deck_node`). We reuse `css/deckbrowser.css`, which targets `.deck`, `.deck.current`, `.collapse`, `.gears`, `.new-count`/`.learn-count`/`.review-count`/`.zero-count`, `#studiedToday`.

---

## Task 5: Deck Browser handler + screen routes + app wiring

**Files:**
- Create: `ankiweb/screens/routes.py`
- Modify: `ankiweb/screens/deckbrowser.py` (add handler), `ankiweb/app.py`
- Test: `tests/test_screen_routes.py`

- [ ] **Step 1: Write the failing test**

`tests/test_screen_routes.py`:
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
        # seed a card so the deck browser has content
        c.portal.call(c.app.state.service.run, _seed)
        yield c


def _seed(col):
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"
    col.add_note(n, col.decks.id("Default"))


def test_root_serves_deckbrowser(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Default" in r.text
    assert 'window.__ankiwebContext="deckbrowser"' in r.text
    assert "/_anki/css/deckbrowser.css" in r.text


def test_deckbrowser_route(client):
    r = client.get("/deckbrowser")
    assert r.status_code == 200
    assert "studiedToday" in r.text


def test_open_command_sets_current_and_navigates(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "deckbrowser", "arg": f"open:{did}"})
        # A run_op-backed command may also broadcast an {type:opchanges} frame; drain
        # until the navigate call (set_current is all-False so usually no opchanges frame,
        # but this is robust for any run_op-backed command).
        msg = ws.receive_json()
        while msg["type"] != "call":
            msg = ws.receive_json()
        assert msg["fn"] == "ankiwebNavigate"
        assert msg["args"] == ["/overview"]
    # current deck is now Default
    cur = client.portal.call(client.app.state.service.run, lambda col: col.decks.get_current_id())
    assert cur == did
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_screen_routes.py -v`
Expected: FAIL (routes/handler not present).

- [ ] **Step 3: Add the deck browser handler**

Append to `ankiweb/screens/deckbrowser.py`:
```python
def make_deckbrowser_handler(service, hub):
    """Returns an async bridge handler(arg) for the 'deckbrowser' context."""
    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "open" or cmd == "select":
            did = int(rest)
            await service.run_op(lambda col: col.decks.set_current(did), initiator="deckbrowser")
            if cmd == "open":
                await hub.push_call("deckbrowser", "ankiwebNavigate", ["/overview"])
            else:
                await hub.push_call("deckbrowser", "ankiwebReload", [])
        elif cmd == "collapse":
            did = int(rest)

            def toggle(col):
                from anki.decks import DeckCollapseScope
                # Read persisted state from the deck dict, NOT the due-tree node:
                # deck_due_tree() prunes empty decks, so a node may be missing.
                collapsed = bool(col.decks.get(did).get("collapsed", False))
                return col.decks.set_collapsed(did, not collapsed, DeckCollapseScope.REVIEWER)

            await service.run_op(toggle, initiator="deckbrowser")
            await hub.push_call("deckbrowser", "ankiwebReload", [])
        elif cmd == "create":
            name = rest.strip()
            if name:
                await service.run_op(
                    lambda col: col.decks.add_normal_deck_with_name(name),
                    initiator="deckbrowser",
                )
                await hub.push_call("deckbrowser", "ankiwebReload", [])
        # 'opts' (gear menu) is deferred to a later plan; ignore for now.
        return None

    return handler
```

- [ ] **Step 4: Create the screen router + handler registration**

`ankiweb/screens/routes.py`:
```python
from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from ankiweb.screens.page import render_page
from ankiweb.screens.deckbrowser import render_deckbrowser_html, make_deckbrowser_handler


def build_screen_router(get_service) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    @router.get("/deckbrowser", response_class=HTMLResponse)
    async def deckbrowser_page():
        service = get_service()
        body = await service.run(render_deckbrowser_html)
        return HTMLResponse(render_page("deckbrowser", body, ["css/deckbrowser.css"]))

    return router


def register_screen_handlers(service, hub) -> None:
    hub.set_handler("deckbrowser", make_deckbrowser_handler(service, hub))
```

- [ ] **Step 5: Wire into app**

In `ankiweb/app.py`:
1. Add import near the others: `from ankiweb.screens.routes import build_screen_router, register_screen_handlers`.
2. In the lifespan, after `app.state.hub = hub`, add: `register_screen_handlers(service, hub)`.
3. Register the screen router **before** the media catch-all (place the line just above the `build_media_router` include):
```python
    app.include_router(build_screen_router(lambda: app.state.service))  # GET / and /deckbrowser
```

- [ ] **Step 6: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_screen_routes.py -v`
Expected: PASS (3 tests). Also run the full suite: `conda run -n ankiweb python -m pytest -q` (no regressions; route order intact).

- [ ] **Step 7: Commit**

```bash
git add ankiweb/screens/deckbrowser.py ankiweb/screens/routes.py ankiweb/app.py tests/test_screen_routes.py
git commit -m "feat: deck browser page route + bridge handler (open/collapse/create)"
```

---

## Task 6: Overview HTML generator (+ finished→congrats)

**Files:**
- Create: `ankiweb/screens/overview.py`, `ankiweb/screens/congrats.py`
- Test: `tests/test_overview.py`

- [ ] **Step 1: Write the failing test**

`tests/test_overview.py`:
```python
import tempfile, os
import pytest
from anki.collection import Collection
from ankiweb.screens.overview import render_overview_html
from ankiweb.screens.congrats import render_congrats_html


@pytest.fixture
def col():
    c = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))
    yield c
    c.close()


def test_overview_shows_counts_and_study_button(col):
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"
    col.add_note(n, col.decks.id("Default"))
    col.decks.set_current(col.decks.id("Default"))
    html = render_overview_html(col)
    assert "Default" in html               # deck name heading
    assert "Study Now" in html
    assert 'pycmd(\'study\')' in html or "study" in html
    assert "new-count" in html             # one new card shown


def test_overview_finished_shows_congrats(col):
    # empty Default deck → finished → congrats
    col.decks.set_current(col.decks.id("Default"))
    html = render_overview_html(col)
    assert "Congratulations" in html or "congrats" in html.lower()


def test_congrats_fragment(col):
    html = render_congrats_html(col)
    assert "Congratulations" in html
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_overview.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement congrats**

`ankiweb/screens/congrats.py`:
```python
from __future__ import annotations
import html


def render_congrats_html(col) -> str:
    """Simple server-rendered finished screen (the real SvelteKit congrats is a later plan)."""
    info = col.sched.congratulations_info()
    lines = ["<h1>Congratulations!</h1>",
             "<p>You have finished this deck for now.</p>"]
    if info.learn_remaining:
        mins = max(1, info.secs_until_next_learn // 60)
        lines.append(f"<p>The next learning card will be ready in {mins} minute(s).</p>")
    if info.have_user_buried or info.have_sched_buried:
        lines.append("<p><button onclick='pycmd(\"unbury\")'>Unbury</button> "
                     "buried cards.</p>")
    back = "<p><button onclick='pycmd(\"decks\")'>Back to Decks</button></p>"
    return "<center class='congrats'>" + "".join(lines) + back + "</center>"
```

- [ ] **Step 4: Implement overview**

`ankiweb/screens/overview.py`:
```python
from __future__ import annotations
import html
from ankiweb.screens.congrats import render_congrats_html


def _number_cell(n: int, cls: str) -> str:
    return f"<td align='center'><span class='{cls}'>{n}</span></td>"


def render_overview_html(col) -> str:
    deck = col.decks.current()
    new, learn, review = col.sched.counts()
    if new + learn + review == 0:
        # Nothing queued (counts already reflect limits/buried) → finished. Public-API
        # alternative to the private col.sched._is_finished().
        return render_congrats_html(col)

    name = html.escape(deck["name"])

    desc = ""
    raw = deck.get("desc", "")
    if raw:
        rendered = col.render_markdown(raw) if deck.get("md") else html.escape(raw)
        desc = f"<div class='descfont descmid description'>{rendered}</div>"

    table = (
        "<table cellspacing='0' cellpadding='5' class='overview-counts'><tr>"
        "<th>New</th><th>Learning</th><th>To Review</th></tr><tr>"
        f"{_number_cell(new, 'new-count')}"
        f"{_number_cell(learn, 'learn-count')}"
        f"{_number_cell(review, 'review-count')}"
        "</tr></table>"
    )
    study = ("<button id='study' class='but' autofocus "
             "onclick=\"pycmd('study');return false;\">Study Now</button>")

    bottom = ["<button onclick='pycmd(\"opts\")'>Options</button>"]
    if deck.get("dyn"):
        bottom.append("<button onclick='pycmd(\"refresh\")'>Rebuild</button>")
        bottom.append("<button onclick='pycmd(\"empty\")'>Empty</button>")
    else:
        bottom.append("<button onclick='pycmd(\"studymore\")'>Custom Study</button>")
    if col.sched.have_buried():
        bottom.append("<button onclick='pycmd(\"unbury\")'>Unbury</button>")
    bottom.append("<button onclick='pycmd(\"decks\")'>Decks</button>")

    return (
        f"<center><h3>{name}</h3>{desc}{table}"
        f"<div class='studybtn'>{study}</div>"
        f"<div class='bottom-buttons'>{''.join(bottom)}</div></center>"
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_overview.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add ankiweb/screens/overview.py ankiweb/screens/congrats.py tests/test_overview.py
git commit -m "feat: overview + server-rendered congrats generators"
```

> Fidelity reference: `qt/aqt/overview.py` (`_table`/`_desc`/`_renderBottom`), `congratulations_info()` proto (`learn_remaining/secs_until_next_learn/have_user_buried/have_sched_buried`). Reuses `css/overview.css`.

---

## Task 7: Overview route + handler

**Files:**
- Modify: `ankiweb/screens/overview.py` (add handler), `ankiweb/screens/routes.py`
- Test: `tests/test_screen_routes.py` (append)

- [ ] **Step 1: Write the failing test (append to tests/test_screen_routes.py)**

```python
def test_overview_route(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    r = client.get("/overview")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="overview"' in r.text
    assert "/_anki/css/overview.css" in r.text


def test_overview_study_navigates_to_reviewer(client):
    with client.websocket_connect("/ws?context=overview") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "overview", "arg": "study"})
        msg = ws.receive_json()
        assert msg["type"] == "call"
        assert msg["fn"] == "ankiwebNavigate"
        assert msg["args"] == ["/reviewer"]


def test_overview_decks_navigates_home(client):
    with client.websocket_connect("/ws?context=overview") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "overview", "arg": "decks"})
        msg = ws.receive_json()
        assert msg["fn"] == "ankiwebNavigate"
        assert msg["args"] == ["/deckbrowser"]
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_screen_routes.py -k overview -v`
Expected: FAIL (no /overview route, no handler).

- [ ] **Step 3: Add overview handler**

Append to `ankiweb/screens/overview.py`:
```python
def make_overview_handler(service, hub):
    async def handler(arg: str):
        if arg == "study":
            await service.run(lambda col: col.startTimebox())
            await hub.push_call("overview", "ankiwebNavigate", ["/reviewer"])
        elif arg == "decks":
            await hub.push_call("overview", "ankiwebNavigate", ["/deckbrowser"])
        elif arg == "unbury":
            def unbury(col):
                from anki.scheduler.base import UnburyDeck
                return col.sched.unbury_deck(col.decks.get_current_id(), UnburyDeck.Mode.ALL)
            await service.run_op(unbury, initiator="overview")
            await hub.push_call("overview", "ankiwebReload", [])
        elif arg in ("refresh", "empty"):
            did = await service.run(lambda col: col.decks.get_current_id())
            is_dyn = await service.run(lambda col: bool(col.decks.get(did).get("dyn")))
            if is_dyn:  # rebuild/empty raise FilteredDeckError on a normal deck
                if arg == "refresh":
                    await service.run_op(lambda col: col.sched.rebuild_filtered_deck(did),
                                         initiator="overview")
                else:
                    await service.run_op(lambda col: col.sched.empty_filtered_deck(did),
                                         initiator="overview")
                await hub.push_call("overview", "ankiwebReload", [])
        # 'opts' (deck options), 'studymore' (custom study), 'description' deferred to later plans.
        return None

    return handler
```

- [ ] **Step 4: Add overview route + register handler**

In `ankiweb/screens/routes.py`:
1. Imports: `from ankiweb.screens.overview import render_overview_html, make_overview_handler`.
2. Add inside `build_screen_router` (before `return router`):
```python
    @router.get("/overview", response_class=HTMLResponse)
    async def overview_page():
        service = get_service()
        body = await service.run(render_overview_html)
        return HTMLResponse(render_page("overview", body, ["css/overview.css"]))
```
3. In `register_screen_handlers`, add: `hub.set_handler("overview", make_overview_handler(service, hub))`.

- [ ] **Step 5: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_screen_routes.py -v`
Expected: PASS (all). Full suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 6: Commit**

```bash
git add ankiweb/screens/overview.py ankiweb/screens/routes.py tests/test_screen_routes.py
git commit -m "feat: overview page route + handler (study/decks/unbury/rebuild/empty)"
```

---

## Task 8: Reviewer placeholder route

**Files:**
- Modify: `ankiweb/screens/routes.py`
- Test: `tests/test_screen_routes.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
def test_reviewer_placeholder(client):
    r = client.get("/reviewer")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="reviewer"' in r.text
    # placeholder offers a way back to decks
    assert "pycmd" in r.text and "decks" in r.text
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_screen_routes.py -k reviewer_placeholder -v`
Expected: FAIL (no /reviewer route).

- [ ] **Step 3: Add the placeholder route + a reviewer "decks" handler**

In `ankiweb/screens/routes.py`, inside `build_screen_router` (before `return router`):
```python
    @router.get("/reviewer", response_class=HTMLResponse)
    async def reviewer_page():
        body = ("<center><h2>Reviewer</h2>"
                "<p>The study screen arrives in the next milestone.</p>"
                "<button onclick='pycmd(\"decks\")'>Back to Decks</button></center>")
        return HTMLResponse(render_page("reviewer", body, ["css/reviewer.css"]))
```
In `register_screen_handlers`, add a minimal reviewer handler so "Back to Decks" works:
```python
    async def reviewer_nav(arg: str):
        if arg == "decks":
            await hub.push_call("reviewer", "ankiwebNavigate", ["/deckbrowser"])
        return None
    hub.set_handler("reviewer", reviewer_nav)
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_screen_routes.py -v`
Expected: PASS (all). Full suite green.

- [ ] **Step 5: Commit**

```bash
git add ankiweb/screens/routes.py tests/test_screen_routes.py
git commit -m "feat: reviewer placeholder route (real reviewer in Plan 3)"
```

> Note: Plan 3 replaces this placeholder route + handler with the real reviewer. The `reviewer` context + "Back to Decks" nav are kept.

---

## Task 9: Integration test — browse → open → overview (Playwright)

**Files:**
- Test: `tests/test_study_loop_home.py`

- [ ] **Step 1: Write the Playwright integration test**

`tests/test_study_loop_home.py`:
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
def live_server(tmp_path: Path):
    col_path = tmp_path / "collection.anki2"
    col = Collection(str(col_path))
    try:
        for i in range(3):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"] = f"Q{i}"
            col.add_note(n, col.decks.id("Default"))
    finally:
        col.close()

    settings = Settings(collection_path=col_path, port=8124)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8124, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8124"
    server.should_exit = True
    t.join(timeout=5)


def test_browse_then_open_deck(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR:", e))
        page.goto(f"{live_server}/")
        # deck browser shows the Default deck with a new-count of 3
        page.wait_for_selector("tr.deck")
        assert "Default" in page.inner_text("body")
        assert "3" in page.inner_text("tr.deck")
        # click the deck name → server sets current + pushes navigate → lands on /overview
        page.click("a.deck")
        page.wait_for_url("**/overview", timeout=5000)
        assert "Study Now" in page.inner_text("body")
        browser.close()
```

- [ ] **Step 2: Run the integration test**

Run: `conda run -n ankiweb python -m pytest tests/test_study_loop_home.py -v`
Expected: PASS — the deck browser renders the Default deck (new-count 3), clicking it navigates to `/overview` showing "Study Now", proving the full server-render → bridge cmd → run_op → push navigate → new screen chain over a real browser + WebSocket.

- [ ] **Step 3: Run the full suite + commit**

Run: `conda run -n ankiweb python -m pytest -q`
Expected: all green.

```bash
git add tests/test_study_loop_home.py
git commit -m "test: study-loop home integration (browse -> open -> overview)"
```

---

## Self-Review

**1. Spec coverage (Spec §6.1, §6.2, §6.4 — home portions):**

| Spec item | Task(s) |
|---|---|
| §6.1 deck tree HTML from `deck_due_tree`, counts, classes | 4 |
| §6.1 bridge commands open/collapse/create/select | 5 |
| §6.2 overview counts + Study Now + bottom links | 6, 7 |
| §6.2 bridge study/decks/unbury/refresh/empty | 7 |
| §6.2 finished → congrats | 6 |
| §6.4 congrats (server-rendered; real SvelteKit deferred) | 6 |
| §2.3 real OpChanges → emit on the bus (Plan 1 deferral) | 1 |
| §6.5 shell nav/router + opchanges reload | 2, 3, 5, 7, 8 |
| navigation between screens | 5, 7, 8 |
| end-to-end proof | 9 |

Deferred (noted, not gaps): deck drag-drop reparent + gear "opts" menu (the handler ignores `opts`); deck Options / Custom Study / deck Description dialogs (overview handler ignores `opts`/`studymore`/`description`); the real SvelteKit congrats page; full i18n; the real Reviewer (Plan 3 — placeholder served).

**2. Placeholder scan:** No "TBD/TODO". The `opts`/`studymore`/`description` no-ops are explicit, documented deferrals (the gear/options dialogs are separate sub-projects), not unfinished requirements.

**3. Type/name consistency:** `op_changes_to_flags`/`run_op` defined Task 1, used Tasks 5/7. `render_page(context, body, css_files)` defined Task 3, used Task 5/7/8. `render_deckbrowser_html(col)`/`make_deckbrowser_handler(service, hub)` defined Tasks 4/5, used Task 5. `render_overview_html(col)`/`make_overview_handler` Tasks 6/7. `render_congrats_html(col)` Task 6, used by overview. `build_screen_router(get_service)`/`register_screen_handlers(service, hub)` Task 5, extended Tasks 7/8, wired in app.py Task 5. Shell globals `ankiwebNavigate`/`ankiwebReload`/`ankiwebCreateDeck` defined Task 2, emitted by handlers Tasks 5/7/8 and the create button Task 4. Bridge `push_call(ctx, fn, args)` and `set_handler(ctx, handler)` are Foundation APIs (unchanged). `run_op(fn, initiator)` matches every call site's `initiator="..."` kwarg.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-31-ankiweb-study-loop-home.md`. (Plan 3 — the Reviewer — follows.)
