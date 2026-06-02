# ankiweb i18n — I3: Preferences form

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Steps use `- [ ]`.

**Goal:** A server-rendered `/preferences` form for the collection-level settings the Qt Preferences dialog exposes (scheduling / reviewing / editing / backups), reading `col.get_preferences()` and writing `col.set_preferences()`. i18n'd via `tr` (I1/I2). This completes the Preferences + i18n sub-project.

**Architecture:** Mirror the E4/E5 server-rendered form screens (custom_study / filtered_deck): a `render_preferences_html(col)` builds a `<form>`; submit gathers JSON and `pycmd("savePrefs:"+json)` over the WS bridge; `make_preferences_handler` merges the submitted values onto a fresh `get_preferences()` and calls `set_preferences` via `run_op` (broadcasts), then navigates back. Errors use the `ankiwebPrefsError` + `#err` in-page pattern (NOT HTTP 500 — `ws.py` swallows handler exceptions). A "Preferences" toolbar entry links to it.

**Tech Stack:** Python 3.12, `anki==25.9.4` (`col.get_preferences()` / `col.set_preferences(prefs)` → `anki.config_pb2.Preferences`; `tr` from `ankiweb.i18n`), FastAPI, pytest (`asyncio_mode=auto`). Run: `conda run -n ankiweb python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-06-02-ankiweb-preferences-i18n-design.md` (I3 section — has the verified 22-field→key table + control map).

**Verified proto (live-probed):** `col.get_preferences()` → `anki.config_pb2.Preferences` with 4 sub-messages: `.scheduling` (rollover:uint32, learn_ahead_secs:uint32, new_review_mix:enum, new_timezone:bool, day_learn_first:bool), `.reviewing` (hide_audio_play_buttons, interrupt_audio_when_answering, show_remaining_due_counts, show_intervals_on_buttons:bool; time_limit_secs:uint32; load_balancer_enabled, fsrs_short_term_with_steps_enabled:bool), `.editing` (adding_defaults_to_current_deck, paste_images_as_png, paste_strips_formatting:bool; default_search_text:str; ignore_accents_in_search, render_latex:bool), `.backups` (daily, weekly, monthly, minimum_interval_mins:uint32). `set_preferences(prefs)` returns an `OpChanges` and writes each present section's scalars wholesale — so the handler MUST merge onto a fresh `get_preferences()` and resend all 4 sections.

**Verified keys (all probed to exist; English shown):** section headers `preferences_scheduling`="Scheduling", `preferences_review`="Review" (no args), `preferences_editing`="Editing", `preferences_backups`="Backups". Plus `preferences_preferences`="Preferences" (toolbar/heading). Per-field keys + the 2 English-fallback labels are in the control map below.

---

### Task 1: `ankiweb/screens/preferences.py` — render + handler

**Files:** Create `ankiweb/screens/preferences.py`. Test: `tests/test_preferences.py` (Task 3).

- [ ] **Step 1 — render function.** Create `render_preferences_html(col)` building a `<form id='pf' onsubmit='return false;'>` with 4 `<fieldset>` sections (legends from the section keys). Import `from ankiweb.i18n import tr`. Use these controls (id = proto field name unless noted):

**scheduling** (`p = col.get_preferences().scheduling`):
| field | control | label key |
|---|---|---|
| rollover | `<input type=number id=rollover min=0 max=23>` | `preferences_next_day_starts_at` |
| learn_ahead_secs | `<input type=number id=learn_ahead_secs min=0>` | `preferences_learn_ahead_limit` |
| new_review_mix | `<select id=new_review_mix>` 3 options | `scheduling_mix_new_cards_and_reviews`(v=0) / `scheduling_show_new_cards_after_reviews`(v=1) / `scheduling_show_new_cards_before_reviews`(v=2) |
| new_timezone | INVERSE checkbox `id=legacy_timezone` checked iff `not new_timezone` | `preferences_legacy_timezone_handling` |
| day_learn_first | checkbox | `preferences_show_learning_cards_with_larger_steps` |

**reviewing**:
| field | control | label key |
|---|---|---|
| hide_audio_play_buttons | INVERSE checkbox `id=show_play_buttons` checked iff `not hide_audio_play_buttons` | `preferences_show_play_buttons_on_cards_with` |
| interrupt_audio_when_answering | checkbox | `preferences_interrupt_current_audio_when_answering` |
| show_remaining_due_counts | checkbox | `preferences_show_remaining_card_count` |
| show_intervals_on_buttons | checkbox | `preferences_show_next_review_time_above_answer` |
| time_limit_secs | `<input type=number min=0>` | `preferences_timebox_time_limit` |
| load_balancer_enabled | checkbox | **ENGLISH-FALLBACK** literal `"Enable load balancer"` (no Anki key) |
| fsrs_short_term_with_steps_enabled | checkbox | **ENGLISH-FALLBACK** literal `"Use FSRS for short-term scheduling (with steps)"` |

