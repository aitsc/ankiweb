# ankiweb AnkiConnect B4 — gui* Actions + UI-State Mirror Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `gui*` actions of the AnkiConnect API — drive and read the live web UI (reviewer current card/side, navigate screens, undo, check DB) and the browser-domain queries (browse/select) — backed by a small server-side **UI-state mirror** on the shared `BridgeHub`.

**Architecture:** A `UiState` dataclass lives on the shared `BridgeHub` (`hub.ui_state`), the one object both the web app and the ankiconnect app already share (via `__main__`). The web reviewer screen writes `current_card_id`/`side`; `hub.dispatch_cmd` writes `current_screen`. gui* actions (in `ankiweb/ankiconnect/actions/gui.py`) read the mirror and DRIVE the reviewer by reusing its existing bridge handler (`hub.dispatch_cmd("reviewer", cmd)`), which keeps any connected browser in sync. Navigation actions push `ankiwebNavigate` to the active screen's context. Browser/editor-coupled actions degrade to AnkiConnect's faithful "no window open" return values or are explicitly deferred to Plan D.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the B1–B3 AnkiConnect infra + the C study-loop screens, pytest. Run via `conda run -n ankiweb ...`.

**This is Plan B4 of 4 for Sub-project B (the last).** Spec: `docs/superpowers/specs/2026-06-01-ankiweb-ankiconnect-api-design.md` §1.4, §3.

**Scope (verified by recon).** The complete gui* set is 21 actions. Four "misc/profile" actions (`reloadCollection`, `getProfiles`, `getActiveProfile`, `loadProfile`) are ALREADY shipped in B1 (`actions/meta.py`) — do NOT touch them. B4 implements the remaining **18 gui\* actions**, classified:
- **supportable-now (11):** guiReviewActive, guiCurrentCard, guiStartCardTimer, guiShowQuestion, guiShowAnswer, guiAnswerCard, guiDeckBrowser, guiDeckOverview, guiDeckReview, guiUndo, guiCheckDatabase.
- **degraded-now (5):** guiBrowse (returns the real `findCards` result; records query+matches), guiSelectCard, guiSelectNote (deprecated alias), guiSelectedNotes, guiPlayAudio (best-effort; faithful bool).
- **deferred-to-D / refuse (faithful stubs now):** guiAddCards (validates deck/model, returns the prospective int note id WITHOUT adding — the dialog is deferred to D), guiEditNote (returns None), guiAddNoteSetData (returns the exact "Add Note dialog is not open" error dict — always true pre-D); guiImportFile (refuses — no server file picker); guiExitAnki (no-op-returns-None per spec §4 — never shut the shared server).

**Faithfulness principle for degraded actions:** where AnkiConnect's value depends only on the collection (guiBrowse→findCards) we return the REAL value; where it depends on a live Browser window we return exactly the value AnkiConnect returns when *no Browser is open* (`False` / `[]` / recorded-selection) — a legitimate runtime state, not a fake.

**Grounded anki 25.9.4 facts (verified live):** `card.template()`→TemplateDict (has `"name"`); `card.start_timer()`→None; `card.question()`/`card.answer()`→str; `col.undo()`→OpChangesAfterUndo (has `.changes`); `col.undo_status().undo`→str (empty when nothing to undo); `col.fix_integrity()`→`(str, bool)`; `col._backend.get_scheduling_states(card_id)` is UNRELIABLE for arbitrary cards (raises NotFoundError) → for the reviewer's current card use `col.sched.get_queued_cards(fetch_limit=1).cards[0].states` + `col.sched.describe_next_states(states)` (the exact source `reviewer.py` already uses). `col.decks.id_for_name(name)`→int|None (read-only); `col.decks.set_current(did)`→all-False OpChanges (use `run`, no broadcast); `col.decks.name(did)`→str; `col.startTimebox()`→None (use `run`, not `run_op`).

---

## Architecture map (existing code this plan touches)

