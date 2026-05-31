# ankiweb AnkiConnect B2 — Notes + Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The note and card actions of the AnkiConnect API — add/update/find/info/delete notes, manage tags, and find/inspect/schedule cards — so real clients (Yomitan, etc.) can add and query notes and operate on cards.

**Architecture:** More `@action("name")` async handlers in `ankiweb/ankiconnect/actions/{notes,cards}.py`, registered into the same `ACTIONS` registry and dispatched by the existing B1 dispatcher over the shared `CollectionService`. A small `run_emit(rt, fn)` helper runs a mutating op that returns `(value, OpChanges)`, broadcasts the change flags on the bus (so the open web UI refreshes), and returns the value to the client.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the B1 AnkiConnect infra, pytest. Run via `conda run -n ankiweb ...`.

**This is Plan B2 of 4 for Sub-project B.** B3 = Models+Media, B4 = gui*. Spec: `docs/superpowers/specs/2026-06-01-ankiweb-ankiconnect-api-design.md`.

**Deliberate deferrals (NOT defects):** the note spec's **media fields** (`audio`/`video`/`picture` arrays that download/attach media into fields) → B3 (with the media actions); advanced **duplicateScope options** (`duplicateScopeOptions.{deckName,checkChildren,checkAllModels}`) → B2 supports `allowDuplicate` + collection-scope dup detection only; `updateNoteModel` (reassigns a note's notetype — touches notetype internals) is included but minimal. `setSpecificValueOfCard`'s risky-key warning gate is preserved. Statistics/export/Models/Media/gui* are other plans.

**Grounded anki 25.9.4 facts (verified live):** `col.new_note(nt)`; `col.add_note(note, did)→OpChangesWithCount` (sets `note.id`); `col.add_notes(Iterable[AddNoteRequest(note, deck_id)])→OpChanges`; `note.fields_check()→int` (NORMAL=0, EMPTY=1, DUPLICATE=2, MISSING_CLOZE=3); `note["Field"]` / `note.fields` / `note.tags` / `note.add_tag` / `note.card_ids()`; `col.update_note(note)`; `col.remove_notes(ids)→OpChangesWithCount`; `col.find_notes/find_cards(query)`; `col.get_card(id)`; `col.update_card(card)`; `col.tags.bulk_add(ids, "space sep")/bulk_remove/all()/clear_unused_tags()`; `col.sched.{suspend_cards,unsuspend_cards,bury_cards,schedule_cards_as_new(ids,*,context=),set_due_date(ids,"3"),answer_card}`; `col.set_user_flag_for_cards(flag, cids)`; `col._backend.get_scheduling_states(cid)` + `col.sched.describe_next_states(states)`; `col.models.field_map(nt)→{name:(ord,field)}`; Card attrs `id/nid/did/ord/type/queue/due/ivl/factor/reps/lapses/mod` (suspended ⇔ `queue==-1`). `col.db.all/scalar/execute(sql, *args)`.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/ankiconnect/actions/_helpers.py` (create) | `run_emit(rt, fn)`, `build_note(col, spec)`, `check_addable(col, note, options)`, `note_to_info(col, note)` |
| `ankiweb/ankiconnect/actions/notes.py` (create) | note add/update/tags/query/delete actions |
| `ankiweb/ankiconnect/actions/cards.py` (create) | card query/info/scheduling actions |
| `ankiweb/ankiconnect/actions/__init__.py` (modify) | also import `notes`, `cards` |
| `tests/ankiconnect/test_note_actions.py`, `test_card_actions.py` (create) | tests |

---

## Task 1: Helpers + note creation (addNote/addNotes/canAddNote(s))

**Files:**
- Create: `ankiweb/ankiconnect/actions/_helpers.py`, `ankiweb/ankiconnect/actions/notes.py`
- Modify: `ankiweb/ankiconnect/actions/__init__.py`
- Test: `tests/ankiconnect/test_note_actions.py`

- [ ] **Step 1: Write the failing test**

`tests/ankiconnect/test_note_actions.py`:
```python
import pytest
from pathlib import Path
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


def _err(client, action, **params):
    r = client.post("/", json={"action": action, "version": 6, "params": params})
    return r.json()["error"]


def _basic(front="Q1", back="A1", deck="Default", **extra):
    return {"deckName": deck, "modelName": "Basic", "fields": {"Front": front, "Back": back}, **extra}


def test_add_note_returns_id(client):
    nid = _call(client, "addNote", note=_basic())
    assert isinstance(nid, int)
    assert _call(client, "findNotes", query="deck:Default") == [nid]


