# ankiweb Reviewer Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ankiweb actually usable for studying — a working Reviewer screen: see a card's question (rendered by Anki's real `reviewer.js`), reveal the answer, rate it with the four ease buttons (showing real interval previews), and advance to the next card (or Congrats), with deck/overview counts refreshing via the OpChanges bus.

**Architecture:** A `ReviewerSession` holds the in-flight `anki.cards.Card` (timer started) and its `SchedulingStates` between show→answer (the card object must persist because `build_answer` needs `card.time_taken()`). The reviewer page reuses Anki's real `reviewer.js` (+ jQuery + MathJax) to render `#qa` via the spike-proven `_showQuestion(q,a,bodyclass)`/`_showAnswer(a)` globals; a small server-driven answer bar (`ankiwebSetAnswerBar(html)`) shows the Show-Answer button, then the four ease buttons whose interval labels come from `col.sched.describe_next_states(states)`. Bridge commands `show`/`ans`/`ease1..4`/`decks` drive the flow: `show` fetches the top of `get_queued_cards`; `ease N` runs `build_answer`→`answer_card` (via `run_op`, so OpChanges broadcast) then shows the next card or navigates to `/overview` (which shows Congrats when finished).

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, FastAPI, the Foundation + Home modules, Playwright. Run everything via `conda run -n ankiweb ...`.

**This is Plan 3 of 3 for Study Loop C** (Plan 4 = Reviewer Extras). Spec §6.3: `docs/superpowers/specs/2026-05-31-ankiweb-foundation-study-loop-design.md`.

**Deliberate deferrals to Plan 4 (Reviewer Extras), NOT defects:** type-in-the-answer (`[[type:Field]]` filtering + `compare_answer` diff); `[sound:]` HTML5 audio + replay buttons; custom scheduling (`cardStateCustomizer` eval handshake + `getSchedulingStatesWithContext`/`setSchedulingStates` RPC handlers + per-session state-mutation key); auto-advance; the Edit-current-note button (`pycmd("edit")` — needs the editor, Plan D); reuse of the compiled `reviewer-bottom.js` bottom-bar bundle (Plan 3 uses a simpler server-driven answer bar). For Plan 3, cards with `[[type:...]]` will show the literal marker (acceptable — test uses plain Basic cards). Also deferred (documented for a complete deferral set): **leech detection** (`col.sched.state_is_leech(new_state)` → tag/suspend feedback); the **non-v3 scheduler guard** (Anki's reviewer refuses sched_ver 1 — acceptable to skip since modern collections are v3-only, but no guard is added); **reviewer keyboard shortcuts** (Space = show-answer/Good, 1–4 = ease, `e` = edit, `r` = replay — client keydown→pycmd, added later); and **nightMode in the card bodyclass** (Plan 3 uses `card card{ord+1}` without the theme class). TTS + voice recording remain out of scope entirely.

**Grounded facts (verified live against anki 25.9.4 in the env):**
- `col.sched.get_queued_cards(fetch_limit=1)` → `QueuedCards{cards, new_count, learning_count, review_count}`; empty `cards` ⇒ finished.
- `top = queued.cards[0]`: `top.card` (Card proto, `.id`), `top.states` (`SchedulingStates`), `top.context`.
- `card = col.get_card(top.card.id)`; **`card.start_timer()` is REQUIRED before `build_answer`** (else `time_taken()` does `time.time() - None` → TypeError). The session must hold this same `card` through to the answer.
- `card.question()` / `card.answer()` → HTML strings; `card.ord` → int (bodyclass `card card{ord+1}`).
- `col.sched.describe_next_states(states)` → 4 labels in order [Again, Hard, Good, Easy] (e.g. `<1m`/`<6m`/`<10m`/`3d`; they contain Unicode bidi isolate chars — render as-is).
- `col.sched.build_answer(card=card, states=states, rating=CardAnswer.Rating.X)` (KEYWORD-ONLY) → `CardAnswer`; `CardAnswer.Rating` AGAIN/HARD/GOOD/EASY = 0/1/2/3 (`from anki.scheduler.v3 import CardAnswer`).
- `col.sched.answer_card(answer)` → `OpChanges` with `study_queues=True` (so the bus broadcast triggers deckbrowser/overview reload).
- reviewer.js exposes `window._showQuestion`/`_showAnswer` after its IIFE; it also emits `pycmd("updateToolbar")` after each render — the handler must ignore unknown commands (return None, never raise).

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/screens/reviewer.py` (create) | `ReviewerSession`; flow fns `load_question`/`render_answer`/`answer_current`; answer-bar generators; `reviewer_page_body()`; `make_reviewer_handler(service, hub)` |
| `ankiweb/screens/page.py` (modify) | `render_page` gains a `js_files` param (inject `<script src=/_anki/...>` before bootstrap.js) |
| `ankiweb/screens/routes.py` (modify) | `/reviewer` serves the real reviewer page; register the real reviewer handler (replacing the placeholder) |
| `tests/test_reviewer.py` (create) | flow + answer-bar + handler tests |
| `tests/test_screens_page.py` (modify) | js_files assertion |
| `tests/test_reviewer_integration.py` (create) | Playwright: study a card end-to-end |

---

## Task 1: ReviewerSession + review-flow functions

**Files:**
- Create: `ankiweb/screens/reviewer.py`
- Test: `tests/test_reviewer.py`

- [ ] **Step 1: Write the failing test**

`tests/test_reviewer.py`:
```python
import tempfile, os
import pytest
from anki.collection import Collection
from ankiweb.screens.reviewer import (
    ReviewerSession, load_question, render_answer, answer_current,
)


@pytest.fixture
def col():
    c = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))
    for i in range(2):
        n = c.new_note(c.models.by_name("Basic")); n["Front"] = f"Q{i}"; n["Back"] = f"A{i}"
        c.add_note(n, c.decks.id("Default"))
    yield c
    c.close()