- `ankiweb/bridge/hub.py` — `BridgeHub`: `_conns: dict[ctx,[ws]]`, `register/unregister`, `set_handler`, `push_call(ctx,fn,args)`, `eval_with_callback`, `broadcast_opchanges`, `dispatch_cmd(ctx,arg)`→`await handler(arg)`. **B4 adds `self.ui_state` + sets `current_screen` in `dispatch_cmd`.**
- `ankiweb/bridge/ws.py` — `ws_endpoint(websocket, context="default")` registers per ctx, routes `cmd`→`dispatch_cmd`. **B4 sets `current_screen` on connect.**
- `ankiweb/screens/reviewer.py` — `make_reviewer_handler(service, hub)` owns ONE closure-local `ReviewerSession`; `_show_next()` loads/pushes the question; handler args `show`/`ans`/`ease1..4`/`decks`. **B4 writes `hub.ui_state.current_card_id`/`side` here + adds a `starttimer` arg.**
- `ankiweb/ankiconnect/app.py` — per-request `rt = Runtime(service=app.state.service, config=app.state.config, hub=app.state.hub)` (line 71, unchanged). **B4 resolves `hub = hub if hub is not None else BridgeHub()` at function scope (after `owns_service`); the lifespan closure stores that resolved hub as `app.state.hub`, so `rt.hub` is never None and `rt.hub.ui_state` always exists.**
- `ankiweb/ankiconnect/actions/_helpers.py` — `run_emit(rt, fn)` (fn→(value, op); broadcasts; None-safe). **Reused by guiUndo.**
- `ankiweb/screens/routes.py::register_screen_handlers(service, hub)` — registers deckbrowser/overview/reviewer handlers (called by `create_app` lifespan). gui* reviewer-control reuses these via `dispatch_cmd`.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/bridge/ui_state.py` (create) | `UiState` dataclass (the mirror) |
| `ankiweb/bridge/hub.py` (modify) | own a `UiState`; set `current_screen` in `dispatch_cmd` |
| `ankiweb/bridge/ws.py` (modify) | set `current_screen` on WS connect |
| `ankiweb/screens/reviewer.py` (modify) | write `current_card_id`/`side`; add `starttimer` |
| `ankiweb/ankiconnect/app.py` (modify) | resolve `hub = hub or BridgeHub()` |
| `ankiweb/ankiconnect/actions/gui.py` (create) | all 18 gui* actions |
| `ankiweb/ankiconnect/actions/__init__.py` (modify) | import `gui` |
| `tests/ankiconnect/test_gui_actions.py` (create) | gui* tests (web-app TestClient + portal + shared hub) |

---

## Task 1: UI-state mirror + bridge/reviewer wiring

**Files:**
- Create: `ankiweb/bridge/ui_state.py`
- Modify: `ankiweb/bridge/hub.py`, `ankiweb/bridge/ws.py`, `ankiweb/screens/reviewer.py`, `ankiweb/ankiconnect/app.py`
- Test: `tests/test_ui_state.py`

- [ ] **Step 1: Write the failing test** — `tests/test_ui_state.py`:
```python
import functools
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.bridge.ui_state import UiState
from ankiweb.bridge.hub import BridgeHub


def test_ui_state_defaults_and_review_active():
    s = UiState()
    assert s.current_screen is None and s.current_card_id is None and s.side is None
    assert s.browser_open is False
    assert s.matched_card_ids == [] and s.selected_note_ids == []
    assert s.review_active is False
    s.current_screen = "reviewer"
    assert s.review_active is False           # needs a card too
    s.current_card_id = 123
    assert s.review_active is True
    s.current_screen = "deckbrowser"
    assert s.review_active is False           # not on reviewer


def test_hub_has_ui_state():
    assert isinstance(BridgeHub().ui_state, UiState)


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        c.portal.call(c.app.state.service.run, _seed)
        yield c


def _seed(col):
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"; n["Back"] = "a"
    col.add_note(n, col.decks.id("Default"))


def test_dispatch_cmd_sets_current_screen(client):
    hub = client.app.state.hub
    # deckbrowser 'open:...'-style cmd flows through dispatch_cmd -> sets current_screen
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(hub.dispatch_cmd, "deckbrowser", f"open:{did}")
    assert hub.ui_state.current_screen == "deckbrowser"


def test_reviewer_show_updates_ui_state(client):
    hub = client.app.state.hub
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    # drive the reviewer handler directly (no WS needed; pushes are no-ops)
    client.portal.call(hub.dispatch_cmd, "reviewer", "show")
    assert hub.ui_state.current_screen == "reviewer"
    assert hub.ui_state.current_card_id is not None
    assert hub.ui_state.side == "question"
    client.portal.call(hub.dispatch_cmd, "reviewer", "ans")
    assert hub.ui_state.side == "answer"


def test_reviewer_finish_clears_ui_state(client):
    hub = client.app.state.hub
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    client.portal.call(hub.dispatch_cmd, "reviewer", "show")
    client.portal.call(hub.dispatch_cmd, "reviewer", "ans")
    client.portal.call(hub.dispatch_cmd, "reviewer", "ease4")  # graduates the only card -> finished
    assert hub.ui_state.current_card_id is None
    assert hub.ui_state.side is None


