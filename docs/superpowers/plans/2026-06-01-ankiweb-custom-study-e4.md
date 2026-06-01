# ankiweb Plan E4 — Custom Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** REBUILD Anki's "Custom Study" dialog as a server-rendered HTML form at `GET /custom-study` (the dialog is Qt-only — no SvelteKit bundle to reuse), submit the chosen option via the WS bridge to `col.sched.custom_study(...)` (broadcasting so the overview refreshes), and launch it from the overview's "Custom Study" button.

**Architecture:** A new server-rendered screen (same pattern as `overview`): `render_custom_study_html(col)` renders a single-page `<form>` with the six radio options (increase new limit / increase review limit / review forgotten / review ahead / preview new / study by card state or tag), one context-sensitive number `<input>` whose label+default+suffix change per option, and a cram sub-block (a card-state `<select>` + include/exclude tag multi-selects) shown only for the cram option — all prefilled from `col.sched.custom_study_defaults(col.decks.get_current_id())`. A small inline `<script>` toggles the cram block and on OK gathers the fields into JSON and `pycmd("submit:"+json)`. The `customstudy` WS handler parses the payload, builds a `CustomStudyRequest(deck_id=current, …)`, runs `col.sched.custom_study(req)` via `run_op` (the returned `OpChanges.study_queues=True` broadcasts), and on success `ankiwebNavigate("/overview")` — the cram/forgot/ahead/preview options CREATE a filtered deck and SELECT it as current (probed), so the overview then shows that filtered deck; on `anki.errors.CustomStudyError` ("No cards matched…") it pushes `ankiwebCustomStudyError(msg)` and stays on the form. The overview's "Custom Study" button (`pycmd("studymore")`, currently a no-op) navigates to `/custom-study`; **bonus:** the overview's "Options" button (`pycmd("opts")`, also currently a no-op) navigates to `/deck-options/{current_did}` (completing the E2 deck-options wiring from the overview).

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the server-rendered screen framework (`render_page`/`build_screen_router`/`register_screen_handlers`/`hub.set_handler`/`hub.push_call`), `col.sched.custom_study`/`custom_study_defaults`, `anki.scheduler_pb2.CustomStudyRequest`, pytest (+ Playwright). Run via `conda run -n ankiweb ...`.

**This is E4 of Sub-project E.** Spec: `docs/superpowers/specs/2026-06-01-ankiweb-specialized-screens-design.md`. E1–E3 reused the SvelteKit SPA; E4/E5 are REBUILDS (Qt-only dialogs). Next: E5 (filtered-deck options), then E6/E7 deferred.