def test_load_question_returns_html_and_sets_session(col):
    s = ReviewerSession()
    info = load_question(col, s)
    assert info is not None
    assert "Q0" in info["q"] or "Q1" in info["q"]   # one of the two cards' fronts
    assert info["bodyclass"].startswith("card card")
    assert s.card is not None and s.states is not None


def test_load_question_returns_none_when_finished(col):
    # bury both cards so the queue is empty → finished
    s = ReviewerSession()
    cids = col.find_cards("")
    col.sched.bury_cards(cids)
    assert load_question(col, s) is None
    assert s.card is None


def test_render_answer_has_answer_and_four_labels(col):
    s = ReviewerSession()
    load_question(col, s)
    info = render_answer(col, s)
    assert info["a"]                       # answer HTML present
    assert len(info["labels"]) == 4        # Again/Hard/Good/Easy interval labels


def test_answer_advances_queue(col):
    s = ReviewerSession()
    load_question(col, s)
    before = col.sched.counts()            # (new, learn, review)
    changes = answer_current(col, s, 3)    # rate Good
    assert changes.study_queues is True
    after = col.sched.counts()
    assert after != before                 # answering moved the card
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_reviewer.py -v`
Expected: FAIL (`ModuleNotFoundError: ankiweb.screens.reviewer`).

- [ ] **Step 3: Implement the session + flow functions**

`ankiweb/screens/reviewer.py`:
```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ReviewerSession:
    """Holds the in-flight card (timer started) and its scheduling states between
    show-question, show-answer, and answer. Single-user → one session per reviewer."""
    card: object = None      # anki.cards.Card with start_timer() already called
    states: object = None    # SchedulingStates from the queue
    context: object = None   # SchedulingContext


def load_question(col, session: ReviewerSession) -> dict | None:
    """Fetch the top queued card into the session, start its timer, render the question.
    Returns {"q","a","bodyclass"} or None when there are no cards left (finished)."""
    queued = col.sched.get_queued_cards(fetch_limit=1)
    if not queued.cards:
        session.card = session.states = session.context = None
        return None
    top = queued.cards[0]
    card = col.get_card(top.card.id)
    card.start_timer()  # REQUIRED: build_answer() later calls card.time_taken()
    session.card = card
    session.states = top.states
    session.context = top.context
    return {"q": card.question(), "a": card.answer(), "bodyclass": f"card card{card.ord + 1}"}