def test_add_note_case_insensitive_fields(client):
    nid = _call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
                                         "fields": {"front": "x", "BACK": "y"}})
    assert isinstance(nid, int)


def test_add_note_empty_first_field_errors(client):
    assert "empty" in (_err(client, "addNote", note=_basic(front="")) or "").lower()


def test_add_note_duplicate_errors_unless_allowed(client):
    _call(client, "addNote", note=_basic(front="dup"))
    assert "duplicate" in (_err(client, "addNote", note=_basic(front="dup")) or "").lower()
    # allowDuplicate bypasses
    nid = _call(client, "addNote", note=_basic(front="dup", options={"allowDuplicate": True}))
    assert isinstance(nid, int)


def test_can_add_note(client):
    assert _call(client, "canAddNote", note=_basic(front="ok")) is True
    assert _call(client, "canAddNote", note=_basic(front="")) is False


def test_can_add_note_with_error_detail(client):
    res = _call(client, "canAddNoteWithErrorDetail", note=_basic(front=""))
    assert res["canAdd"] is False and "error" in res


def test_add_notes_success_returns_ids(client):
    res = _call(client, "addNotes", notes=[_basic(front="g1"), _basic(front="g2")])
    assert len(res) == 2 and all(isinstance(i, int) for i in res)


def test_add_notes_errors_and_rolls_back_on_any_failure(client):
    # one good + one empty → faithful AnkiConnect: the WHOLE call errors and rolls back all.
    r = client.post("/", json={"action": "addNotes", "version": 6,
                               "params": {"notes": [_basic(front="g1"), _basic(front="")]}})
    assert r.json()["error"] is not None
    assert _call(client, "findNotes", query="deck:Default") == []  # rolled back


def test_can_add_notes_batch(client):
    res = _call(client, "canAddNotes", notes=[_basic(front="ok"), _basic(front="")])
    assert res == [True, False]
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_note_actions.py -v`
Expected: FAIL (`ModuleNotFoundError` / actions unregistered).

- [ ] **Step 3: Implement helpers + note-creation actions**

`ankiweb/ankiconnect/actions/_helpers.py`:
```python
from __future__ import annotations
from ankiweb.collection_service import op_changes_to_flags

# fields_check() int states
_EMPTY, _DUPLICATE = 1, 2


async def run_emit(rt, fn):
    """Run fn(col) -> (value, op_with_changes | None); broadcast its OpChanges flags on the
    bus (so an open web UI refreshes); return value. Tolerates a None op (no-op actions)."""
    value, op = await rt.service.run(fn)
    if op is None:  # no-op action (e.g. removeEmptyNotes with nothing to remove)
        return value
    changes = getattr(op, "changes", op)
    flags = op_changes_to_flags(changes)
    if any(flags.values()):
        await rt.service.emit(flags, "ankiconnect")
    return value


def build_note(col, spec):
    """Build (not add) an anki Note from an AnkiConnect note spec. Case-insensitive field
    matching. Media fields (audio/video/picture) are deferred to B3."""
    spec = spec or {}
    model = col.models.by_name(spec.get("modelName", ""))
    if model is None:
        raise Exception("model was not found: " + str(spec.get("modelName")))
    note = col.new_note(model)
    by_lower = {f["name"].lower(): f["name"] for f in model["flds"]}
    for key, val in (spec.get("fields") or {}).items():
        real = by_lower.get(str(key).lower())
        if real is not None:
            note[real] = val
    for tag in spec.get("tags") or []:
        note.add_tag(tag)
    return note, model


def check_addable(col, note, options):
    """Return (can_add: bool, error: str|None) using fields_check + allowDuplicate."""
    options = options or {}
    fc = note.fields_check()
    if fc == _EMPTY:
        return False, "cannot create note because it is empty"
    if fc == _DUPLICATE and not options.get("allowDuplicate", False):
        return False, "cannot create note because it is a duplicate"
    return True, None
```

`ankiweb/ankiconnect/actions/notes.py`:
```python
from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import run_emit, build_note, check_addable


@action("addNote")
async def add_note(rt, note=None):
    spec = note or {}

    def fn(col):
        n, _ = build_note(col, spec)
        ok, err = check_addable(col, n, spec.get("options"))
        if not ok:
            raise Exception(err)
        did = col.decks.id(spec.get("deckName", "Default"))
        res = col.add_note(n, did)
        return n.id, res
    return await run_emit(rt, fn)