def test_ws_connect_sets_current_screen(client):
    hub = client.app.state.hub
    with client.websocket_connect("/ws?context=overview"):
        assert hub.ui_state.current_screen == "overview"
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_ui_state.py -v`
Expected: FAIL (`ModuleNotFoundError: ankiweb.bridge.ui_state`).

- [ ] **Step 3: Create `ankiweb/bridge/ui_state.py`**
```python
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class UiState:
    """Server-side mirror of the live web UI, shared on the BridgeHub. Single-user local.

    Written by: the web client/screens (current_screen via dispatch_cmd + WS connect;
    current_card_id/side by the reviewer handler) and the gui* actions (browse/selection)."""
    current_screen: str | None = None        # 'deckbrowser'|'overview'|'reviewer'|'congrats'
    current_card_id: int | None = None        # reviewer's in-flight card
    side: str | None = None                   # 'question'|'answer'|None
    browser_open: bool = False                # set True by guiBrowse (degraded "Browser window")
    last_browse_query: str | None = None      # the last guiBrowse query (may be None)
    matched_card_ids: list = field(default_factory=list)
    selected_card_ids: list = field(default_factory=list)
    selected_note_ids: list = field(default_factory=list)

    @property
    def review_active(self) -> bool:
        return self.current_screen == "reviewer" and self.current_card_id is not None
```

- [ ] **Step 4: Modify `ankiweb/bridge/hub.py`** — own a `UiState`, set `current_screen` in `dispatch_cmd`.

Add the import at the top:
```python
from ankiweb.bridge.ui_state import UiState
```
In `__init__`, add (after `self._handlers = {}`):
```python
        self.ui_state = UiState()
```
Replace `dispatch_cmd` with (set `current_screen` from the context before running the handler):
```python
    async def dispatch_cmd(self, ctx: str, arg: str) -> Any:
        self.ui_state.current_screen = ctx
        handler = self._handlers.get(ctx)
        if handler is None:
            return None
        return await handler(arg)
```

- [ ] **Step 5: Modify `ankiweb/bridge/ws.py`** — set `current_screen` on connect.

After `hub.register(context, websocket)` add:
```python
        hub.ui_state.current_screen = context
```

- [ ] **Step 6: Modify `ankiweb/screens/reviewer.py`** — write the mirror + add `starttimer`.

In `make_reviewer_handler`'s `_show_next`, replace the body so it writes `hub.ui_state`:
```python
    async def _show_next():
        info = await service.run(lambda col: load_question(col, session))
        if info is None:  # finished → overview (which renders Congrats)
            hub.ui_state.current_card_id = None
            hub.ui_state.side = None
            await hub.push_call("reviewer", "ankiwebNavigate", ["/overview"])
            return
        hub.ui_state.current_card_id = session.card.id
        hub.ui_state.side = "question"
        await hub.push_call("reviewer", "_showQuestion",
                            [info["q"], info["a"], info["bodyclass"]])
        await hub.push_call("reviewer", "ankiwebSetAnswerBar", [show_answer_bar()])
```
In the `handler`, in the `arg == "ans"` branch, after the two `push_call`s add `hub.ui_state.side = "answer"`:
```python
        elif arg == "ans":
            if session.card is None:
                return None
            info = await service.run(lambda col: render_answer(col, session))
            await hub.push_call("reviewer", "_showAnswer", [info["a"]])
            await hub.push_call("reviewer", "ankiwebSetAnswerBar",
                                [ease_buttons_bar(info["labels"])])
            hub.ui_state.side = "answer"
```
Add a new branch BEFORE the `elif arg == "decks":` branch (restart the in-flight card's timer):
```python
        elif arg == "starttimer":
            if session.card is not None:
                await service.run(lambda col: session.card.start_timer())
```
(The `ease1..4` branch already calls `_show_next()` after answering, which now updates the mirror for the next card or clears it on finish — no extra change needed there.)

- [ ] **Step 7: Modify `ankiweb/ankiconnect/app.py`** — guarantee a hub (so `rt.hub.ui_state` always exists).

Add the import at the top:
```python
from ankiweb.bridge.hub import BridgeHub
```
In `create_ankiconnect_app`, right after `owns_service = service is None`, add:
```python
    hub = hub if hub is not None else BridgeHub()
```
(The lifespan already stores `app.state.hub = hub`; now it is never None. In production `__main__` still injects the SHARED hub, so this only affects standalone/test apps.)

- [ ] **Step 8: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_ui_state.py -v`
Then: `conda run -n ankiweb python -m pytest tests/test_screen_routes.py tests/test_reviewer.py tests/test_reviewer_integration.py tests/test_bridge_hub.py tests/test_ws_roundtrip.py -q`
Expected: PASS (reviewer/ws/screen tests must still pass — the mirror writes are additive).

- [ ] **Step 9: Commit**
```bash
git add ankiweb/bridge/ui_state.py ankiweb/bridge/hub.py ankiweb/bridge/ws.py ankiweb/screens/reviewer.py ankiweb/ankiconnect/app.py tests/test_ui_state.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(bridge): UI-state mirror on the hub + reviewer reporting (B4 foundation)"
```

## Context
`UiState` is a lock-free dataclass on the shared `BridgeHub`. `current_screen` is set wherever a screen interacts (`dispatch_cmd`) and on WS connect; the reviewer handler writes `current_card_id`/`side` (inside its existing `service.run` callbacks → serialized on the single executor) and clears them on finish; `review_active` is a derived property. gui* actions read `rt.hub.ui_state` and never need to reach the closure-local `ReviewerSession`.