def render_answer(col, session: ReviewerSession) -> dict:
    """Render the answer side + the 4 ease interval labels [Again, Hard, Good, Easy]."""
    return {
        "a": session.card.answer(),
        "labels": list(col.sched.describe_next_states(session.states)),
    }


def answer_current(col, session: ReviewerSession, ease: int):
    """Answer the in-flight card with ease 1..4. Returns OpChanges."""
    from anki.scheduler.v3 import CardAnswer
    rating_map = {
        1: CardAnswer.Rating.AGAIN, 2: CardAnswer.Rating.HARD,
        3: CardAnswer.Rating.GOOD, 4: CardAnswer.Rating.EASY,
    }
    answer = col.sched.build_answer(
        card=session.card, states=session.states, rating=rating_map[ease]
    )
    return col.sched.answer_card(answer)
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_reviewer.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add ankiweb/screens/reviewer.py tests/test_reviewer.py
git commit -m "feat: reviewer session + flow (load question, render answer, answer card)"
```

## Context
These functions are the server-side heart of the reviewer and run inside `service.run`/`run_op` (so all `col`-touching calls are on the single worker thread). The session holds the `Card` object (not just an id) because `build_answer` needs the timer that `load_question` started on that exact object. `answer_current` returns `OpChanges` so the handler can drive it through `run_op` (broadcasting `study_queues` for cross-screen refresh).

## Before You Begin
Ask if unclear. Otherwise TDD via the conda env.

## Report Format
Report: Status, test results (pytest summary), files changed, self-review findings, commit SHA, concerns.

---

## Task 2: Answer-bar generators

**Files:**
- Modify: `ankiweb/screens/reviewer.py`
- Test: `tests/test_reviewer.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
def test_show_answer_bar():
    from ankiweb.screens.reviewer import show_answer_bar
    html = show_answer_bar()
    assert "Show Answer" in html
    assert "pycmd('ans')" in html


def test_ease_buttons_bar():
    from ankiweb.screens.reviewer import ease_buttons_bar
    html = ease_buttons_bar(["<1m", "<6m", "<10m", "3d"])
    for name in ("Again", "Hard", "Good", "Easy"):
        assert name in html
    for i in (1, 2, 3, 4):
        assert f"pycmd('ease{i}')" in html
    assert "3d" in html  # easy interval label rendered
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_reviewer.py -k "answer_bar or ease_buttons" -v`
Expected: FAIL (`ImportError: cannot import name 'show_answer_bar'`).

- [ ] **Step 3: Implement (append to ankiweb/screens/reviewer.py)**

```python
import html as _html

_EASE_NAMES = ("Again", "Hard", "Good", "Easy")


def show_answer_bar() -> str:
    return "<button id='ansbut' class='ansbut' onclick=\"pycmd('ans')\">Show Answer</button>"


def ease_buttons_bar(labels) -> str:
    """labels: 4 interval strings in order [Again, Hard, Good, Easy]."""
    cells = []
    for i, name in enumerate(_EASE_NAMES, start=1):
        label = _html.escape(labels[i - 1]) if i - 1 < len(labels) else ""
        cells.append(
            f"<button class='ease' data-ease='{i}' onclick=\"pycmd('ease{i}')\">"
            f"<span class='ease-label'>{name}</span>"
            f"<span class='ease-ivl'>{label}</span></button>"
        )
    return "<div class='ease-row'>" + "".join(cells) + "</div>"
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_reviewer.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add ankiweb/screens/reviewer.py tests/test_reviewer.py
git commit -m "feat: reviewer answer-bar generators (show-answer + ease buttons)"
```

## Context
Pure HTML generators for the server-driven answer bar (no `col`). `show_answer_bar` is shown after the question; `ease_buttons_bar` after the answer, with interval previews from `describe_next_states`. The buttons emit `pycmd('ans')` / `pycmd('ease1..4')`. (We do not reuse the compiled `reviewer-bottom.js` bottom bar in Plan 3 — this simpler bar is sufficient; reuse is a possible later refinement.)

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 3: `render_page` gains `js_files`

**Files:**
- Modify: `ankiweb/screens/page.py`
- Test: `tests/test_screens_page.py` (append)

- [ ] **Step 1: Write the failing test (append to tests/test_screens_page.py)**

```python
def test_render_page_injects_js_files_before_bootstrap():
    from ankiweb.screens.page import render_page
    html = render_page("reviewer", "<div id=qa></div>",
                       ["css/reviewer.css"], ["js/reviewer.js"])
    assert '/_anki/js/reviewer.js' in html
    # vendored js must load before the shell bootstrap so window._showQuestion exists
    assert html.index("/_anki/js/reviewer.js") < html.index("bootstrap.js")
    # and after the context var
    assert html.index("__ankiwebContext") < html.index("/_anki/js/reviewer.js")
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_screens_page.py -v`
Expected: FAIL (`render_page() takes ... positional arguments but 4 were given` or missing js).

- [ ] **Step 3: Replace `render_page` in `ankiweb/screens/page.py`**

```python
from __future__ import annotations
from typing import Sequence