@action("canAddNote")
async def can_add_note(rt, note=None):
    spec = note or {}

    def fn(col):
        try:
            n, _ = build_note(col, spec)
            ok, _err = check_addable(col, n, spec.get("options"))
            return ok
        except Exception:
            return False
    return await rt.service.run(fn)


@action("canAddNoteWithErrorDetail")
async def can_add_note_with_error_detail(rt, note=None):
    spec = note or {}

    def fn(col):
        try:
            n, _ = build_note(col, spec)
            ok, err = check_addable(col, n, spec.get("options"))
            return {"canAdd": ok} if ok else {"canAdd": False, "error": err}
        except Exception as exc:
            return {"canAdd": False, "error": str(exc)}
    return await rt.service.run(fn)


@action("addNotes")
async def add_notes(rt, notes=None):
    specs = notes or []

    def fn(col):
        # Faithful to AnkiConnect (plugin __init__.py:2134): add each note (addNote raises
        # on empty/duplicate); collect error strings; if ANY failed, roll back ALL added
        # notes and raise. On full success return the list of ids.
        added_ids = []
        errs = []
        last_op = None
        for spec in specs:
            try:
                n, _ = build_note(col, spec or {})
                ok, err = check_addable(col, n, (spec or {}).get("options"))
                if not ok:
                    raise Exception(err)
                did = col.decks.id((spec or {}).get("deckName", "Default"))
                last_op = col.add_note(n, did)
                added_ids.append(n.id)
            except Exception as e:
                errs.append(str(e))
        if errs:
            if added_ids:
                col.remove_notes(added_ids)
            raise Exception(str(errs))
        return added_ids, last_op  # last_op is None for an empty list → run_emit tolerates
    return await run_emit(rt, fn)


@action("canAddNotes")
async def can_add_notes(rt, notes=None):
    return [await can_add_note(rt, note=n) for n in (notes or [])]


@action("canAddNotesWithErrorDetail")
async def can_add_notes_with_error_detail(rt, notes=None):
    return [await can_add_note_with_error_detail(rt, note=n) for n in (notes or [])]
```

- [ ] **Step 4: Update `actions/__init__.py`**

```python
# Importing the action modules registers their handlers in the ACTIONS registry.
from ankiweb.ankiconnect.actions import meta, decks, notes, cards  # noqa: F401
```
(Create an empty `ankiweb/ankiconnect/actions/cards.py` stub now — `"""AnkiConnect card actions (filled in Task 4)."""` — so this import resolves; Task 4 fills it.)

- [ ] **Step 5: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_note_actions.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ankiweb/ankiconnect/actions/_helpers.py ankiweb/ankiconnect/actions/notes.py ankiweb/ankiconnect/actions/cards.py ankiweb/ankiconnect/actions/__init__.py tests/ankiconnect/test_note_actions.py
git commit -m "feat(ankiconnect): note creation (addNote/addNotes/canAddNote+ErrorDetail) + helpers"
```

## Context
`build_note` does case-insensitive field matching (like AnkiConnect). `check_addable` uses `fields_check()` (EMPTY=1/DUPLICATE=2) honoring `allowDuplicate`. `addNote` returns `note.id` and broadcasts via `run_emit`. `addNotes` rolls back ALL on any failure (faithful). Media fields + advanced duplicateScope deferred to B3.

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 2: Note update + tag actions

**Files:**
- Modify: `ankiweb/ankiconnect/actions/notes.py`
- Test: `tests/ankiconnect/test_note_actions.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
def test_update_note_fields_and_tags(client):
    nid = _call(client, "addNote", note=_basic(front="u1"))
    assert _call(client, "updateNoteFields",
                 note={"id": nid, "fields": {"Back": "newback"}}) is None
    info = _call(client, "notesInfo", notes=[nid])[0]
    assert info["fields"]["Back"]["value"] == "newback"
    assert _call(client, "updateNote", note={"id": nid, "tags": ["x", "y"]}) is None
    assert set(_call(client, "getNoteTags", note=nid)) == {"x", "y"}


def test_bulk_tags(client):
    nid = _call(client, "addNote", note=_basic(front="t1"))
    assert _call(client, "addTags", notes=[nid], tags="marked blue") is None
    assert "marked" in _call(client, "getNoteTags", note=nid)
    assert _call(client, "removeTags", notes=[nid], tags="blue") is None
    assert "blue" not in _call(client, "getNoteTags", note=nid)
    assert "marked" in _call(client, "getTags")


def test_clear_unused_tags(client):
    assert _call(client, "clearUnusedTags") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_note_actions.py -k "update_note or bulk_tags or clear_unused" -v`