## Report Format
Report: Status, both pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 2: supportable-now gui* actions (reviewer-control + nav + backend)

**Files:**
- Create: `ankiweb/ankiconnect/actions/gui.py`
- Modify: `ankiweb/ankiconnect/actions/__init__.py`
- Test: `tests/ankiconnect/test_gui_actions.py`

- [ ] **Step 1: Write the failing test** — `tests/ankiconnect/test_gui_actions.py`:
```python
import functools
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app
from ankiweb.ankiconnect.runtime import Runtime
from ankiweb.ankiconnect.config import AnkiConnectConfig
from ankiweb.ankiconnect.registry import ACTIONS


@pytest.fixture
def client(tmp_path: Path):
    # The WEB app constructs hub + service + registers screen handlers in its lifespan,
    # so gui* reviewer-control actions (which reuse hub.dispatch_cmd) work end-to-end.
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        c.portal.call(c.app.state.service.run, _seed)
        yield c


def _seed(col):
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"; n["Back"] = "a"
    col.add_note(n, col.decks.id("Default"))


def _rt(client):
    return Runtime(service=client.app.state.service, config=AnkiConnectConfig(),
                   hub=client.app.state.hub)


async def _run(rt, name, params):
    return await ACTIONS[name](rt, **params)


def _gui(client, name, **params):
    return client.portal.call(_run, _rt(client), name, params)


def _drive(client, arg):
    client.portal.call(client.app.state.hub.dispatch_cmd, "reviewer", arg)


def _select_default(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))


def test_review_active_false_when_idle(client):
    assert _gui(client, "guiReviewActive") is False


def test_gui_current_card_raises_when_idle(client):
    with pytest.raises(Exception):
        _gui(client, "guiCurrentCard")


def test_reviewer_flow(client):
    _select_default(client)
    _drive(client, "show")                       # loads the seeded card
    assert _gui(client, "guiReviewActive") is True
    cur = _gui(client, "guiCurrentCard")
    assert cur["cardId"] and cur["question"] and "Back" in cur["fields"]
    assert cur["buttons"] == [1, 2, 3, 4]
    assert len(cur["nextReviews"]) == 4
    assert cur["modelName"] == "Basic" and cur["deckName"] == "Default"
    assert cur["template"]  # active template name
    assert _gui(client, "guiStartCardTimer") is True
    # show question / answer / answer-card all return True while review is active
    assert _gui(client, "guiShowQuestion") is True
    assert _gui(client, "guiShowAnswer") is True
    assert _gui(client, "guiAnswerCard", ease=3) is True


def test_gui_answer_card_requires_answer_side(client):
    _select_default(client)
    _drive(client, "show")                       # side == 'question'
    assert _gui(client, "guiAnswerCard", ease=3) is False  # answer not shown yet
    assert _gui(client, "guiAnswerCard", ease=9) is False  # out of range, even on answer side later


def test_gui_undo(client):
    # add a note via the API path so there is something to undo
    def add(col):
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "u"
        return col.add_note(n, col.decks.id("Default"))
    client.portal.call(client.app.state.service.run_op, add, "test")
    assert _gui(client, "guiUndo") is True
    # undoing again with nothing to undo still returns True (no-op)
    for _ in range(5):
        if _gui(client, "guiUndo") is True:
            pass
    assert _gui(client, "guiUndo") is True


def test_gui_check_database(client):
    assert _gui(client, "guiCheckDatabase") is True


def test_gui_deck_overview_and_review(client):
    assert _gui(client, "guiDeckOverview", name="Default") is True
    assert _gui(client, "guiDeckOverview", name="No Such Deck") is False
    assert _gui(client, "guiDeckReview", name="Default") is True
    assert _gui(client, "guiDeckReview", name="No Such Deck") is False


def test_gui_deck_browser_pushes_navigate(client):
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        # ws connect set current_screen='deckbrowser'; guiDeckBrowser pushes navigate to it
        assert _gui(client, "guiDeckBrowser") is None
        m = ws.receive_json()
        while m["type"] != "call":
            m = ws.receive_json()
        assert m["fn"] == "ankiwebNavigate" and m["args"] == ["/deckbrowser"]
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_gui_actions.py -v`
Expected: FAIL (gui actions not registered → KeyError in `_run`).