**Grounded facts (live-probed + source-read against `/mnt/sda/git/tools/anki`):**
- `col.sched.custom_study(request: CustomStudyRequest) -> OpChanges` (returns `OpChanges` with `study_queues=True`). `col.sched.custom_study_defaults(deck_id) -> CustomStudyDefaultsResponse`.
- `CustomStudyDefaultsResponse` fields: `tags` (each `.name`/`.include`/`.exclude`), `extend_new`, `extend_review`, `available_new`, `available_review`, `available_new_in_children`, `available_review_in_children`.
- `CustomStudyRequest` fields: `deck_id`, `new_limit_delta` (int32, may be negative), `review_limit_delta` (int32), `forgot_days` (uint32), `review_ahead_days` (uint32), `preview_days` (uint32), `cram` (a `Cram`).
- `Cram` fields: `kind`, `card_limit`, `tags_to_include`, `tags_to_exclude`. **`CramKind` integer values: `CRAM_KIND_DUE=0`, `CRAM_KIND_NEW=1`, `CRAM_KIND_REVIEW=2`, `CRAM_KIND_ALL=3`.**
- The 6 Qt radio options → request fields: NEW→`new_limit_delta`, REV→`review_limit_delta`, FORGOT→`forgot_days` (default 1, Qt range 1–30), AHEAD→`review_ahead_days` (default 1), PREVIEW→`preview_days` (default 1), CRAM→`cram{kind,card_limit(default 100),tags_to_include,tags_to_exclude}`. The cram card-state list order in Qt is: New only(→NEW=1), Due only(→DUE=0), All review random(→REVIEW=2), All random no-reschedule(→ALL=3).
- **Runtime behavior (probed):** `new_limit_delta`/`review_limit_delta` keep the SAME current deck (just bump today's limit) + broadcast `study_queues`. `cram`/`forgot_days`/`review_ahead_days`/`preview_days` CREATE a filtered deck named "Custom Study Session" and SET IT as `get_current_id()`. An empty result (e.g. `forgot_days=1` with no forgotten cards) RAISES `anki.errors.CustomStudyError("No cards matched the criteria you provided.")`.
- The overview launch: the "Custom Study" button sends `pycmd("studymore")` (overview handler, currently a deferred no-op at `ankiweb/screens/overview.py`); the "Options" button sends `pycmd("opts")` (also a deferred no-op). The button only appears for NON-filtered decks (the overview already gates this via `deck.get("dyn")`).
- Screen framework: `render_page(context, body, css_files, js_files)` wraps a fragment + sets `window.__ankiwebContext` so the page's bridge connects to `/ws?context=<context>`; `register_screen_handlers` wires a WS handler per context via `hub.set_handler(ctx, handler)`; handlers drive the page via `hub.push_call(ctx, fn, args)`; `service.run_op(fn, initiator)` broadcasts the op's flags.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/screens/custom_study.py` (create) | `render_custom_study_html(col)` (the form) + `make_custom_study_handler(service, hub)` (parse → `custom_study` → nav/err) |
| `ankiweb/screens/routes.py` (modify) | import; `GET /custom-study` route; register the `customstudy` handler |
| `ankiweb/screens/overview.py` (modify) | `studymore` → nav `/custom-study`; `opts` → nav `/deck-options/{current_did}` |
| `tests/test_custom_study.py` (create) | route renders the form; WS submit (new-limit broadcast / cram filtered-deck / forgot error); overview studymore+opts nav |
| `tests/test_custom_study_integration.py` (create) | Playwright: the form renders + submitting drives the backend + navigates to /overview |

---

## Task 1: the `/custom-study` form screen + handler + overview wiring

**Files:** Create `ankiweb/screens/custom_study.py`; modify `ankiweb/screens/routes.py`, `ankiweb/screens/overview.py`; Test `tests/test_custom_study.py`.

- [ ] **Step 1: Write the failing tests** — `tests/test_custom_study.py`:
```python
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _seed(client, n=3):
    def seed(col):
        did = col.decks.id("Default")
        col.decks.set_current(did)
        for i in range(n):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = f"f{i}"; note["Back"] = f"b{i}"
            col.add_note(note, did)
        return did
    return client.portal.call(client.app.state.service.run, seed)


def test_custom_study_route_renders_form(client):
    _seed(client)
    r = client.get("/custom-study")
    assert r.status_code == 200
    body = r.text
    assert "Increase today's new card limit" in body
    assert "Study by card state or tag" in body
    assert 'name="r"' in body          # the radio group
    assert 'id="spin"' in body         # the number input


def _drain_for(ws, fn):
    m = ws.receive_json()
    while not (m["type"] == "call" and m["fn"] == fn):
        m = ws.receive_json()
    return m


def test_custom_study_new_limit_navigates_and_broadcasts(client):
    _seed(client)
    with client.websocket_connect("/ws?context=customstudy") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "customstudy",
                      "arg": "submit:" + json.dumps({"radio": 1, "value": 5})})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == ["/overview"]


def test_custom_study_cram_creates_filtered_deck(client):
    _seed(client)
    with client.websocket_connect("/ws?context=customstudy") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "customstudy",
                      "arg": "submit:" + json.dumps(
                          {"radio": 6, "value": 50, "cram_kind": 1,
                           "include": [], "exclude": []})})
        _drain_for(ws, "ankiwebNavigate")
    cur = client.portal.call(
        client.app.state.service.run,
        lambda col: (col.decks.get(col.decks.get_current_id())["name"],
                     bool(col.decks.get(col.decks.get_current_id()).get("dyn"))))
    assert cur[1] is True                       # current deck is now filtered
    assert cur[0] == "Custom Study Session"


def test_custom_study_error_when_no_cards_match(client):
    _seed(client)   # fresh new cards → none "forgotten"
    with client.websocket_connect("/ws?context=customstudy") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "customstudy",
                      "arg": "submit:" + json.dumps({"radio": 3, "value": 1})})
        m = ws.receive_json()
        seen_err = False
        for _ in range(10):
            if m["type"] == "call" and m["fn"] == "ankiwebCustomStudyError":
                seen_err = True
                assert "matched" in m["args"][0].lower() or "card" in m["args"][0].lower()
                break
            if m["type"] == "call" and m["fn"] == "ankiwebNavigate":
                pytest.fail("navigated despite CustomStudyError")
            m = ws.receive_json()
        assert seen_err


def test_overview_studymore_navigates_to_custom_study(client):
    _seed(client)
    with client.websocket_connect("/ws?context=overview") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "overview", "arg": "studymore"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == ["/custom-study"]