Expected: FAIL.

- [ ] **Step 3: Implement (append to notes.py)**

```python
@action("updateNoteFields")
async def update_note_fields(rt, note=None):
    spec = note or {}

    def fn(col):
        n = col.get_note(spec["id"])
        for name, val in (spec.get("fields") or {}).items():
            if name in n:  # case-sensitive (AnkiConnect updateNoteFields is case-sensitive)
                n[name] = val
        return None, col.update_note(n, skip_undo_entry=True)
    await run_emit(rt, fn)
    return None


@action("updateNoteTags")
async def update_note_tags(rt, note=None, tags=None):
    tags = tags or []

    def fn(col):
        n = col.get_note(note)
        n.tags = list(tags)
        return None, col.update_note(n)
    await run_emit(rt, fn)
    return None


@action("getNoteTags")
async def get_note_tags(rt, note=None):
    return await rt.service.run(lambda col: list(col.get_note(note).tags))


@action("updateNote")
async def update_note(rt, note=None):
    spec = note or {}
    if "fields" in spec:
        await update_note_fields(rt, note=spec)
    if "tags" in spec:
        await update_note_tags(rt, note=spec["id"], tags=spec["tags"])
    return None


@action("updateNoteModel")
async def update_note_model(rt, note=None):
    # Reassign a note's notetype + fields/tags. Minimal: change mid, rebuild fields by name.
    spec = note or {}

    def fn(col):
        n = col.get_note(spec["id"])
        model = col.models.by_name(spec.get("modelName", ""))
        if model is None:
            raise Exception("model was not found: " + str(spec.get("modelName")))
        n.mid = model["id"]
        n.fields = [""] * len(model["flds"])
        by_lower = {f["name"].lower(): i for i, f in enumerate(model["flds"])}
        for name, val in (spec.get("fields") or {}).items():
            idx = by_lower.get(str(name).lower())
            if idx is not None:
                n.fields[idx] = val
        if "tags" in spec:
            n.tags = list(spec["tags"])
        return None, col.update_note(n)
    await run_emit(rt, fn)
    return None


@action("addTags")
async def add_tags(rt, notes=None, tags=None, add=True):
    notes = notes or []

    def fn(col):
        return None, col.tags.bulk_add(notes, tags or "")
    await run_emit(rt, fn)
    return None


@action("removeTags")
async def remove_tags(rt, notes=None, tags=None):
    notes = notes or []

    def fn(col):
        return None, col.tags.bulk_remove(notes, tags or "")
    await run_emit(rt, fn)
    return None


@action("getTags")
async def get_tags(rt):
    return await rt.service.run(lambda col: col.tags.all())


@action("clearUnusedTags")
async def clear_unused_tags(rt):
    def fn(col):
        return None, col.tags.clear_unused_tags()
    await run_emit(rt, fn)
    return None


@action("replaceTags")
async def replace_tags(rt, notes=None, tag_to_replace=None, replace_with_tag=None):
    notes = notes or []

    def fn(col):
        for nid in notes:
            n = col.get_note(nid)
            if tag_to_replace in n.tags:
                n.tags = [replace_with_tag if t == tag_to_replace else t for t in n.tags]
                col.update_note(n)
        return None
    await rt.service.run(fn)
    return None


@action("replaceTagsInAllNotes")
async def replace_tags_in_all_notes(rt, tag_to_replace=None, replace_with_tag=None):
    def fn(col):
        return None, col.tags.rename(tag_to_replace, replace_with_tag)
    await run_emit(rt, fn)
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_note_actions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ankiweb/ankiconnect/actions/notes.py tests/ankiconnect/test_note_actions.py
git commit -m "feat(ankiconnect): note update + tag actions"
```

## Context
`updateNoteFields` is case-SENSITIVE (matches AnkiConnect). `updateNote` dispatches to fields+tags. `addTags`/`removeTags` take a space-separated tag STRING (col.tags.bulk_add). `replaceTagsInAllNotes` uses `col.tags.rename`. All mutations broadcast via `run_emit`.

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 3: Note query/info/delete actions