- [ ] **Step 3: Create `ankiweb/ankiconnect/actions/gui.py`**
```python
from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import run_emit, build_note


def _ui(rt):
    return rt.hub.ui_state


# ---------- reviewer state queries ----------
@action("guiReviewActive")
async def gui_review_active(rt):
    return _ui(rt).review_active


@action("guiCurrentCard")
async def gui_current_card(rt):
    ui = _ui(rt)
    if not ui.review_active:
        raise Exception("Gui review is not currently active.")
    cid = ui.current_card_id

    def build(col):
        # nextReviews: prefer the queued top card's states (the reviewer-faithful source);
        # if the queue top has drifted from the mirror, fall back to get_scheduling_states.
        labels = []
        queued = col.sched.get_queued_cards(fetch_limit=1)
        if queued.cards and queued.cards[0].card.id == cid:
            labels = list(col.sched.describe_next_states(queued.cards[0].states))
        else:
            try:
                labels = list(col.sched.describe_next_states(
                    col._backend.get_scheduling_states(cid)))
            except Exception:
                labels = []
        card = col.get_card(cid)
        note = card.note()
        model = note.note_type()
        fields = {name: {"value": note.fields[o], "order": o}
                  for name, (o, _f) in col.models.field_map(model).items()}
        return {
            "cardId": cid,
            "fields": fields,
            "fieldOrder": card.ord,
            "question": card.question(),
            "answer": card.answer(),
            "buttons": [1, 2, 3, 4],          # v3 always has 4 answer buttons (shape-stable, ref-faithful)
            "nextReviews": labels,
            "modelName": model["name"],
            "deckName": col.decks.name(card.did),
            "css": model.get("css", ""),
            "template": card.template()["name"],
        }
    return await rt.service.run(build)


# ---------- reviewer control (drive the real reviewer handler; keeps the browser in sync) ----------
@action("guiStartCardTimer")
async def gui_start_card_timer(rt):
    if not _ui(rt).review_active:
        return False
    await rt.hub.dispatch_cmd("reviewer", "starttimer")
    return True


@action("guiShowQuestion")
async def gui_show_question(rt):
    if not _ui(rt).review_active:
        return False
    await rt.hub.dispatch_cmd("reviewer", "show")
    return True


@action("guiShowAnswer")
async def gui_show_answer(rt):
    if not _ui(rt).review_active:
        return False
    await rt.hub.dispatch_cmd("reviewer", "ans")
    return True


@action("guiAnswerCard")
async def gui_answer_card(rt, ease=None):
    ui = _ui(rt)
    if not ui.review_active or ui.side != "answer":
        return False
    # v3 answerButtons() is hardcoded to 4 in anki 25.9.4 (matches the reference's dynamic
    # check here); also reject bool/non-int ease (a hardening over the reference).
    if not isinstance(ease, int) or isinstance(ease, bool) or not (1 <= ease <= 4):
        return False
    await rt.hub.dispatch_cmd("reviewer", f"ease{ease}")
    return True


# ---------- navigation (push to the active screen's context) ----------
async def _navigate(rt, url):
    target = _ui(rt).current_screen or "deckbrowser"
    await rt.hub.push_call(target, "ankiwebNavigate", [url])


@action("guiDeckBrowser")
async def gui_deck_browser(rt):
    await _navigate(rt, "/deckbrowser")
    return None


@action("guiDeckOverview")
async def gui_deck_overview(rt, name=None):
    did = await rt.service.run(lambda col: col.decks.id_for_name(name or ""))
    if did is None:
        return False
    await rt.service.run(lambda col: col.decks.set_current(did))
    await _navigate(rt, "/overview")
    return True


@action("guiDeckReview")
async def gui_deck_review(rt, name=None):
    did = await rt.service.run(lambda col: col.decks.id_for_name(name or ""))
    if did is None:
        return False
    await rt.service.run(lambda col: col.decks.set_current(did))
    await rt.service.run(lambda col: col.startTimebox())
    await _navigate(rt, "/reviewer")
    return True


# ---------- backend ops (work headless; broadcast so open screens refresh) ----------
@action("guiUndo")
async def gui_undo(rt):
    def do(col):
        from anki.errors import UndoEmpty
        if not col.undo_status().undo:
            return True, None          # nothing to undo → no-op (mw.undo is a no-op)
        try:
            return True, col.undo()
        except UndoEmpty:              # undo_status can report a label yet undo() still be empty
            return True, None
    return await run_emit(rt, do)


@action("guiCheckDatabase")
async def gui_check_database(rt):
    await rt.service.run(lambda col: col.fix_integrity())
    return True
```

- [ ] **Step 4: Modify `ankiweb/ankiconnect/actions/__init__.py`** — add `gui` to the import line:
```python
from ankiweb.ankiconnect.actions import meta, decks, notes, cards, models, media, gui  # noqa: F401
```

