# ankiweb Plan E6c — AnkiConnect Import/Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the AnkiConnect HTTP actions `importPackage(path)` and `exportPackage(deck, path, includeSched=False)` — replicating AnkiConnect's contract (server-side filesystem paths; `True`/`False` returns) while running on the collection executor.

**Architecture:** Two `@action` handlers in a new `ankiweb/ankiconnect/actions/import_export.py`, registered via `actions/__init__.py`. **Implementation note (deviation from the spec, justified by evidence):** the E6 spec proposed the legacy `anki.importing.AnkiPackageImporter` / `anki.exporting.AnkiPackageExporter`. Probing showed the **legacy `AnkiPackageImporter.run()` CRASHES on the headless backend** — `AttributeError: 'NoneType' object has no attribute 'strip_html'` because its logging path calls `anki.lang.current_i18n.strip_html(...)` and the global i18n is None for a bare `Collection()` (Qt initializes it; we don't). So both actions use the **modern backend API** (`col.import_anki_package` / `col.export_anki_package`) — which is robust headless (it's what E6a/E6b use) and produces the **identical observable contract** (a `.apkg` is written/read; the action returns `True`/`False`). This preserves AnkiConnect API compatibility while avoiding the crash. `exportPackage` returns `False` for an unknown deck (faithful to upstream's `{result:False}` branch); `importPackage` broadcasts the import's `OpChanges` (via `run_emit`) so an open web UI refreshes. The upstream `startEditing()` (a Qt `requireReset`) is intentionally dropped (no Qt mainwindow), consistent with B1–B4.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the AnkiConnect action registry (`@action`, `Runtime`, `rt.service.run`, the `run_emit` helper), `anki.import_export_pb2.{ImportAnkiPackageRequest, ExportLimit, ExportAnkiPackageOptions}`, pytest. Run via `conda run -n ankiweb ...`.

**This is E6c of Sub-project E6** (import/export) — the final plan. Spec: `docs/superpowers/specs/2026-06-02-ankiweb-import-export-e6-design.md`. Builds on E6a/E6b (merged). API-only (no GUI → no Playwright).

**Grounded facts (live-probed):**
- `col.decks.by_name("NoSuchDeck")` returns `None` (→ `exportPackage` returns `False`).
- Modern export of a deck (probed): `lim = ExportLimit(); lim.deck_id = d["id"]`; `col.export_anki_package(out_path=path, options=ExportAnkiPackageOptions(with_scheduling=includeSched, with_media=True, with_deck_configs=False, legacy=True), limit=lim)` → wrote a 59 KB `.apkg`, count=2.
- Modern import (probed): `col.import_anki_package(ImportAnkiPackageRequest(package_path=path))` with EMPTY options works — note_count 0→2, `resp.changes.note=True`, NO crash. (`ImportResponse` has `.changes`.)
- The legacy `AnkiPackageImporter(col, path).run()` RAISES `AttributeError('NoneType' ... strip_html')` headless — DO NOT use it.
- AnkiConnect action pattern (`ankiweb/ankiconnect/`): `@action("name")` from `registry`; handler `async def fn(rt, **params)`; `rt.service.run(fn)` runs `fn(col)` on the executor; `run_emit(rt, fn)` (from `actions/_helpers.py`) runs `fn(col)->(value, op_with_changes|None)`, broadcasts the op's `OpChanges` flags, returns value. Modules register by being imported in `actions/__init__.py`. Tests: `create_ankiconnect_app(Settings(...))` + `_call(client, action, **params)` posting `{"action","version":6,"params"}` to `/`. `addNote`/`findNotes`/`deleteNotes` actions exist (B2).

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/ankiconnect/actions/import_export.py` (create) | `@action("exportPackage")` + `@action("importPackage")` (modern backend API) |
| `ankiweb/ankiconnect/actions/__init__.py` (modify) | import the new module so its actions register |
| `tests/ankiconnect/test_import_export_actions.py` (create) | unknown-deck→False; export→file; export→delete→importPackage restores the notes |

---

## Task 1: the `importPackage` + `exportPackage` actions

**Files:** Create `ankiweb/ankiconnect/actions/import_export.py`; modify `ankiweb/ankiconnect/actions/__init__.py`; Test `tests/ankiconnect/test_import_export_actions.py`.

- [ ] **Step 1: Write the failing tests** — `tests/ankiconnect/test_import_export_actions.py`:
```python
import os
from pathlib import Path
import pytest
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


def test_export_package_unknown_deck_returns_false(client, tmp_path):
    out = str(tmp_path / "x.apkg")
    assert _call(client, "exportPackage", deck="NoSuchDeck", path=out) is False
    assert not os.path.exists(out)


def test_export_package_writes_file(client, tmp_path):
    for i in range(2):
        _call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
              "fields": {"Front": f"f{i}", "Back": f"b{i}"}})
    out = str(tmp_path / "deck.apkg")
    assert _call(client, "exportPackage", deck="Default", path=out, includeSched=False) is True
    assert os.path.exists(out) and os.path.getsize(out) > 0


def test_export_then_reimport_restores_notes(client, tmp_path):
    nids = [_call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
                  "fields": {"Front": f"f{i}", "Back": f"b{i}"}}) for i in range(2)]
    out = str(tmp_path / "deck.apkg")
    assert _call(client, "exportPackage", deck="Default", path=out) is True
    # delete the notes, then re-import the package to restore them
    _call(client, "deleteNotes", notes=nids)
    assert _call(client, "findNotes", query="front:f0") == []
    assert _call(client, "importPackage", path=out) is True
    assert len(_call(client, "findNotes", query="front:f0")) == 1