def test_overview_opts_navigates_to_deck_options(client):
    did = _seed(client)
    with client.websocket_connect("/ws?context=overview") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "overview", "arg": "opts"})
        m = _drain_for(ws, "ankiwebNavigate")
        assert m["args"] == [f"/deck-options/{did}"]
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_custom_study.py -v` → FAIL.

- [ ] **Step 3: Create `ankiweb/screens/custom_study.py`** — the form renderer + the WS handler:
```python
from __future__ import annotations
import html
import json


def render_custom_study_html(col) -> str:
    did = col.decks.get_current_id()
    d = col.sched.custom_study_defaults(did)
    avail_new = d.available_new + d.available_new_in_children
    avail_rev = d.available_review + d.available_review_in_children

    radios = [
        (1, "Increase today's new card limit"),
        (2, "Increase today's review card limit"),
        (3, "Review forgotten cards"),
        (4, "Review ahead"),
        (5, "Preview new cards"),
        (6, "Study by card state or tag"),
    ]
    radio_html = "".join(
        f"<div><label><input type='radio' name='r' value='{v}'"
        f"{' checked' if v == 1 else ''} onchange='onRadio()'> {html.escape(t)}</label></div>"
        for v, t in radios
    )

    kinds = [(1, "New cards only"), (0, "Due cards only"),
             (2, "All review cards in random order"),
             (3, "All cards in random order (don't reschedule)")]
    kind_opts = "".join(f"<option value='{k}'>{html.escape(t)}</option>" for k, t in kinds)
    tag_opts = "".join(
        f"<option value='{html.escape(t.name)}'>{html.escape(t.name)}</option>"
        for t in d.tags
    )

    # per-radio config: [label, default, suffix, min]
    cfg = {
        1: ["Increase today's new card limit by", d.extend_new or 0, "cards", -9999],
        2: ["Increase today's review card limit by", d.extend_review or 0, "cards", -9999],
        3: ["Review cards forgotten in the last", 1, "days", 1],
        4: ["Review ahead by", 1, "days", 1],
        5: ["Preview new cards added in the last", 1, "days", 1],
        6: ["Select", 100, "cards from the deck", 1],
    }

    body = f"""
<div class='custom-study'>
  <h3>Custom Study</h3>
  <div class='avail'>New available: {avail_new} &nbsp; Review available: {avail_rev}</div>
  <form id='cs' onsubmit='return false;'>
    {radio_html}
    <div class='spinrow' style='margin:8px 0;'>
      <span id='spinlabel'></span>
      <input type='number' id='spin' value='{cfg[1][1]}' style='width:6em;'>
      <span id='spinsuffix'></span>
    </div>
    <div id='cramblock' style='display:none;'>
      <div>Card state:
        <select id='cramkind'>{kind_opts}</select>
      </div>
      <div style='margin-top:6px;'>Require one or more of these tags:<br>
        <select id='inc' multiple size='4'>{tag_opts}</select></div>
      <div style='margin-top:6px;'>Exclude tags:<br>
        <select id='exc' multiple size='4'>{tag_opts}</select></div>
    </div>
    <div style='margin-top:10px;'>
      <button type='button' id='go' onclick='submitCs()'>OK</button>
      <button type='button' onclick="pycmd('cancel')">Cancel</button>
    </div>
    <div id='err' style='color:#c00;margin-top:8px;'></div>
  </form>
</div>
<script>
var CFG = {json.dumps(cfg)};
function selectedRadio() {{
  var els = document.getElementsByName('r');
  for (var i = 0; i < els.length; i++) if (els[i].checked) return parseInt(els[i].value);
  return 1;
}}
function onRadio() {{
  var r = selectedRadio();
  var c = CFG[r];
  document.getElementById('spinlabel').textContent = c[0];
  document.getElementById('spin').value = c[1];
  document.getElementById('spin').min = c[3];
  document.getElementById('spinsuffix').textContent = c[2];
  document.getElementById('cramblock').style.display = (r === 6) ? '' : 'none';
}}
function multiVals(id) {{
  var out = [], el = document.getElementById(id);
  for (var i = 0; i < el.options.length; i++) if (el.options[i].selected) out.push(el.options[i].value);
  return out;
}}
function submitCs() {{
  document.getElementById('err').textContent = '';
  var r = selectedRadio();
  var payload = {{radio: r, value: parseInt(document.getElementById('spin').value || '0')}};
  if (r === 6) {{
    payload.cram_kind = parseInt(document.getElementById('cramkind').value);
    payload.include = multiVals('inc');
    payload.exclude = multiVals('exc');
  }}
  pycmd('submit:' + JSON.stringify(payload));
}}
window.ankiwebCustomStudyError = function(msg) {{
  document.getElementById('err').textContent = msg;
}};
onRadio();
</script>
"""
    return body