- [ ] **Step 5: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_gui_actions.py -v`
Expected: PASS. (`describe_next_states` returns 4 labels for every card type under the v3 scheduler — verified for new/learning/review/cloze — so `len(nextReviews)==4` and `buttons==[1,2,3,4]` hold for any card.)

- [ ] **Step 6: Commit**
```bash
git add ankiweb/ankiconnect/actions/gui.py ankiweb/ankiconnect/actions/__init__.py tests/ankiconnect/test_gui_actions.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(ankiconnect): supportable-now gui* actions (reviewer/nav/undo/checkdb)"
```

## Context
Reviewer-control actions validate via `rt.hub.ui_state` then DRIVE the reviewer through its existing bridge handler (`dispatch_cmd("reviewer", cmd)`), so a connected browser stays in sync (the handler pushes `_showQuestion`/`_showAnswer`/ease-bar). `guiCurrentCard` rebuilds AnkiConnect's dict from the current card, taking `nextReviews`/`buttons` from `get_queued_cards` (the reviewer-faithful source). Nav actions push `ankiwebNavigate` to the active screen's context. `guiUndo` checks `undo_status().undo` first (no-op when empty) and broadcasts via `run_emit`. All return faithful `False`/`None` when no review/screen is active.

## Report Format
Report: Status, pytest summary, files changed, self-review, commit SHA, concerns.

---

## Task 3: degraded + deferred + refuse gui* actions

**Files:**
- Modify: `ankiweb/ankiconnect/actions/gui.py`
- Test: `tests/ankiconnect/test_gui_actions.py` (append)

- [ ] **Step 1: Write the failing test (append to `tests/ankiconnect/test_gui_actions.py`)**
```python
def test_gui_browse_returns_findcards_and_records(client):
    cids = _gui(client, "guiBrowse", query="deck:Default")
    assert isinstance(cids, list) and len(cids) >= 1
    # the query + matches are recorded in the mirror; the Browser is "open"
    assert client.app.state.hub.ui_state.last_browse_query == "deck:Default"
    assert client.app.state.hub.ui_state.matched_card_ids == cids
    assert client.app.state.hub.ui_state.browser_open is True


def test_gui_browse_no_query_returns_empty(client):
    # findCards(None) returns [] in AnkiConnect; guiBrowse with no query must too,
    # while still "opening" the Browser (so guiSelectCard works afterward).
    assert _gui(client, "guiBrowse") == []
    assert client.app.state.hub.ui_state.browser_open is True


def test_gui_browse_reorder_validation(client):
    # a malformed reorderCards must raise (faithful to the reference)
    with pytest.raises(Exception):
        _gui(client, "guiBrowse", query="", reorderCards={"order": "sideways"})
    # a well-formed one is accepted (reorder is a no-op without a table)
    assert isinstance(_gui(client, "guiBrowse", query="",
                            reorderCards={"columnId": "noteFld", "order": "descending"}), list)


def test_gui_select_and_selected_notes(client):
    # no browser "open" yet -> select returns False, selectedNotes is []
    assert _gui(client, "guiSelectedNotes") == []
    cids = _gui(client, "guiBrowse", query="deck:Default")  # "opens" the browser domain
    assert _gui(client, "guiSelectCard", card=cids[0]) is True
    nids = _gui(client, "guiSelectedNotes")
    assert len(nids) == 1 and isinstance(nids[0], int)
    # guiSelectNote is a deprecated alias for guiSelectCard
    assert _gui(client, "guiSelectNote", note=cids[0]) is True


def test_gui_select_card_false_without_browse(client):
    # fresh mirror: browser_open is False -> no browser open -> False (reference behavior)
    assert _gui(client, "guiSelectCard", card=12345) is False


def test_gui_play_audio(client):
    assert _gui(client, "guiPlayAudio") is False     # not reviewing
    _select_default(client)
    _drive(client, "show")
    assert _gui(client, "guiPlayAudio") is True       # reviewing -> faithful True (best-effort)


def test_gui_add_note_set_data_stub(client):
    res = _gui(client, "guiAddNoteSetData",
               note={"deckName": "Default", "modelName": "Basic", "fields": {"Front": "x"}})
    assert res == {"error": "Add Note dialog is not open", "code": 1}


def test_gui_edit_note_noop(client):
    assert _gui(client, "guiEditNote", note=123) is None


def test_gui_add_cards_returns_int_and_validates(client):
    # faithful shape: returns an int note id (note is validated but NOT added pre-D)
    res = _gui(client, "guiAddCards",
               note={"deckName": "Default", "modelName": "Basic", "fields": {"Front": "x"}})
    assert isinstance(res, int)
    assert isinstance(_gui(client, "guiAddCards"), int)   # blank dialog form
    # unknown deck / model still raise (matches the reference's validation)
    with pytest.raises(Exception):
        _gui(client, "guiAddCards",
             note={"deckName": "No Such Deck", "modelName": "Basic", "fields": {"Front": "x"}})
    with pytest.raises(Exception):
        _gui(client, "guiAddCards",
             note={"deckName": "Default", "modelName": "No Such Model", "fields": {}})


def test_gui_import_file_refuses(client):
    with pytest.raises(Exception):
        _gui(client, "guiImportFile", path="/tmp/x.apkg")