def render_page(
    context: str,
    body: str,
    css_files: Sequence[str] = (),
    js_files: Sequence[str] = (),
) -> str:
    """Wrap a server-rendered fragment in a full shell HTML document.

    Sets window.__ankiwebContext BEFORE any script so the Bridge connects to
    /ws?context=<context>. Vendored js_files (served from /_anki/) load BEFORE
    the shell bootstrap.js, so globals they define (e.g. reviewer.js's
    window._showQuestion) exist when the page body's inline script runs.
    """
    links = "".join(f'<link rel="stylesheet" href="/_anki/{c}">' for c in css_files)
    scripts = "".join(f'<script src="/_anki/{j}"></script>' for j in js_files)
    return (
        "<!doctype html>\n"
        '<html><head><meta charset="utf-8">'
        f'<script>window.__ankiwebContext="{context}"</script>'
        f"{links}"
        f"{scripts}"
        '<script src="/shell/static/bootstrap.js"></script>'
        "</head>"
        f"<body>{body}</body></html>"
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_screens_page.py -v`
Expected: PASS (both the existing `test_render_page_structure` and the new test).

- [ ] **Step 5: Commit**

```bash
git add ankiweb/screens/page.py tests/test_screens_page.py
git commit -m "feat: render_page supports js_files (vendored scripts before bootstrap)"
```

## Context
The reviewer page needs to load the vendored `jquery.min.js`, `mathjax.js`, `tex-chtml-full.js`, and `reviewer.js` BEFORE `bootstrap.js`, so that when the page body's inline script runs, both `window._showQuestion` (from reviewer.js) and `window.__ankiwebBridge` (from bootstrap.js) exist. Existing callers (deckbrowser/overview) pass no `js_files` and are unaffected.

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 4: Reviewer page + handler + route (replace the placeholder)

**Files:**
- Modify: `ankiweb/screens/reviewer.py` (add `reviewer_page_body` + `make_reviewer_handler`), `ankiweb/screens/routes.py`
- Test: `tests/test_reviewer.py` (append), `tests/test_screen_routes.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_reviewer.py`:
```python
def test_reviewer_page_body_loads_qa_and_registers():
    from ankiweb.screens.reviewer import reviewer_page_body
    body = reviewer_page_body()
    assert "id='qa'" in body or 'id="qa"' in body
    assert "ankiweb-answer" in body
    assert "registerCalls" in body
    assert "_showQuestion" in body
    assert "pycmd('show')" in body
```

Append to `tests/test_screen_routes.py`:
```python
def test_reviewer_route_serves_real_page(client):
    r = client.get("/reviewer")
    assert r.status_code == 200
    assert 'window.__ankiwebContext="reviewer"' in r.text
    assert "/_anki/js/reviewer.js" in r.text          # real reviewer bundle loaded
    assert "/_anki/css/reviewer.css" in r.text
    assert "id='qa'" in r.text or 'id="qa"' in r.text


def test_reviewer_show_pushes_question(client):
    # seed a card and select Default
    client.portal.call(client.app.state.service.run, _seed)
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        msgs = {}
        for _ in range(2):  # expect _showQuestion + ankiwebSetAnswerBar (order not guaranteed)
            m = ws.receive_json()
            if m["type"] == "call":
                msgs[m["fn"]] = m["args"]
        assert "_showQuestion" in msgs
        assert "ankiwebSetAnswerBar" in msgs
        assert "Show Answer" in msgs["ankiwebSetAnswerBar"][0]


def test_reviewer_ease_answers_and_shows_next(client):
    # The client fixture already seeds exactly ONE Basic card (do NOT seed again).
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        # drain the two pushes from show (_showQuestion + ankiwebSetAnswerBar)
        ws.receive_json(); ws.receive_json()
        # answer Easy (ease4): a new card graduates to review (multi-day) → today's queue empties
        # → reviewer navigates to /overview. (Good/ease3 would move it to learning, which
        # may still be queued, so use Easy for a deterministic "finished".)
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "ease4"})
        nav = None
        for _ in range(5):  # tolerate an intervening opchanges broadcast frame
            m = ws.receive_json()
            if m["type"] == "call" and m["fn"] == "ankiwebNavigate":
                nav = m["args"]; break
        assert nav == ["/overview"]