**editing**:
| field | control | label key |
|---|---|---|
| adding_defaults_to_current_deck | checkbox | `preferences_when_adding_default_to_current_deck` |
| paste_images_as_png | checkbox | `preferences_paste_clipboard_images_as_png` |
| paste_strips_formatting | checkbox | `preferences_paste_without_shift_key_strips_formatting` |
| default_search_text | `<input type=text>` | `preferences_default_search_text` |
| ignore_accents_in_search | checkbox | `preferences_ignore_accents_in_search` |
| render_latex | checkbox | `preferences_generate_latex_images_automatically` |

**backups**: daily/weekly/monthly/minimum_interval_mins → `<input type=number min=0>`, keys `preferences_daily_backups` / `preferences_weekly_backups` / `preferences_monthly_backups` / `preferences_minutes_between_backups`.

Heading `<h3>{tr.preferences_preferences()}</h3>`. Checkboxes: render ` checked` when the (possibly inverted) value is true. HTML-escape all `tr.` label text (use a local `e=html.escape`). default_search_text value goes in `value="{html.escape(...)}"`. Buttons: `<button id=save onclick='savePrefs()'>{tr.actions_save()}</button>` + `<button onclick="pycmd('cancel')">{tr.actions_cancel()}</button>`. An `<div id='err' style='color:#c00'></div>`.

Inline `<script>` (escape `{{`/`}}`): a `savePrefs()` that builds a payload of the PROTO field values — for the 2 inverse checkboxes invert: `new_timezone: !document.getElementById('legacy_timezone').checked`, `hide_audio_play_buttons: !document.getElementById('show_play_buttons').checked`; bools = `.checked`; numbers = `parseInt(...||'0')`; `new_review_mix = parseInt(select.value)`; `default_search_text = el.value` — then `pycmd('savePrefs:'+JSON.stringify(payload))`. Plus `window.ankiwebPrefsError = function(m){{document.getElementById('err').textContent=m;}}`.

- [ ] **Step 2 — handler.** Add `make_preferences_handler(service, hub)` returning `async def handler(arg)`:
  - `cmd, _, rest = arg.partition(":")`; if `cmd=="cancel"` → `await hub.push_call("preferences","ankiwebNavigate",["/deckbrowser"])`, return None.
  - if `cmd!="savePrefs"`: return None. `try: p=json.loads(rest) except: return None`.
  - Define `apply(col)`: `prefs = col.get_preferences()` (fresh merge base); set each field from `p` (cast: `int(...)` for uint32/enum, `bool(...)` for bools, `str(...)` for default_search_text); `return col.set_preferences(prefs)`.
  - `try: await service.run_op(apply, initiator="preferences")` `except Exception as exc: await hub.push_call("preferences","ankiwebPrefsError",[str(exc)]); return None`.
  - On success: `await hub.push_call("preferences","ankiwebNavigate",["/deckbrowser"])`; return None.

  (For uint32 fields, guard against negatives if desired, but the proto/backend will clamp/raise — the error path handles it.)

- [ ] **Step 3** — `conda run -n ankiweb python -c "import ankiweb.screens.preferences"` to confirm it imports. Commit `i18n(I3): preferences screen render + handler`.

---

### Task 2: wire route + handler + toolbar entry

**Files:** Modify `ankiweb/screens/routes.py`, `ankiweb/screens/page.py`.

- [ ] **Step 1 — route + handler registration** in `routes.py`: import `from ankiweb.screens.preferences import render_preferences_html, make_preferences_handler`; add
```python
    @router.get("/preferences", response_class=HTMLResponse)
    async def preferences_page():
        service = get_service()
        body = await service.run(render_preferences_html)
        return HTMLResponse(render_page("preferences", body))
```
and in `register_screen_handlers`: `hub.set_handler("preferences", make_preferences_handler(service, hub))`.

- [ ] **Step 2 — toolbar entry** in `page.py` `_toolbar_html()`: add `f"<a href='/preferences'>{tr.preferences_preferences()}</a>"` (place it after the Stats link, before Source). NOTE: check `tests/test_global_toolbar.py` still passes — its assertions target the 4 existing links + Source by exact `href`+label; a new link won't break substring asserts. If any test asserts an exact toolbar string/count, update it.

- [ ] **Step 3** — `conda run -n ankiweb python -m pytest tests/test_global_toolbar.py tests/test_screen_routes.py -q`. Commit `i18n(I3): /preferences route + toolbar entry`.

---

### Task 3: tests

**Files:** Create `tests/test_preferences.py`.