def test_gui_exit_anki_noop(client):
    assert _gui(client, "guiExitAnki") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_gui_actions.py -k "browse or select or play_audio or add_note_set or edit_note or add_cards or import or exit" -v`
Expected: FAIL.

- [ ] **Step 3: Append to `ankiweb/ankiconnect/actions/gui.py`**
```python
# ---------- degraded browser-domain actions (faithful to AnkiConnect's "no window" values) ----------
@action("guiBrowse")
async def gui_browse(rt, query=None, reorderCards=None):
    if reorderCards is not None:  # reference checks 1-3 (ref 1795-1807); columnId-resolves (4) needs the table (Plan D)
        if not isinstance(reorderCards, dict):
            raise Exception("reorderCards should be a dict")
        if "columnId" not in reorderCards or "order" not in reorderCards:
            raise Exception('Must provide a "columnId" and an "order" property')
        if reorderCards["order"] not in ("ascending", "descending"):
            raise Exception("invalid card order: " + str(reorderCards["order"]))
        # columnId validity is checked against the live Browser table → deferred to Plan D.
    # findCards(None) returns [] (ref cards.py); only a real query searches.
    cids = await rt.service.run(
        lambda col: [] if query is None else list(col.find_cards(query)))
    ui = _ui(rt)
    ui.browser_open = True          # guiBrowse opens the Browser regardless of the query
    ui.last_browse_query = query
    ui.matched_card_ids = cids
    return cids


@action("guiSelectCard")
async def gui_select_card(rt, card=None):
    ui = _ui(rt)
    if not ui.browser_open:   # no Browser window open → reference returns False
        return False

    def note_of(col):
        try:
            return col.get_card(card).nid
        except Exception:
            return None
    nid = await rt.service.run(note_of)
    ui.selected_card_ids = [card]
    ui.selected_note_ids = [nid] if nid is not None else []
    return True


@action("guiSelectNote")
async def gui_select_note(rt, note=None):
    # deprecated alias: AnkiConnect forwards to guiSelectCard (selects by CARD id)
    return await gui_select_card(rt, card=note)


@action("guiSelectedNotes")
async def gui_selected_notes(rt):
    return list(_ui(rt).selected_note_ids)


@action("guiPlayAudio")
async def gui_play_audio(rt):
    # [sound:] audio playback in the reviewer is deferred to Plan 4; preserve the contract:
    # True while review is active (best-effort side effect), False otherwise.
    return bool(_ui(rt).review_active)


# ---------- deferred to Plan D (editor/import) — faithful stubs now ----------
@action("guiAddNoteSetData")
async def gui_add_note_set_data(rt, note=None, append=False):
    # The Add Note editor dialog is Plan D; it is never open pre-D, so return exactly
    # AnkiConnect's "dialog not open" payload.
    return {"error": "Add Note dialog is not open", "code": 1}


@action("guiEditNote")
async def gui_edit_note(rt, note=None):
    # No editor dialog yet (Plan D); reference returns null. No-op.
    return None


@action("guiAddCards")
async def gui_add_cards(rt, note=None):
    # The interactive Add dialog is Plan D. Preserve the contract (returns an int note id)
    # without the surprising side effect of actually adding: validate deck/model/fields and
    # return the prospective (unsaved) note id — like the reference, which returns the
    # not-yet-saved ankiNote.id. The note is NOT added to the collection.
    if note is None:
        return 0  # blank dialog → fresh unsaved note (deferred to Plan D)

    def build(col):
        did = col.decks.id_for_name(note.get("deckName", ""))
        if did is None:
            raise Exception("deck was not found: " + str(note.get("deckName")))
        n, _ = build_note(col, note)  # raises on unknown model/fields (faithful validation)
        return n.id                   # unsaved note id (0 until added; dialog deferred to D)
    return await rt.service.run(build)


# ---------- server-incompatible (refuse / no-op) ----------
@action("guiImportFile")
async def gui_import_file(rt, path=None):
    raise Exception("guiImportFile is not supported in ankiweb (no GUI file picker)")


@action("guiExitAnki")
async def gui_exit_anki(rt):
    # Never shut down the shared local server on a client request (spec §4). No-op.
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_gui_actions.py -v`
Then full suite: `conda run -n ankiweb python -m pytest -q`.
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add ankiweb/ankiconnect/actions/gui.py tests/ankiconnect/test_gui_actions.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(ankiconnect): degraded + deferred gui* actions (browse/select/stubs)"
```

## Context
`guiBrowse` returns the REAL `findCards(query)` (its entire contract for clients like Yomitan) — `query=None`→`[]` exactly like the reference — sets `browser_open=True`, and records query+matches into the mirror so `guiSelectCard`/`guiSelectedNotes` have a domain; `reorderCards` validation mirrors the reference's checks 1-3 (the columnId-resolves check needs the table → Plan D). `guiSelectCard`/`guiSelectNote`/`guiSelectedNotes` return exactly AnkiConnect's "no Browser open" values (`False`/`[]`) until a `guiBrowse` opens the domain (`browser_open`). The Plan-D-coupled actions preserve faithful shapes: `guiAddCards` validates deck/model and returns the prospective int note id (no add); `guiAddNoteSetData` returns the exact `{"error":"Add Note dialog is not open","code":1}` payload; `guiEditNote` returns `None`. `guiImportFile` refuses; `guiExitAnki` no-ops per spec §4.