```
(Note: the Plan-2 `client` fixture in `tests/test_screen_routes.py` already seeds exactly ONE Basic card via `_seed`. `test_reviewer_ease_answers_and_shows_next` therefore must NOT seed again — it answers that single card with Easy (ease4), which graduates it out of today's queue so the reviewer finishes and navigates to `/overview`. The `for _ in range(5)` loop only needs to tolerate one intervening `opchanges` broadcast frame (from the `run_op` answer) before the `ankiwebNavigate` call. `test_reviewer_show_pushes_question` calls `_seed` once more, which is fine — it only needs a card to show.)

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/test_reviewer.py tests/test_screen_routes.py -k reviewer -v`
Expected: FAIL (no real page/handler; placeholder still served).

- [ ] **Step 3: Add `reviewer_page_body` + `make_reviewer_handler` (append to ankiweb/screens/reviewer.py)**

```python
def reviewer_page_body() -> str:
    """The reviewer DOM shell + inline script that registers the JS calls the server
    pushes (_showQuestion/_showAnswer from reviewer.js; ankiwebSetAnswerBar for our bar)
    and asks the server for the first card on load."""
    return (
        "<div id='_mark' hidden>★</div>"
        "<div id='_flag' hidden>⚑</div>"
        "<div id='qa' dir='auto'></div>"
        "<div id='ankiweb-answer'></div>"
        "<script>(function(){"
        "var b=window.__ankiwebBridge;"
        "b.registerCalls({"
        "_showQuestion:function(){return window._showQuestion.apply(window,arguments);},"
        "_showAnswer:function(){return window._showAnswer.apply(window,arguments);},"
        "ankiwebSetAnswerBar:function(h){"
        "document.getElementById('ankiweb-answer').innerHTML=String(h);}"
        "});"
        "window.addEventListener('load',function(){window.pycmd('show');});"
        "})();</script>"
    )


def make_reviewer_handler(service, hub):
    """Bridge handler for the 'reviewer' context. Owns one ReviewerSession."""
    session = ReviewerSession()

    async def _show_next():
        info = await service.run(lambda col: load_question(col, session))
        if info is None:  # finished → overview (which renders Congrats)
            await hub.push_call("reviewer", "ankiwebNavigate", ["/overview"])
            return
        await hub.push_call("reviewer", "_showQuestion",
                            [info["q"], info["a"], info["bodyclass"]])
        await hub.push_call("reviewer", "ankiwebSetAnswerBar", [show_answer_bar()])

    async def handler(arg: str):
        if arg == "show":
            await _show_next()
        elif arg == "ans":
            info = await service.run(lambda col: render_answer(col, session))
            await hub.push_call("reviewer", "_showAnswer", [info["a"]])
            await hub.push_call("reviewer", "ankiwebSetAnswerBar",
                                [ease_buttons_bar(info["labels"])])
        elif arg in ("ease1", "ease2", "ease3", "ease4"):
            ease = int(arg[4:])
            await service.run_op(lambda col: answer_current(col, session, ease),
                                 initiator="reviewer")
            await _show_next()
        elif arg == "decks":
            await hub.push_call("reviewer", "ankiwebNavigate", ["/deckbrowser"])
        # ignore everything else (e.g. reviewer.js emits "updateToolbar" after each render)
        return None

    return handler
```