- [ ] **Step 1 — render + i18n + round-trip + error tests:**

```python
import json
import anki.lang
import pytest
from pathlib import Path
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.screens.preferences import render_preferences_html, make_preferences_handler


def test_render_default_english(temp_collection):
    html = render_preferences_html(temp_collection)
    assert "Next day starts at" in html      # preferences_next_day_starts_at
    assert "Learn ahead limit" in html
    assert "Enable load balancer" in html     # english fallback
    assert "id=\"rollover\"" in html or "id='rollover'" in html


def test_render_zh(temp_collection):
    anki.lang.set_lang("zh-CN")
    html = render_preferences_html(temp_collection)
    assert "设置" in html                      # preferences_preferences heading


class _Hub:
    def __init__(self): self.calls = []
    async def push_call(self, ctx, fn, args): self.calls.append((fn, args))


async def _svc(tmp_path):
    svc = CollectionService(Settings(collection_path=tmp_path / "c.anki2"))
    await svc.open()
    return svc


async def test_saveprefs_roundtrip(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_preferences_handler(svc, hub)
    base = await svc.run(lambda col: col.get_preferences())
    payload = {
        "rollover": 6, "learn_ahead_secs": 99, "new_review_mix": 2,
        "new_timezone": base.scheduling.new_timezone, "day_learn_first": True,
        "hide_audio_play_buttons": False, "interrupt_audio_when_answering": True,
        "show_remaining_due_counts": True, "show_intervals_on_buttons": True,
        "time_limit_secs": 0, "load_balancer_enabled": True,
        "fsrs_short_term_with_steps_enabled": False,
        "adding_defaults_to_current_deck": True, "paste_images_as_png": False,
        "paste_strips_formatting": False, "default_search_text": "deck:current",
        "ignore_accents_in_search": False, "render_latex": False,
        "daily": 7, "weekly": 4, "monthly": 3, "minimum_interval_mins": 45,
    }
    await handler("savePrefs:" + json.dumps(payload))
    p = await svc.run(lambda col: col.get_preferences())
    assert p.scheduling.rollover == 6
    assert p.scheduling.learn_ahead_secs == 99
    assert p.scheduling.new_review_mix == 2
    assert p.editing.default_search_text == "deck:current"
    assert p.backups.minimum_interval_mins == 45
    assert ("ankiwebNavigate", ["/deckbrowser"]) in hub.calls
    await svc.close()


async def test_saveprefs_error_uses_callback(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_preferences_handler(svc, hub)
    # rollover out of range (>23) -> backend raises -> error callback, no navigate
    base = await svc.run(lambda col: col.get_preferences())
    payload = {f.name: getattr(base.scheduling, f.name) for f in base.scheduling.DESCRIPTOR.fields}
    payload.update({f.name: getattr(base.reviewing, f.name) for f in base.reviewing.DESCRIPTOR.fields})
    payload.update({f.name: getattr(base.editing, f.name) for f in base.editing.DESCRIPTOR.fields})
    payload.update({f.name: getattr(base.backups, f.name) for f in base.backups.DESCRIPTOR.fields})
    payload["new_timezone"] = base.scheduling.new_timezone
    payload["rollover"] = 99  # invalid
    await handler("savePrefs:" + json.dumps(payload))
    fns = [c[0] for c in hub.calls]
    if "ankiwebPrefsError" in fns:           # backend validated -> error path
        assert "ankiwebNavigate" not in fns
    else:                                     # backend clamped silently -> navigated, no crash
        assert "ankiwebNavigate" in fns
    await svc.close()
```

- [ ] **Step 2** — run `conda run -n ankiweb python -m pytest tests/test_preferences.py -q`. If `test_saveprefs_error_uses_callback` reveals the backend clamps rather than raises (no validation), the test already tolerates both; keep it. Then full suite.

- [ ] **Step 3** — `conda run -n ankiweb python -m pytest -q` (all green). Commit `test(i18n): preferences form tests`.

---

## Self-Review
- **Coverage:** all 22 fields mapped (control + label) per the spec's verified table; the 2 inverse checkboxes + 2 English-fallback labels + the enum select are handled; merge-onto-fresh-get_preferences avoids clobbering; WS error pattern (no HTTP 500); toolbar entry. Default-English + zh render + round-trip + error-path tested.
- **Type/name consistency:** input ids = proto field names except the 2 inverse ones (`legacy_timezone`, `show_play_buttons`), whose JS inverts back to the proto field in the payload; handler reads payload keys = proto field names; `make_preferences_handler(service, hub)` matches the routes.py call.
- **Risk:** if `set_preferences` doesn't validate `rollover`, the error test's else-branch covers it (no crash, navigates). Verify the exact behavior at implementation time and keep whichever branch fires.
