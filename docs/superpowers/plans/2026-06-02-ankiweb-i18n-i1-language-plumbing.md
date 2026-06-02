# ankiweb i18n — I1: Language Plumbing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire a startup-chosen UI language (`ANKIWEB_LANG`) through ankiweb so the reused Anki frontend follows it, and lay a crash-proof `tr` foundation for the hand-written screens (I2) and Preferences form (I3).

**Architecture:** Add a `Settings.lang` field (env `ANKIWEB_LANG`). `CollectionService.open()` calls `anki.lang.set_lang(settings.lang or "en")` before constructing the `Collection`, which localizes `col.tr`, the process-global `tr_legacyglobal`, and the frontend's `i18n_resources`. Because `tr_legacyglobal` is `None`/uninitialized until `set_lang` runs (and opening a `Collection` does NOT initialize it), a new `ankiweb/i18n.py` self-initializes with a guarded import-time `set_lang` so code paths that render the toolbar without opening a collection (six existing tests call `render_page()` directly) never crash. All screens import `tr` from `ankiweb.i18n`.

**Tech Stack:** Python 3.12, `anki==25.9.4` (`anki.lang.set_lang` / `anki.lang.current_i18n` / `anki.lang.tr_legacyglobal`), FastAPI, pytest (`asyncio_mode=auto`). Run tests via `conda run -n ankiweb python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-06-02-ankiweb-preferences-i18n-design.md` (I1 section).

**Ground-truth facts (probed against anki==25.9.4):**
- `anki.lang.current_i18n` is `None` until `set_lang` is called; opening a `Collection` does NOT change that.
- `anki.lang.tr_legacyglobal.actions_add()` with no prior `set_lang` raises `TypeError: 'NoneType' object is not callable` (at `anki/_backend.py:192`).
- After `anki.lang.set_lang("en")`: `tr_legacyglobal.actions_add()` == `"Add"`. After `set_lang("zh-CN")`: a freshly-opened collection's `col.tr.actions_add()` == `"添加"`.
- `set_lang("")` / `set_lang("en")` / an unknown code all safely yield English without raising.
- `tr_legacyglobal` is a singleton whose backend `set_lang` mutates in place, so a bound `from anki.lang import tr_legacyglobal as tr` import tracks the active language after init.

---

### Task 1: Add `Settings.lang` (env `ANKIWEB_LANG`)

**Files:**
- Modify: `ankiweb/config.py:24-50`
- Test: `tests/test_config_lang.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_lang.py`:

```python
import os
from pathlib import Path
from ankiweb.config import Settings


def test_lang_defaults_to_empty(tmp_path: Path):
    s = Settings(collection_path=tmp_path / "c.anki2")
    assert s.lang == ""


def test_from_env_reads_ankiweb_lang(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ANKIWEB_COLLECTION", str(tmp_path / "c.anki2"))
    monkeypatch.setenv("ANKIWEB_LANG", "zh-CN")
    s = Settings.from_env()
    assert s.lang == "zh-CN"


def test_from_env_lang_absent_is_empty(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ANKIWEB_COLLECTION", str(tmp_path / "c.anki2"))
    monkeypatch.delenv("ANKIWEB_LANG", raising=False)
    s = Settings.from_env()
    assert s.lang == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n ankiweb python -m pytest tests/test_config_lang.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'lang'` or `AttributeError: 'Settings' object has no attribute 'lang'`.

- [ ] **Step 3: Add the field + env read**

In `ankiweb/config.py`, add a `lang` field to the `Settings` dataclass (after `source_url`, before `from_env`):

```python
    # UI language chosen at startup (Anki locale code, e.g. "zh-CN", "ja"). Empty = English.
    # Applied by CollectionService.open() via anki.lang.set_lang(); there is no in-UI switcher.
    lang: str = ""
```

And in `from_env`, add to the `cls(...)` call (e.g. after `source_url=...`):

```python
            lang=os.environ.get("ANKIWEB_LANG", ""),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n ankiweb python -m pytest tests/test_config_lang.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add ankiweb/config.py tests/test_config_lang.py
git commit -m "feat(i18n): add Settings.lang from ANKIWEB_LANG env"
```

---

### Task 2: Create `ankiweb/i18n.py` with guarded self-init + `tr`

**Files:**
- Create: `ankiweb/i18n.py`
- Test: `tests/test_i18n.py` (create)

**Why a guarded init:** `tr_legacyglobal` crashes until `set_lang` runs at least once, and `CollectionService.open()` (the other `set_lang` site) does NOT fire for code paths that render the toolbar without a collection. `ankiweb/i18n.py` is the import that every screen/toolbar uses for `tr`, so it is the right place to guarantee one-time English-default init. It reads `ANKIWEB_LANG` directly (it has no `Settings` instance at import time); `CollectionService.open()` later re-affirms with `settings.lang or "en"` and overrides if needed (in-place backend mutation).