- [ ] **Step 4: Wire the real reviewer into routes (ankiweb/screens/routes.py)**

1. Add import: `from ankiweb.screens.reviewer import reviewer_page_body, make_reviewer_handler`.
2. Replace the placeholder `/reviewer` route's body. The route becomes:
```python
    @router.get("/reviewer", response_class=HTMLResponse)
    async def reviewer_page():
        return HTMLResponse(render_page(
            "reviewer",
            reviewer_page_body(),
            ["css/reviewer.css"],
            ["js/vendor/jquery.min.js", "js/mathjax.js",
             "js/vendor/mathjax/tex-chtml-full.js", "js/reviewer.js"],
        ))
```
3. In `register_screen_handlers`, REPLACE the placeholder `reviewer_nav` registration with:
```python
    hub.set_handler("reviewer", make_reviewer_handler(service, hub))
```
   (Delete the old `async def reviewer_nav(...)` placeholder and its `set_handler` line — the real handler now covers `decks` too.)

- [ ] **Step 5: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/test_reviewer.py tests/test_screen_routes.py -v`
Expected: PASS. Then full suite: `conda run -n ankiweb python -m pytest -q`. **You MUST update the Plan-2 `test_reviewer_placeholder` test in `tests/test_screen_routes.py`** — its existing body is `assert r.status_code == 200`, `assert 'window.__ankiwebContext="reviewer"' in r.text`, and `assert "pycmd" in r.text and "decks" in r.text`. The real reviewer page has no "decks" control, so the `"decks" in r.text` assertion now FAILS. Simplest fix: **delete `test_reviewer_placeholder` entirely** (it is fully superseded by `test_reviewer_route_serves_real_page` added in Step 1). (Alternatively, replace its body with `assert r.status_code == 200; assert 'window.__ankiwebContext="reviewer"' in r.text; assert "/_anki/js/reviewer.js" in r.text`.) Then re-run the full suite.

- [ ] **Step 6: Commit**

```bash
git add ankiweb/screens/reviewer.py ankiweb/screens/routes.py tests/test_reviewer.py tests/test_screen_routes.py
git commit -m "feat: real reviewer page + handler (show/ans/ease/decks) replacing placeholder"
```

## Context
`reviewer_page_body` registers the JS calls synchronously (reviewer.js + bootstrap.js are sync head scripts, so `window._showQuestion` and `window.__ankiwebBridge` exist by the time the body inline script runs), then sends `pycmd("show")` on `load` (after bootstrap's `ready()` load-listener has flushed the domDone queue). The handler: `show` loads & pushes the question + Show-Answer bar (or navigates to /overview if finished); `ans` pushes the answer + ease buttons; `easeN` answers via `run_op` (broadcasts study_queues) then shows the next; `decks` navigates home; unknown commands (e.g. `updateToolbar` from reviewer.js) are ignored. The route replaces Plan 2's placeholder; update the placeholder test accordingly.

## Report Format
Report: Status, test results (new + full suite), files changed, self-review, commit SHA, concerns.

---

## Task 5: Integration test — study a card end-to-end (Playwright)

**Files:**
- Test: `tests/test_reviewer_integration.py`

- [ ] **Step 1: Write the Playwright test**

`tests/test_reviewer_integration.py`:
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
        n = col.new_note(col.models.by_name("Basic")); n["Front"] = "CapitalFrance"; n["Back"] = "Paris"
        col.add_note(n, col.decks.id("Default"))
        col.decks.set_current(col.decks.id("Default"))
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8125)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8125, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8125"
    server.should_exit = True; t.join(timeout=5)


def test_study_one_card(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR:", e))
        page.goto(f"{live_server}/reviewer")
        # real reviewer.js renders the question into #qa
        page.wait_for_function("document.getElementById('qa').textContent.includes('CapitalFrance')",
                               timeout=6000)
        # Show Answer
        page.click("#ansbut")
        page.wait_for_function("document.getElementById('qa').textContent.includes('Paris')",
                               timeout=6000)
        # four ease buttons appear with interval labels
        page.wait_for_selector(".ease[data-ease='4']")
        assert page.locator(".ease").count() == 4
        # rate Easy (ease4) → the lone new card graduates to review (multi-day) →
        # today's queue empties → reviewer navigates to /overview (Congrats).
        # (Good/ease3 would leave the card in the learning queue, re-fetched as the
        # same card → it would never finish.)
        page.click(".ease[data-ease='4']")
        page.wait_for_url("**/overview", timeout=6000)
        assert "Congratulations" in page.inner_text("body")
        browser.close()
```