```
(NOTE: `front:f0` is a field search matching the first note. After delete it's empty; after re-import it returns 1. This proves `importPackage` actually adds notes back — the legacy importer would have crashed here.)

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/ankiconnect/test_import_export_actions.py -v` → FAIL (actions not registered).

- [ ] **Step 3: Create `ankiweb/ankiconnect/actions/import_export.py`**:
```python
from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import run_emit


@action("exportPackage")
async def export_package(rt, deck=None, path=None, includeSched=False):
    """Export a deck to a .apkg at a server-side path. Returns True, or False if the
    deck name is unknown (faithful to AnkiConnect). Uses the modern backend export
    (the legacy AnkiPackageImporter crashes headless; the exporter contract is identical)."""
    def fn(col):
        import anki.import_export_pb2 as ie
        d = col.decks.by_name(deck)
        if d is None:
            return False
        lim = ie.ExportLimit()
        lim.deck_id = d["id"]
        opts = ie.ExportAnkiPackageOptions(
            with_scheduling=bool(includeSched), with_media=True,
            with_deck_configs=False, legacy=True)
        col.export_anki_package(out_path=path, options=opts, limit=lim)
        return True
    return await rt.service.run(fn)


@action("importPackage")
async def import_package(rt, path=None):
    """Import a .apkg from a server-side path. Returns True; broadcasts the import's
    OpChanges so an open web UI refreshes. Uses the modern backend import (the legacy
    AnkiPackageImporter.run() raises on the headless backend — anki.lang.current_i18n is None)."""
    def fn(col):
        import anki.import_export_pb2 as ie
        resp = col.import_anki_package(ie.ImportAnkiPackageRequest(package_path=path))
        return True, resp
    return await run_emit(rt, fn)
```

- [ ] **Step 4: Register the module** — in `ankiweb/ankiconnect/actions/__init__.py`, add `import_export` to the import line:
```python
from ankiweb.ankiconnect.actions import meta, decks, notes, cards, models, media, gui, import_export  # noqa: F401
```

- [ ] **Step 5: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/ankiconnect/test_import_export_actions.py -v`, then regression: `conda run -n ankiweb python -m pytest tests/ankiconnect/ -q`.

- [ ] **Step 6: Commit**
```bash
git add ankiweb/ankiconnect/actions/import_export.py ankiweb/ankiconnect/actions/__init__.py tests/ankiconnect/test_import_export_actions.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(ankiconnect): importPackage + exportPackage actions (modern backend API, faithful contract)"
```

## Context
`exportPackage(deck, path, includeSched)` and `importPackage(path)` complete the AnkiConnect import/export surface. Both take server-side paths (faithful to AnkiConnect's local-first contract — the server is the user's machine). They use the modern backend API rather than the legacy `anki.importing`/`anki.exporting` classes because the legacy `AnkiPackageImporter.run()` raises `AttributeError` on the headless backend (`anki.lang.current_i18n` is None); the observable contract (file written/read, `True`/`False` return) is identical. `importPackage` broadcasts the import's `OpChanges` (via `run_emit`) so an open web UI refreshes; `exportPackage` mutates nothing. The upstream Qt `startEditing()` wrapper is dropped (no Qt mainwindow).

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns (incl. confirmation the modern API round-trip restored notes and `exportPackage` returns False for an unknown deck).

---

## Self-Review

**1. Spec coverage (E6c = AnkiConnect import/export):** `exportPackage(deck, path, includeSched)` → deck `.apkg` export, unknown deck → `False` (Task 1, both tested); `importPackage(path)` → import + broadcast, returns `True` (Task 1, tested via export→delete→reimport-restores). Both on the collection executor; server-side paths; `startEditing` dropped. **Justified deviation:** modern backend API instead of the legacy classes (the legacy importer crashes headless — probed) — documented in the architecture + inline docstrings; contract preserved.

**2. Placeholder scan:** No TBD/TODO. Both handlers are complete; the test proves the full round-trip (not just registration).

**3. Type/name consistency:** `@action("exportPackage")`/`@action("importPackage")` in `import_export.py`; registered via `actions/__init__.py`. `export_package` uses `col.decks.by_name` + `ie.ExportLimit().deck_id` + `ie.ExportAnkiPackageOptions(...)` + `col.export_anki_package(out_path=, options=, limit=)` → `rt.service.run`. `import_package` uses `col.import_anki_package(ie.ImportAnkiPackageRequest(package_path=path))` returning `ImportResponse` (has `.changes`) → `run_emit(rt, fn)` (fn returns `(True, resp)`). Matches the probed signatures + the existing action/`run_emit` conventions.

**4. Risks:** The legacy-importer headless crash is avoided by the modern API (the central decision — documented). `import_anki_package` with empty options uses backend defaults (probed working). Server-side paths are unconstrained by design (faithful to AnkiConnect; the local-first single-user model — the server IS the user's machine), unlike the GUI import's temp-dir confinement. `export_package` returns `False` (not an error) for an unknown deck, preserving the `{result:False, error:null}` contract. The round-trip test deletes then re-imports into the SAME collection (guids no longer present → re-added), proving import adds notes. No broadcast on export (mutates nothing); `importPackage` broadcasts via `run_emit`.