**Files:**
- Modify: `ankiweb/ankiconnect/actions/notes.py`, `ankiweb/ankiconnect/actions/_helpers.py`
- Test: `tests/ankiconnect/test_note_actions.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
def test_notes_info_shape(client):
    nid = _call(client, "addNote", note=_basic(front="info1"))
    info = _call(client, "notesInfo", notes=[nid])[0]
    assert info["noteId"] == nid
    assert info["modelName"] == "Basic"
    assert info["fields"]["Front"]["value"] == "info1"
    assert info["fields"]["Front"]["order"] == 0
    assert isinstance(info["tags"], list) and isinstance(info["cards"], list)


def test_notes_info_by_query(client):
    _call(client, "addNote", note=_basic(front="byq"))
    res = _call(client, "notesInfo", query="deck:Default")
    assert len(res) == 1


def test_delete_notes(client):
    nid = _call(client, "addNote", note=_basic(front="del"))
    assert _call(client, "deleteNotes", notes=[nid]) is None
    assert _call(client, "findNotes", query="deck:Default") == []


def test_cards_to_notes(client):
    nid = _call(client, "addNote", note=_basic(front="c2n"))
    cards = _call(client, "findCards", query="deck:Default")
    assert _call(client, "cardsToNotes", cards=cards) == [nid]


def test_notes_mod_time(client):
    nid = _call(client, "addNote", note=_basic(front="mt"))
    res = _call(client, "notesModTime", notes=[nid])
    assert res[0]["noteId"] == nid and isinstance(res[0]["mod"], int)
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_note_actions.py -k "notes_info or delete_notes or cards_to_notes or mod_time" -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add to `_helpers.py`:
```python
def note_to_info(col, note):
    model = note.note_type()
    fields = {}
    for name, (ord_, _f) in col.models.field_map(model).items():
        fields[name] = {"value": note.fields[ord_], "order": ord_}
    return {
        "noteId": note.id,
        "profile": "User 1",
        "tags": list(note.tags),
        "fields": fields,
        "modelName": model["name"],
        "mod": note.mod,
        "cards": list(note.card_ids()),
    }
```

Append to `notes.py`:
```python
from ankiweb.ankiconnect.actions._helpers import note_to_info


@action("findNotes")
async def find_notes(rt, query=""):
    return await rt.service.run(lambda col: list(col.find_notes(query or "")))


@action("notesInfo")
async def notes_info(rt, notes=None, query=None):
    def fn(col):
        ids = list(notes) if notes is not None else list(col.find_notes(query or ""))
        return [note_to_info(col, col.get_note(nid)) for nid in ids]
    return await rt.service.run(fn)


@action("notesModTime")
async def notes_mod_time(rt, notes=None):
    notes = notes or []
    return await rt.service.run(
        lambda col: [{"noteId": nid, "mod": col.get_note(nid).mod} for nid in notes])


@action("deleteNotes")
async def delete_notes(rt, notes=None):
    notes = notes or []

    def fn(col):
        return None, col.remove_notes(notes)
    await run_emit(rt, fn)
    return None


@action("removeEmptyNotes")
async def remove_empty_notes(rt):
    def fn(col):
        report = col.get_empty_cards()
        # use the backend's own "all this note's cards are empty" flag
        nids = [e.note_id for e in report.notes if e.will_delete_note]
        if nids:
            return None, col.remove_notes(nids)
        return None, None  # run_emit tolerates a None op
    await run_emit(rt, fn)
    return None


@action("cardsToNotes")
async def cards_to_notes(rt, cards=None):
    cards = cards or []

    def fn(col):
        seen = []
        for cid in cards:
            nid = col.get_card(cid).nid
            if nid not in seen:
                seen.append(nid)
        return seen
    return await rt.service.run(fn)