- [ ] **Step 2: Run the integration test**

Run: `conda run -n ankiweb python -m pytest tests/test_reviewer_integration.py -v -s`
Expected: PASS — the real `reviewer.js` renders the question, "Show Answer" reveals "Paris", four ease buttons appear, rating Good answers the card and (queue empty) navigates to `/overview` which shows Congratulations. The `-s` surfaces any `PAGEERROR`. If `#qa` never gets the question, check (a) the WS connected under context "reviewer", (b) `window._showQuestion` is defined after reviewer.js (it is per the Plan-1 spike), (c) the inline script registered calls before `pycmd("show")`. Do NOT fake a pass.

- [ ] **Step 3: Full suite + commit**

Run: `conda run -n ankiweb python -m pytest -q`
Expected: all green.

```bash
git add tests/test_reviewer_integration.py
git commit -m "test: reviewer integration — study a card end-to-end in a real browser"
```

## Context
The capstone: proves the whole study loop works in a real browser — question rendered by Anki's real `reviewer.js`, answer revealed, ease buttons shown with intervals, answering with **Easy (ease4)** finishes the queue and navigates to Congrats. The load-bearing assertions are `wait_for_function` on `#qa` text and `wait_for_url("**/overview")`; `page.locator(".ease").count()` is the canonical way to count the buttons (`query_selector_count` does NOT exist on the sync Playwright API).

## Report Format
Report: Status, test result, any PAGEERROR + resolution, full-suite summary, files changed, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (Spec §6.3 Reviewer — core portions):**

| Spec item | Task(s) |
|---|---|
| get next card from `get_queued_cards`; finished → congrats/overview | 1, 4 |
| show question via real `reviewer.js` `_showQuestion` | 3, 4 |
| show answer via `_showAnswer` | 1, 4 |
| ease buttons (1-4) with `describe_next_states` interval previews | 2, 4 |
| v3 answer flow `build_answer`→`answer_card`, queue advance, OpChanges broadcast | 1, 4 |
| reuse real reviewer.js + MathJax (load order, globals) | 3, 4 |
| end-to-end study proof | 5 |

Deferred to Plan 4 (documented in the header): type-in-answer, `[sound:]` audio, custom scheduling (`cardStateCustomizer` + scheduling-states RPC + state-mutation key), auto-advance, Edit button, `reviewer-bottom.js` reuse. TTS/recording out of scope.

**2. Placeholder scan:** No "TBD/TODO". The `updateToolbar`/unknown-command ignore is explicit. The Plan-2 placeholder test is explicitly updated in Task 4 Step 5 (not left dangling).

**3. Type/name consistency:** `ReviewerSession`/`load_question`/`render_answer`/`answer_current` (Task 1) used in Tasks 2/4. `show_answer_bar`/`ease_buttons_bar` (Task 2) used in Task 4. `render_page(context, body, css_files, js_files)` (Task 3) used in Task 4's route. `reviewer_page_body`/`make_reviewer_handler` (Task 4) used in routes.py. `make_reviewer_handler` returns the handler (matching `hub.set_handler(ctx, handler)`); it owns the `ReviewerSession`. Bridge `push_call(ctx, fn, args)` / `service.run` / `service.run_op(fn, initiator)` are existing APIs. `CardAnswer.Rating` import is inside `answer_current` (deferred, avoids circular import). The page registers exactly the calls the handler pushes: `_showQuestion`, `_showAnswer`, `ankiwebSetAnswerBar` (+ `ankiwebNavigate`/`ankiwebReload` already registered by bootstrap.ts).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-01-ankiweb-reviewer-core.md`. (Plan 4 — Reviewer Extras — would follow.)