def make_custom_study_handler(service, hub):
    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "cancel":
            await hub.push_call("customstudy", "ankiwebNavigate", ["/overview"])
            return None
        if cmd != "submit":
            return None
        try:
            p = json.loads(rest)
        except Exception:
            return None
        radio = int(p.get("radio", 1))
        value = int(p.get("value", 0))

        def build_and_run(col):
            import anki.scheduler_pb2 as sp
            did = col.decks.get_current_id()
            req = sp.CustomStudyRequest(deck_id=did)
            if radio == 1:
                req.new_limit_delta = value
            elif radio == 2:
                req.review_limit_delta = value
            elif radio == 3:
                req.forgot_days = value
            elif radio == 4:
                req.review_ahead_days = value
            elif radio == 5:
                req.preview_days = value
            elif radio == 6:
                req.cram.kind = int(p.get("cram_kind", 1))
                req.cram.card_limit = value
                req.cram.tags_to_include.extend(p.get("include", []))
                req.cram.tags_to_exclude.extend(p.get("exclude", []))
            return col.sched.custom_study(req)

        try:
            await service.run_op(build_and_run, initiator="customstudy")
        except Exception as e:
            from anki.errors import CustomStudyError
            msg = str(e) if isinstance(e, CustomStudyError) else "Could not create a custom study session."
            await hub.push_call("customstudy", "ankiwebCustomStudyError", [msg])
            return None
        await hub.push_call("customstudy", "ankiwebNavigate", ["/overview"])
        return None

    return handler
```
(NOTE: `service.run_op` runs the fn and broadcasts the op's flags. `col.sched.custom_study` raises `CustomStudyError` BEFORE returning when nothing matches; the `try/except` around `run_op` catches it, surfaces the message, and does NOT navigate. The cram/forgot/ahead/preview paths set the new filtered deck as current, so `ankiwebNavigate("/overview")` lands on it.)

- [ ] **Step 4: Wire the route + handler** — in `ankiweb/screens/routes.py`: add the import `from ankiweb.screens.custom_study import render_custom_study_html, make_custom_study_handler`; add the route inside `build_screen_router` (next to `/overview`):
```python
    @router.get("/custom-study", response_class=HTMLResponse)
    async def custom_study_page():
        service = get_service()
        body = await service.run(render_custom_study_html)
        return HTMLResponse(render_page("customstudy", body))
```
and register the handler inside `register_screen_handlers`:
```python
    hub.set_handler("customstudy", make_custom_study_handler(service, hub))
```

- [ ] **Step 5: Wire the overview buttons** — in `ankiweb/screens/overview.py` `make_overview_handler`, replace the deferred comment line with `studymore` + `opts` branches (before the final `return None`):
```python
        elif arg == "studymore":
            await hub.push_call("overview", "ankiwebNavigate", ["/custom-study"])
        elif arg == "opts":
            did = await service.run(lambda col: col.decks.get_current_id())
            await hub.push_call("overview", "ankiwebNavigate", ["/deck-options/" + str(did)])
```

- [ ] **Step 6: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_custom_study.py -v`, then regression:
`conda run -n ankiweb python -m pytest tests/test_overview.py tests/test_screen_routes.py tests/test_deck_options.py -q` (use whatever overview test file exists; if none, run `tests/test_screen_routes.py`).

- [ ] **Step 7: Commit**
```bash
git add ankiweb/screens/custom_study.py ankiweb/screens/routes.py ankiweb/screens/overview.py tests/test_custom_study.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(custom-study): server-rendered Custom Study form + custom_study handler + overview launch"
```

## Context
`/custom-study` is a server-rendered REBUILD (the Qt dialog has no web bundle). The form (radios + a context-sensitive spin + a cram sub-block with tag pickers, prefilled from `custom_study_defaults`) submits over the WS bridge; the `customstudy` handler builds a `CustomStudyRequest`, runs `col.sched.custom_study` (broadcasts `study_queues`), and navigates back to `/overview` on success (the created filtered deck is now current) or surfaces `CustomStudyError` inline on failure. The overview's "Custom Study"/"Options" buttons (both prior deferrals) now navigate to `/custom-study` and `/deck-options/{did}`.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns (incl. the exact regression test file you used for the overview, and any escaping/JS issues with the inline form script).

---

## Task 2: Playwright — the Custom Study form renders + submits + navigates

**Files:** Create `tests/test_custom_study_integration.py`.