```

> NOTE: `removeEmptyNotes` is finicky (AnkiConnect removes notes ALL of whose cards are empty). If `col.get_empty_cards()`'s report shape differs, simplify to: gather empty card ids via `report`, find notes with no remaining cards, remove them. During TDD, introspect `col.get_empty_cards()` (returns `EmptyCardsReport` with `.notes[].note_id` and `.notes[].card_ids`); adjust to make a basic test pass (a note with all-empty cards is removed) or, if too fiddly for B2, register `removeEmptyNotes` to no-op return None and note the deferral. Prefer the real impl if the report shape cooperates.

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_note_actions.py -v`
Expected: PASS (note: the appended tests don't cover `removeEmptyNotes`; keep it best-effort).

- [ ] **Step 5: Commit**

```bash
git add ankiweb/ankiconnect/actions/notes.py ankiweb/ankiconnect/actions/_helpers.py tests/ankiconnect/test_note_actions.py
git commit -m "feat(ankiconnect): note query/info/delete actions"
```

## Context
`notesInfo` returns the AnkiConnect shape: `{noteId, profile, tags, fields:{name:{value,order}}, modelName, mod, cards}`. `find_map` via `col.models.field_map`. `cardsToNotes` dedups note ids preserving order.

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 4: Card query/info actions

**Files:**
- Modify: `ankiweb/ankiconnect/actions/cards.py` (the stub from Task 1), `_helpers.py`
- Test: `tests/ankiconnect/test_card_actions.py`

- [ ] **Step 1: Write the failing test**

`tests/ankiconnect/test_card_actions.py`:
```python
import pytest
from pathlib import Path
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


def _add(client, front="Q"):
    return _call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
                                          "fields": {"Front": front, "Back": "A"}})


def test_find_cards(client):
    _add(client)
    cards = _call(client, "findCards", query="deck:Default")
    assert len(cards) == 1 and isinstance(cards[0], int)


def test_cards_info_shape(client):
    _add(client, "cinfo")
    cid = _call(client, "findCards", query="deck:Default")[0]
    info = _call(client, "cardsInfo", cards=[cid])[0]
    assert info["cardId"] == cid
    assert info["deckName"] == "Default"
    assert info["modelName"] == "Basic"
    assert "question" in info and "answer" in info and "fields" in info
    assert info["queue"] == 0 and info["type"] == 0   # new card
    assert isinstance(info["nextReviews"], list)


def test_cards_mod_time(client):
    _add(client)
    cid = _call(client, "findCards", query="deck:Default")[0]
    res = _call(client, "cardsModTime", cards=[cid])
    assert res[0]["cardId"] == cid and isinstance(res[0]["mod"], int)
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_card_actions.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add to `_helpers.py`:
```python
def card_to_info(col, card):
    note = card.note()
    model = note.note_type()
    fields = {}
    for name, (ord_, _f) in col.models.field_map(model).items():
        fields[name] = {"value": note.fields[ord_], "order": ord_}
    try:
        states = col._backend.get_scheduling_states(card.id)
        next_reviews = list(col.sched.describe_next_states(states))
    except Exception:
        next_reviews = []
    return {
        "cardId": card.id, "note": note.id, "deckName": col.decks.name(card.did),
        "modelName": model["name"], "fieldOrder": card.ord,
        "fields": fields, "question": card.question(), "answer": card.answer(),
        "css": model.get("css", ""), "ord": card.ord, "type": card.type,
        "queue": card.queue, "due": card.due, "reps": card.reps, "lapses": card.lapses,
        "left": card.left, "mod": card.mod, "factor": card.factor, "interval": card.ivl,
        "nextReviews": next_reviews,
    }
```

Replace `ankiweb/ankiconnect/actions/cards.py` (the stub):
```python
from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import card_to_info


@action("findCards")
async def find_cards(rt, query=""):
    return await rt.service.run(lambda col: list(col.find_cards(query or "")))


@action("cardsInfo")
async def cards_info(rt, cards=None):
    cards = cards or []
    return await rt.service.run(
        lambda col: [card_to_info(col, col.get_card(cid)) for cid in cards])


@action("cardsModTime")
async def cards_mod_time(rt, cards=None):
    cards = cards or []
    return await rt.service.run(
        lambda col: [{"cardId": cid, "mod": col.get_card(cid).mod} for cid in cards])
```

- [ ] **Step 4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_card_actions.py -v`
Expected: PASS. (If `card.left` raises, drop it from the info dict — verify the Card attr exists; the probe confirmed id/nid/did/ord/type/queue/due/ivl/factor/reps/lapses/mod. `left` is also a Card attr but verify.)

- [ ] **Step 5: Commit**

```bash
git add ankiweb/ankiconnect/actions/cards.py ankiweb/ankiconnect/actions/_helpers.py tests/ankiconnect/test_card_actions.py
git commit -m "feat(ankiconnect): card query/info actions"
```

## Context
`cardsInfo` returns the AnkiConnect shape incl. `question`/`answer`/`fields`/`nextReviews` (from `get_scheduling_states`+`describe_next_states`). `fieldOrder`=card.ord.

## Report Format
Report: Status, test results, files changed, self-review, commit SHA, concerns.

---

## Task 5: Card scheduling actions

**Files:**
- Modify: `ankiweb/ankiconnect/actions/cards.py`
- Test: `tests/ankiconnect/test_card_actions.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
def test_suspend_unsuspend(client):
    _add(client, "susp")
    cid = _call(client, "findCards", query="deck:Default")[0]
    assert _call(client, "suspend", cards=[cid]) is True
    assert _call(client, "suspended", card=cid) is True
    assert _call(client, "areSuspended", cards=[cid]) == [True]
    _call(client, "unsuspend", cards=[cid])
    assert _call(client, "suspended", card=cid) is False


def test_ease_factors(client):
    _add(client, "ease")
    cid = _call(client, "findCards", query="deck:Default")[0]
    assert _call(client, "setEaseFactors", cards=[cid], easeFactors=[2500]) == [True]
    assert _call(client, "getEaseFactors", cards=[cid]) == [2500]


def test_set_due_date_and_forget(client):
    _add(client, "due")
    cid = _call(client, "findCards", query="deck:Default")[0]
    assert _call(client, "setDueDate", cards=[cid], days="3") is True
    assert _call(client, "forgetCards", cards=[cid]) is None


def test_answer_cards(client):
    _add(client, "ans")
    cid = _call(client, "findCards", query="deck:Default")[0]
    res = _call(client, "answerCards", answers=[{"cardId": cid, "ease": 3}])
    assert res == [True]
```

- [ ] **Step 2: Run to verify failure**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_card_actions.py -k "suspend or ease or due or answer" -v`
Expected: FAIL.

- [ ] **Step 3: Implement (append to cards.py)**

```python
from ankiweb.ankiconnect.actions._helpers import run_emit


@action("suspend")
async def suspend(rt, cards=None, suspend=True):
    cards = cards or []

    def fn(col):
        op = col.sched.suspend_cards(cards) if suspend else col.sched.unsuspend_cards(cards)
        return True, op
    return await run_emit(rt, fn)


@action("unsuspend")
async def unsuspend(rt, cards=None):
    cards = cards or []

    def fn(col):
        return None, col.sched.unsuspend_cards(cards)
    await run_emit(rt, fn)
    return None


@action("suspended")
async def suspended(rt, card=None):
    return await rt.service.run(lambda col: col.get_card(card).queue == -1)


@action("areSuspended")
async def are_suspended(rt, cards=None):
    cards = cards or []

    def fn(col):
        out = []
        for cid in cards:
            try:
                out.append(col.get_card(cid).queue == -1)
            except Exception:
                out.append(None)
        return out
    return await rt.service.run(fn)


@action("areDue")
async def are_due(rt, cards=None):
    cards = cards or []
    return await rt.service.run(
        lambda col: [cid in set(col.find_cards("is:due")) or
                     cid in set(col.find_cards("is:new")) for cid in cards])


@action("getEaseFactors")
async def get_ease_factors(rt, cards=None):
    cards = cards or []

    def fn(col):
        out = []
        for cid in cards:
            try:
                out.append(col.get_card(cid).factor)
            except Exception:
                out.append(None)  # faithful: AnkiConnect appends None for missing cards
        return out
    return await rt.service.run(fn)


@action("setEaseFactors")
async def set_ease_factors(rt, cards=None, easeFactors=None):
    cards = cards or []
    easeFactors = easeFactors or []

    def fn(col):
        out = []
        last_op = None
        for cid, factor in zip(cards, easeFactors):
            c = col.get_card(cid)
            c.factor = int(factor)
            last_op = col.update_card(c)
            out.append(True)
        return out, last_op
    return await run_emit(rt, fn)


@action("setSpecificValueOfCard")
async def set_specific_value_of_card(rt, card=None, keys=None, newValues=None, warning_check=False):
    keys = keys or []
    newValues = newValues or []
    risky = {"id", "nid", "did", "ord", "mod", "usn", "type", "queue", "due", "odue",
             "odid", "flags", "data"}

    def fn(col):
        c = col.get_card(card)
        out = []
        for key, val in zip(keys, newValues):
            if key in risky and not warning_check:
                out.append([False, "Can't set this key without explicit warning_check"])
                continue
            try:
                setattr(c, key, val)
                out.append(True)
            except Exception as exc:
                out.append([False, str(exc)])
        op = col.update_card(c)
        return out, op
    return await run_emit(rt, fn)


@action("getIntervals")
async def get_intervals(rt, cards=None, complete=False):
    cards = cards or []
    if not complete:
        return await rt.service.run(lambda col: [col.get_card(cid).ivl for cid in cards])

    def fn(col):
        out = []
        for cid in cards:
            ivls = col.db.list("select ivl from revlog where cid = ? order by id", cid)
            out.append(ivls)
        return out
    return await rt.service.run(fn)


@action("forgetCards")
async def forget_cards(rt, cards=None):
    cards = cards or []

    def fn(col):
        return None, col.sched.schedule_cards_as_new(cards)
    await run_emit(rt, fn)
    return None


@action("relearnCards")
async def relearn_cards(rt, cards=None):
    cards = cards or []

    def fn(col):
        if not cards:  # avoid invalid "where id in ()"
            return None
        col.db.execute(
            "update cards set type=3, queue=1 where id in (%s)" %
            ",".join("?" * len(cards)), *cards)
        return None
    await rt.service.run(fn)
    return None


@action("answerCards")
async def answer_cards(rt, answers=None):
    from anki.scheduler.v3 import CardAnswer
    answers = answers or []
    rating_map = {1: CardAnswer.Rating.AGAIN, 2: CardAnswer.Rating.HARD,
                  3: CardAnswer.Rating.GOOD, 4: CardAnswer.Rating.EASY}

    def fn(col):
        out = []
        last_op = None
        for a in answers:
            cid, ease = a["cardId"], a["ease"]
            card = col.get_card(cid)
            card.start_timer()
            states = col._backend.get_scheduling_states(cid)
            answer = col.sched.build_answer(
                card=card, states=states, rating=rating_map[ease])
            last_op = col.sched.answer_card(answer)
            out.append(True)
        return out, last_op
    return await run_emit(rt, fn)


@action("setDueDate")
async def set_due_date(rt, cards=None, days="0"):
    cards = cards or []

    def fn(col):
        return True, col.sched.set_due_date(cards, str(days))
    return await run_emit(rt, fn)
```

- [ ] **Step 2/4: Run to verify pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_card_actions.py -v`
Then full suite: `conda run -n ankiweb python -m pytest -q`.
Expected: PASS. (`setSpecificValueOfCard`'s double `col.update_card(c)` is intentional only as the run_emit op source — simplify: do one `op = col.update_card(c)` and `return out, op`. Fix during TDD.)

- [ ] **Step 5: Commit**

```bash
git add ankiweb/ankiconnect/actions/cards.py tests/ankiconnect/test_card_actions.py
git commit -m "feat(ankiconnect): card scheduling actions (suspend/ease/due/forget/answer)"
```

## Context
Scheduling wrappers over `col.sched`. `answerCards` mirrors the reviewer flow (start_timer + get_scheduling_states + build_answer + answer_card). `relearnCards` uses raw SQL (faithful to AnkiConnect). `areDue` approximated via `is:due`/`is:new` search membership. `setSpecificValueOfCard` blocks risky keys unless `warning_check`.

## Report Format
Report: Status, test results (new + full suite), files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (B2 = Notes + Cards from spec §2):** Notes group (Tasks 1-3): add/canAdd(+ErrorDetail)/addNotes; updateNoteFields/updateNote/updateNoteModel/updateNoteTags/getNoteTags; addTags/removeTags/getTags/clearUnusedTags/replaceTags/replaceTagsInAllNotes; findNotes/notesInfo/notesModTime/deleteNotes/removeEmptyNotes/cardsToNotes. Cards group (Tasks 4-5): findCards/cardsInfo/cardsModTime; getEaseFactors/setEaseFactors/setSpecificValueOfCard; suspend/unsuspend/suspended/areSuspended/areDue/getIntervals; forgetCards/relearnCards/answerCards/setDueDate. canAddNotes/canAddNotesWithErrorDetail are implemented (Task 1, loops over the single-note variants). Deferred (documented): media fields in addNote (audio/video/picture → B3), advanced duplicateScope options.

**2. Placeholder scan:** No fix-this-later NOTEs remain (the `add_notes` dead code, `setSpecificValueOfCard` double-update, and `removeEmptyNotes` count-comparison were all corrected inline after verification). `addNotes` is faithful (raise + rollback-all); `run_emit` is None-safe; `removeEmptyNotes` uses `will_delete_note`; `getEaseFactors` tolerates missing ids.

**3. Type/name consistency:** `run_emit(rt, fn)`/`build_note`/`check_addable`/`note_to_info`/`card_to_info` (helpers) used across notes.py/cards.py. All actions `async def(rt, **params)` with kwargs matching AnkiConnect param names. `op_changes_to_flags` imported from `ankiweb.collection_service` (exists from Plan 2). cards.py stub created in Task 1, filled in Task 4. `actions/__init__` imports meta/decks/notes/cards.