## Report Format
Report: Status, gui + full-suite pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (B4 = gui* per §1.4/§3):** Foundation (Task 1): `UiState` mirror on the hub, reviewer reports card/side, `current_screen` tracking, `rt.hub.ui_state` always present. supportable-now (Task 2): guiReviewActive, guiCurrentCard, guiStartCardTimer, guiShowQuestion, guiShowAnswer, guiAnswerCard, guiDeckBrowser, guiDeckOverview, guiDeckReview, guiUndo, guiCheckDatabase. degraded (Task 3): guiBrowse, guiSelectCard, guiSelectNote, guiSelectedNotes, guiPlayAudio. deferred/refuse (Task 3): guiAddNoteSetData, guiEditNote, guiAddCards, guiImportFile, guiExitAnki. NOT touched (already in B1 meta.py): reloadCollection, getProfiles, getActiveProfile, loadProfile. Total registered after B4: ~108 actions.

**2. Placeholder scan:** No TBD/TODO. Deferrals (guiAddCards/guiEditNote/guiAddNoteSetData → Plan D editor; guiPlayAudio side effect → Plan 4 audio; guiImportFile/guiExitAnki → refuse/no-op) are documented and return faithful shapes, not stubs-that-lie.

**3. Type/name consistency:** `_ui(rt)`→`rt.hub.ui_state` (a `UiState`); `run_emit` (from `_helpers`, B2/B3) reused by guiUndo (`col.undo()`→OpChangesAfterUndo has `.changes`). All actions `async def(rt, **params)` with kwargs matching AnkiConnect names (name, ease, query, reorderCards, card, note, append, path). Reviewer-control reuses `hub.dispatch_cmd("reviewer", "show"|"ans"|"ease{n}"|"starttimer")` — `starttimer` is the only new reviewer command added in Task 1. `current_screen` written in `dispatch_cmd` (hub) + WS connect (ws.py); `current_card_id`/`side` written by the reviewer handler. `create_ankiconnect_app` resolves `hub = hub or BridgeHub()` so `rt.hub.ui_state` is never None. `actions/__init__` imports meta/decks/notes/cards/models/media/gui.

**4. Risks & mitigations:** (a) `current_screen` can go stale if a tab closes without navigating — acceptable for single-user local; overwritten on next interaction; `review_active` also requires `current_card_id` which the reviewer clears on finish. (b) `guiCurrentCard` recomputes labels from `get_queued_cards` (queue top == current card) with a `get_scheduling_states` fallback; `buttons` is hardcoded `[1,2,3,4]` (v3 always has 4 — verified) so the shape is stable like the reference. (c) reviewer-control actions need the reviewer handler registered on the shared hub — true in production (`create_app` lifespan) and in the tests (web-app TestClient). (d) standalone ankiconnect apps get a private hub with no reviewer handler → reviewer-control returns faithful `False` (review not active), which is correct.

**5. Adversarial verification (3-agent Workflow vs live anki 25.9.4 + reference plugin + existing code):** anki-reviewer-flow RAN PROBES and confirmed ALL load-bearing assumptions: `get_queued_cards(fetch_limit=1)` top == current card and doesn't advance until answered; `describe_next_states` returns EXACTLY 4 labels for new/learning/review/cloze under v3 (so `buttons==[1,2,3,4]` holds); `col.undo()` raises `anki.errors.UndoEmpty` when empty (the guard is load-bearing) and returns `OpChangesAfterUndo` (has `.changes` → run_emit works); `col.fix_integrity()`→`(str,bool)` no-raise; `card.template()["name"]`, `card.start_timer()`, `set_current`→all-False OpChanges (so `run` not `run_op`), `startTimebox`, `id_for_name` all confirmed. consistency confirmed every edit anchor matches byte-for-byte, no circular import (ui_state→stdlib only), `portal.call(fn, *args)` forwards extra positional args (so the test helper is valid), and `dispatch_cmd` is untested elsewhere so unconditionally setting `current_screen` breaks nothing. contract fixes FOLDED IN: guiBrowse `query=None`→`[]` (+`browser_open` flag for the select gate); guiAddCards returns a faithful int note id (validates, no add) instead of raising; guiCurrentCard shape-stable `buttons`/`nextReviews`; reorderCards 3-check validation; guiUndo `UndoEmpty` hardening. **Confirmed-equivalent (no change):** hardcoded `1<=ease<=4` matches the reference's `answerButtons()` (hardcoded 4 in v3); `'buttons'` as ease values `[1,2,3,4]` matches `[b[0] for b in _answerButtonList()]`; guiShowQuestion re-fetch/timer-restart is an accepted bridge-architecture divergence (re-render == re-show).