- [ ] **Step 1: Write the test** — mirror `tests/test_deck_options_integration.py`'s `live_server` (uvicorn thread, fresh port 8133, `pytest.importorskip`, inline `sync_playwright`). Seed new cards + set the current deck. Open `/custom-study`; assert the form renders; pick the cram option, submit, and assert it navigates to `/overview` and a filtered deck was created:
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
def live_server_cs(tmp_path: Path):
    col_path = tmp_path / "c.anki2"
    col = Collection(str(col_path))
    try:
        did = col.decks.id("Default")
        col.decks.set_current(did)
        for i in range(3):
            n = col.new_note(col.models.by_name("Basic"))
            n["Front"] = f"f{i}"; n["Back"] = f"b{i}"
            col.add_note(n, did)
    finally:
        col.close()
    settings = Settings(collection_path=col_path, port=8133)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1",
                                           port=8133, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    yield "http://127.0.0.1:8133"
    server.should_exit = True
    t.join(timeout=5)


def test_custom_study_form_submits_and_navigates(live_server_cs):
    url = live_server_cs
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{url}/custom-study")
        page.wait_for_selector("#go", timeout=10000)
        assert "Custom Study" in page.inner_text("body")
        # pick the cram option (value 6), then submit
        page.check("input[name='r'][value='6']")
        page.click("#go")
        page.wait_for_url("**/overview", timeout=10000)
        assert not errors, errors
        browser.close()
```
(NOTE: the cram option always matches the seeded new cards, so it creates a filtered deck and navigates — robust. If the WS-driven navigation needs a moment, `wait_for_url` already polls. Load-bearing asserts: the form rendered (`#go` present + "Custom Study" text), no page error, and the submit navigated to `/overview`.)

- [ ] **Step 2: Run** — `conda run -n ankiweb python -m pytest tests/test_custom_study_integration.py -v` (PASS if chromium available; SKIPS if not). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 3: Commit**
```bash
git add tests/test_custom_study_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "test(custom-study): Playwright — the form renders, submits, and navigates to overview"
```

## Context
End-to-end proof the rebuilt Custom Study form works in a real browser: renders the radios/spin/cram controls, submits the cram option over the WS bridge, the backend creates the filtered deck, and the page navigates to `/overview`. The new-limit/error paths are covered by the Task-1 WS tests.

## Report Format
Status, pytest summary (Playwright skip/pass + full-suite count), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (E4 = custom study):** a server-rendered `/custom-study` form REBUILD with all six options (Task 1); submit over the WS bridge → `col.sched.custom_study` with the right `CustomStudyRequest` field per option incl. the cram `Cram{kind,card_limit,tags}` (Task 1, tested for new-limit + cram + error); broadcast via `run_op` (study_queues); navigate to `/overview` on success / surface `CustomStudyError` inline on failure (Task 1); overview "Custom Study" launch + bonus "Options"→deck-options (Task 1); Playwright render+submit+navigate proof (Task 2). The cram tag sub-flow is folded into the single form (web-natural) instead of Qt's two-step TagLimit dialog.

**2. Placeholder scan:** No TBD/TODO. The inline form JS is complete (CFG map, onRadio, submitCs, error hook). The regression test file for the overview is "whatever exists" with a `test_screen_routes.py` fallback (the implementer picks the real one).

**3. Type/name consistency:** `render_custom_study_html(col)` + `make_custom_study_handler(service, hub)` in `custom_study.py`; route `GET /custom-study` → `render_page("customstudy", body)`; handler registered under context `"customstudy"`; the page connects to `/ws?context=customstudy` and the handler pushes to the same context. `CustomStudyRequest` built with `new_limit_delta`/`review_limit_delta`/`forgot_days`/`review_ahead_days`/`preview_days`/`cram` per the radio value (1–6); `Cram.kind` uses the probed enum ints (NEW=1/DUE=0/REVIEW=2/ALL=3). overview `studymore`→`/custom-study`, `opts`→`/deck-options/{did}`. `service.run_op` broadcasts; `CustomStudyError` from `anki.errors`.

**4. Risks:** The inline `<script>` uses f-string `{{`/`}}` escaping — Step 3 shows it fully escaped; the Playwright test (Task 2) catches any JS syntax error via the `pageerror` listener. `run_op` raising `CustomStudyError` is caught around the call (the op never broadcasts on failure). The cram path always matches the seeded new cards (deterministic test). The overview buttons only render for non-filtered decks (existing gate) — the handler branches are harmless for filtered decks (no button to trigger them). `custom_study_defaults` needs a current deck — the route uses `get_current_id()`, set by the deckbrowser→overview flow (tests set it explicitly via `set_current`).