- [ ] **Step 1: Write the failing test**

Create `tests/test_i18n.py`:

```python
import anki.lang


def test_ensure_lang_initializes_when_none(monkeypatch):
    # Simulate a fresh process: no language set yet.
    monkeypatch.setattr(anki.lang, "current_i18n", None, raising=False)
    monkeypatch.delenv("ANKIWEB_LANG", raising=False)
    from ankiweb.i18n import _ensure_lang
    _ensure_lang()
    assert anki.lang.current_i18n is not None
    # English default works without opening a Collection.
    assert anki.lang.tr_legacyglobal.actions_add() == "Add"


def test_tr_is_callable_without_collection():
    # Importing the module must have self-initialized; tr works with no Collection open.
    from ankiweb.i18n import tr
    assert tr.actions_add() == "Add"


def test_ensure_lang_honors_env(monkeypatch):
    monkeypatch.setattr(anki.lang, "current_i18n", None, raising=False)
    monkeypatch.setenv("ANKIWEB_LANG", "zh-CN")
    from ankiweb.i18n import _ensure_lang
    _ensure_lang()
    assert anki.lang.tr_legacyglobal.actions_add() == "添加"


def test_ensure_lang_is_idempotent_when_already_set(monkeypatch):
    # If a language is already active, _ensure_lang must NOT override it.
    anki.lang.set_lang("zh-CN")
    monkeypatch.setenv("ANKIWEB_LANG", "ja")  # would change it if guard were absent
    from ankiweb.i18n import _ensure_lang
    _ensure_lang()
    assert anki.lang.tr_legacyglobal.actions_add() == "添加"  # still zh-CN, not ja
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n ankiweb python -m pytest tests/test_i18n.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ankiweb.i18n'`.

- [ ] **Step 3: Create the module**

Create `ankiweb/i18n.py`:

```python
"""Process-wide UI translation access for ankiweb's hand-written screens.

`anki.lang.tr_legacyglobal` is a collection-free global translator, but it CRASHES
(`TypeError: 'NoneType' object is not callable`) until `anki.lang.set_lang` has run at
least once — and opening a `Collection` does NOT initialize it. Screens render the toolbar
without a `Collection` (and several tests call `render_page()` directly), so this module
guarantees a one-time, English-default `set_lang` at import. `CollectionService.open()`
still calls `set_lang(settings.lang or "en")` and overrides this default when `ANKIWEB_LANG`
is set (the backend is mutated in place).

Usage:  from ankiweb.i18n import tr   ;   tr.actions_add()
Always import `tr` from here, never from `anki.lang` directly, so the guard runs first.
"""
from __future__ import annotations
import os
import anki.lang


def _ensure_lang() -> None:
    """Idempotent: initialize the global translator to ANKIWEB_LANG (or English) exactly
    once. A no-op if a language is already active (so open() can override, and tests that
    set a language are not clobbered)."""
    if anki.lang.current_i18n is None:
        anki.lang.set_lang(os.environ.get("ANKIWEB_LANG", "") or "en")


_ensure_lang()

from anki.lang import tr_legacyglobal as tr  # noqa: E402  (must follow _ensure_lang)

__all__ = ["tr", "_ensure_lang"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n ankiweb python -m pytest tests/test_i18n.py -v`
Expected: PASS (4 passed).

Note on test isolation: `set_lang` is process-global and `tr` is a shared singleton, so these tests mutate global state. The file's **definition order** (pytest runs tests top-to-bottom) places the English assertions before the zh-CN-setting tests, so the whole file passes when run together even before Task 4 exists. Task 4's autouse fixture removes this order-dependence for the rest of the suite.

- [ ] **Step 5: Commit**

```bash
git add ankiweb/i18n.py tests/test_i18n.py
git commit -m "feat(i18n): ankiweb.i18n with guarded self-init + tr export"
```

---

### Task 3: Call `set_lang` in `CollectionService.open()`

**Files:**
- Modify: `ankiweb/collection_service.py:40-48` (the `open` method / `_open` closure)
- Test: `tests/test_collection_service_lang.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_collection_service_lang.py`:

```python
from pathlib import Path
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService


async def test_open_localizes_collection_zh(tmp_path: Path):
    svc = CollectionService(Settings(collection_path=tmp_path / "c.anki2", lang="zh-CN"))
    await svc.open()
    try:
        add = await svc.run(lambda col: col.tr.actions_add())
        assert add == "添加"
        # The frontend bundle is served from the same localized backend.
        bundle = await svc.backend_raw("i18n_resources", b"")
        assert len(bundle) > 0
    finally:
        await svc.close()


async def test_open_defaults_to_english(tmp_path: Path):
    svc = CollectionService(Settings(collection_path=tmp_path / "c.anki2"))  # lang=""
    await svc.open()
    try:
        add = await svc.run(lambda col: col.tr.actions_add())
        assert add == "Add"
    finally:
        await svc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `conda run -n ankiweb python -m pytest tests/test_collection_service_lang.py -v`
Expected: `test_open_localizes_collection_zh` FAILS (`assert 'Add' == '添加'`) because `open()` does not yet call `set_lang`. (`test_open_defaults_to_english` may pass incidentally.)

- [ ] **Step 3: Call set_lang before constructing the Collection**

In `ankiweb/collection_service.py`, change the `_open` closure inside `open()` (currently lines 44-45) so `set_lang` runs on the worker thread immediately before the `Collection` is built:

```python
        def _open() -> Collection:
            import anki.lang
            anki.lang.set_lang(self._settings.lang or "en")
            return Collection(str(path), server=False)
```

Also re-apply `set_lang` inside `reopen()`'s closure (same one line) for self-consistency with `open()` — defensive against a future second service with a different language; the single-service topology makes the inherited process-global sufficient today.

- [ ] **Step 4: Run test to verify it passes**

Run: `conda run -n ankiweb python -m pytest tests/test_collection_service_lang.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add ankiweb/collection_service.py tests/test_collection_service_lang.py
git commit -m "feat(i18n): set_lang(settings.lang or en) before opening the Collection"
```

---

### Task 4: Autouse English-default test fixture + full-suite regression check

**Files:**
- Modify: `tests/conftest.py:1-12`

**Why:** `set_lang` is process-global and sticky. Tests that select a non-English language (Task 3's zh-CN test) would otherwise leak into later tests. An autouse fixture resets every test to English first, making the default-English contract (load-bearing for I2's assertions) deterministic regardless of test order. Tests that want another language call `set_lang` themselves *after* the fixture runs.

- [ ] **Step 1: Add the autouse fixture**

In `tests/conftest.py`, add:

```python
@pytest.fixture(autouse=True)
def _default_english_lang():
    """Reset the process-global UI language to English before each test so default-English
    assertions are order-independent (set_lang is process-global and sticky). Tests that
    need another locale call anki.lang.set_lang(...) in their own body."""
    import anki.lang
    anki.lang.set_lang("en")
    yield
```

(Place it after the existing imports; `pytest` is already imported at `tests/conftest.py:2`.)

- [ ] **Step 2: Verify the zh-CN test still passes with the fixture active**

Run: `conda run -n ankiweb python -m pytest tests/test_collection_service_lang.py tests/test_i18n.py -v`
Expected: PASS — the zh-CN cases set their own language inside the test body (Settings(lang="zh-CN") → open() → set_lang, or an explicit set_lang), so the autouse English reset does not break them.

- [ ] **Step 3: Run the FULL suite (regression — no behavior change for existing English text)**

Run: `conda run -n ankiweb python -m pytest -q`
Expected: PASS — all previously-passing tests stay green (≈347 + the new I1 tests). `set_lang("en")` yields the same English text as the previous uninitialized default for `col.tr`; the only change is that `current_i18n` is now non-`None`. If anything fails, STOP and report — do not paper over it.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test(i18n): autouse set_lang(en) fixture for deterministic default-English"
```

---

## Self-Review (run after implementing all tasks)

- **Spec coverage:** I1 spec section requires (a) `Settings.lang`/`ANKIWEB_LANG` → Task 1; (b) unconditional `set_lang(settings.lang or "en")` before `Collection()` → Task 3; (c) `ankiweb/i18n.py` with guarded self-init so col-free render paths are safe + `tr` export imported by all screens → Task 2; (d) belt-and-suspenders autouse English fixture → Task 4; (e) reused frontend localizes via `i18n_resources` → covered by Task 3's `i18n_resources` smoke (same backend). The actual toolbar `tr.` substitution is I2, not I1 — I1 only makes the foundation safe.
- **Type/name consistency:** `Settings.lang` (str), `ankiweb.i18n._ensure_lang()` / `ankiweb.i18n.tr`, `anki.lang.current_i18n` / `anki.lang.set_lang` / `anki.lang.tr_legacyglobal` — used identically across tasks.
- **No placeholders:** every step has concrete code + exact run commands + expected output.

## Notes for I2/I3 (do not implement here)
- I2 will make `page.py`'s `_TOOLBAR_HTML`/`_TOOLBAR_CSS` a per-request function importing `tr` from `ankiweb.i18n`. Once that lands, the six direct-`render_page` tests (`test_license_about.py:32`, `test_global_toolbar.py:10/:18`, `test_night_mode.py:16`, `test_screens_page.py:5/:17`) rely on Task 2's self-init (and Task 4's fixture) to not crash and to read English.
- I3's Preferences submit uses the WS `ankiwebPrefsError` + `#err` pattern (no HTTP 500) and the verified 22-field→key table in the spec.
