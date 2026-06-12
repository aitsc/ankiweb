# removeDuplicateNotes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an ankiweb-original AnkiConnect extra action `POST /extra_actions/removeDuplicateNotes` that finds notes in a deck (and its subdecks) that duplicate another across ALL fields within the same note type, and deletes the newer copies (keeping the oldest), with a `dryRun` preview.

**Architecture:** Mirrors the existing extra-action pattern (`deleteModel`, `extendCardLimits`): a pydantic params model in `schemas/extra.py`, an `@extra_action(...)` async handler in a new `extra_actions/notes.py` whose body is `fn(col) -> (result_dict, op_or_None)` run through `run_emit` (so the `OpChanges` from `remove_notes` broadcasts and an open web UI refreshes), registered by importing the module in `extra_actions/__init__.py`. The dedup key is `(mid, tuple(strip_html_media(field) for each field))`; per group keep the smallest `nid` (oldest) and delete the rest. No `app.py` change is needed — the router auto-builds from `EXTRA_ACTION_SPECS`.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, anki 25.9.4 (pinned). Run everything in the `ankiweb` conda env (`conda run -n ankiweb ...`).

---

## File Structure

- **Create** `ankiweb/ankiconnect/extra_actions/notes.py` — the `removeDuplicateNotes` handler (one responsibility: deck-scoped all-fields note de-duplication).
- **Modify** `ankiweb/ankiconnect/schemas/extra.py` — append `RemoveDuplicateNotesParams`.
- **Modify** `ankiweb/ankiconnect/extra_actions/__init__.py` — import the new `notes` module so the action registers.
- **Modify** `tests/ankiconnect/test_extra_actions.py` — add a `_add_note` helper and the test cases.

No change to `ankiweb/ankiconnect/app.py` (it already imports the `extra_actions` package at line 14 and builds the router at line 112).

### Key verified facts (anki 25.9.4, this env)

- `from anki.utils import ids2str, split_fields, strip_html_media` and `from anki.collection import SearchNode` all import.
- `strip_html_media("<b>Q</b>[sound:a.mp3] x")` → `"Q[sound:a.mp3] x"` (HTML tags stripped, `[sound:]` text preserved). It needs `anki.lang.current_i18n`, which `CollectionService.open()` initialises via `set_lang(...)` before any `fn(col)` runs — safe at runtime and in tests.
- `col.remove_notes(nids)` returns `OpChangesWithCount`; `run_emit` reads `.changes` and `op_changes_to_flags(...)["note"] is True`, so it broadcasts.
- `nid` is the creation-time ms timestamp and is strictly increasing across rapid `add_note` calls, so smallest nid == oldest.
- `ids2str([])` returns `"()"`, which makes `where id in ()` invalid SQL — the implementation MUST skip the DB query when there are no nids.
- `AddNoteSpec` has `options.allowDuplicate` (bool), so tests can create duplicate notes via `/actions/addNote`.

---

## Task 1: Schema, handler, registration + core behaviour tests

**Files:**
- Modify: `ankiweb/ankiconnect/schemas/extra.py`
- Create: `ankiweb/ankiconnect/extra_actions/notes.py`
- Modify: `ankiweb/ankiconnect/extra_actions/__init__.py`
- Test: `tests/ankiconnect/test_extra_actions.py`

- [ ] **Step 1: Write the failing tests**

Add a helper near the top of `tests/ankiconnect/test_extra_actions.py` (just after the existing `_model_names` function):

```python
def _add_note(client, deck, model, fields):
    """Add a note (always allowing duplicates) and return its noteId."""
    r = _post(client, "/actions/addNote",
              note={"deckName": deck, "modelName": model, "fields": fields,
                    "options": {"allowDuplicate": True}})
    return r["result"]
```

Append these tests at the end of the file:

```python
# ----- removeDuplicateNotes (all-fields, deck-scoped de-duplication) -----
def test_remove_duplicate_notes_keeps_oldest(client):
    _post(client, "/actions/createDeck", deck="Dup")
    a = _add_note(client, "Dup", "Basic", {"Front": "Q", "Back": "A"})
    b = _add_note(client, "Dup", "Basic", {"Front": "Q", "Back": "A"})
    c = _add_note(client, "Dup", "Basic", {"Front": "Q", "Back": "A"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="Dup")["result"]
    assert r["duplicateGroups"] == 1
    assert r["duplicateNotes"] == 2
    assert r["deleted"] == 2
    assert r["dryRun"] is False
    assert r["notesScanned"] == 3
    assert r["groups"][0]["model"] == "Basic"
    assert r["groups"][0]["kept"] == a                      # oldest survives
    assert r["groups"][0]["deleted"] == [b, c]              # newer copies, ascending nid
    remaining = client.post("/actions/findNotes", json={"query": "deck:Dup"}).json()["result"]
    assert remaining == [a]


def test_remove_duplicate_notes_dry_run(client):
    _post(client, "/actions/createDeck", deck="DupDry")
    a = _add_note(client, "DupDry", "Basic", {"Front": "Q", "Back": "A"})
    b = _add_note(client, "DupDry", "Basic", {"Front": "Q", "Back": "A"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="DupDry", dryRun=True)["result"]
    assert r["dryRun"] is True
    assert r["duplicateGroups"] == 1 and r["duplicateNotes"] == 2
    assert r["deleted"] == 0                                 # nothing removed
    remaining = client.post("/actions/findNotes", json={"query": "deck:DupDry"}).json()["result"]
    assert sorted(remaining) == sorted([a, b])


def test_remove_duplicate_notes_by_id(client):
    did = _post(client, "/actions/createDeck", deck="DupId")["result"]
    _add_note(client, "DupId", "Basic", {"Front": "Q", "Back": "A"})
    _add_note(client, "DupId", "Basic", {"Front": "Q", "Back": "A"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deckId=did)["result"]
    assert r["deckId"] == did and r["deck"] == "DupId"
    assert r["deleted"] == 1


def test_remove_duplicate_notes_no_duplicates(client):
    _post(client, "/actions/createDeck", deck="Uniq")
    _add_note(client, "Uniq", "Basic", {"Front": "Q1", "Back": "A"})
    _add_note(client, "Uniq", "Basic", {"Front": "Q2", "Back": "A"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="Uniq")["result"]
    assert r["duplicateGroups"] == 0 and r["duplicateNotes"] == 0 and r["deleted"] == 0
    assert r["groups"] == []


def test_remove_duplicate_notes_deck_not_found(client):
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="NoSuchDeck")
    assert r["result"] is None and "deck was not found" in r["error"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_extra_actions.py -k remove_duplicate -v`
Expected: FAIL — the `_post` helper asserts HTTP 200 but `/extra_actions/removeDuplicateNotes` returns 404 (action not registered yet).

- [ ] **Step 3: Add the params schema**

Append to `ankiweb/ankiconnect/schemas/extra.py` (after `SetNotifyConfigParams`):

```python
class RemoveDuplicateNotesParams(ACBaseModel):
    """Find notes in a deck (and its subdecks) that are duplicates across ALL fields within the
    same note type, and remove the newer copies (keeping the oldest). Identify the deck by name
    or id. Set dryRun to preview the statistics without deleting anything."""
    deck: Optional[str] = Field(default=None, description="Deck name.")
    deckId: Optional[int] = Field(default=None, description="Deck id (alternative to `deck`).")
    dryRun: bool = Field(default=False,
                         description="If true, report duplicates but delete nothing.")
```

(`Optional` and `Field` are already imported at the top of the file.)

- [ ] **Step 4: Create the handler**

Create `ankiweb/ankiconnect/extra_actions/notes.py`:

```python
"""Note de-duplication extra actions."""
from __future__ import annotations
from anki.collection import SearchNode
from anki.utils import ids2str, split_fields, strip_html_media
from ankiweb.ankiconnect.registry import extra_action
from ankiweb.ankiconnect.actions._helpers import run_emit
from ankiweb.ankiconnect.schemas.extra import RemoveDuplicateNotesParams


@extra_action("removeDuplicateNotes", params=RemoveDuplicateNotesParams,
              summary="Remove notes that duplicate another across ALL fields (keep the oldest)")
async def remove_duplicate_notes(rt, deck=None, deckId=None, dryRun=False):
    """Scan a deck and its subdecks for notes that are duplicates across every field within the
    same note type (each field normalized with strip_html_media, as Anki's find_dupes does;
    notes whose fields are all empty after stripping are skipped), and delete the more recently
    added copies, keeping the oldest note in each duplicate group. dryRun returns the same
    statistics without deleting. ankiweb-original: reachable only at
    /extra_actions/removeDuplicateNotes, never via the canonical POST /."""
    def fn(col):
        # resolve the deck: a valid deckId wins, else fall back to the name
        did = deckId if (deckId is not None and col.decks.get(deckId) is not None) else None
        name = col.decks.name(did) if did is not None else None
        if name is None and deck:
            d = col.decks.by_name(deck)
            if d is not None:
                did, name = d["id"], d["name"]
        if name is None:
            raise Exception("deck was not found: " + str(deck if deck else deckId))

        nids = col.find_notes(col.build_search_string(SearchNode(deck=name)))
        rows = col.db.all(
            f"select id, mid, flds from notes where id in {ids2str(nids)}") if nids else []

        groups: dict[tuple, list[int]] = {}
        for nid, mid, flds in rows:
            stripped = tuple(strip_html_media(v) for v in split_fields(flds))
            if not any(stripped):                 # all fields empty -> never a duplicate
                continue
            groups.setdefault((mid, stripped), []).append(nid)

        detail = []
        redundant: list[int] = []
        for (mid, _key), members in groups.items():
            if len(members) < 2:
                continue
            members.sort()                        # ascending nid: oldest first
            kept, dupes = members[0], members[1:]
            redundant.extend(dupes)
            detail.append({"model": col.models.get(mid)["name"],
                           "kept": kept, "deleted": dupes})

        op = col.remove_notes(redundant) if (redundant and not dryRun) else None
        result = {
            "deck": name,
            "deckId": did,
            "notesScanned": len(nids),
            "duplicateGroups": len(detail),
            "duplicateNotes": len(redundant),
            "deleted": 0 if dryRun else len(redundant),
            "dryRun": bool(dryRun),
            "groups": detail,
        }
        return result, op
    return await run_emit(rt, fn)
```

- [ ] **Step 5: Register the module**

Edit `ankiweb/ankiconnect/extra_actions/__init__.py` to import the new module. After the `models` import line add:

```python
from ankiweb.ankiconnect.extra_actions import notes  # noqa: F401 — registers extra actions
```

The final import block should read (alphabetical):

```python
from ankiweb.ankiconnect.extra_actions import models  # noqa: F401 — registers extra actions
from ankiweb.ankiconnect.extra_actions import notes  # noqa: F401 — registers extra actions
from ankiweb.ankiconnect.extra_actions import notify  # noqa: F401 — registers extra actions
from ankiweb.ankiconnect.extra_actions import scheduling  # noqa: F401 — registers extra actions
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_extra_actions.py -k remove_duplicate -v`
Expected: PASS — all five `remove_duplicate` tests green.

- [ ] **Step 7: Commit**

```bash
git add ankiweb/ankiconnect/schemas/extra.py ankiweb/ankiconnect/extra_actions/notes.py \
        ankiweb/ankiconnect/extra_actions/__init__.py tests/ankiconnect/test_extra_actions.py
git commit -m "feat(extra_actions): removeDuplicateNotes — all-fields deck de-duplication

Find notes in a deck (incl. subdecks) that duplicate another across ALL
fields within the same note type (strip_html_media per Anki find_dupes),
keep the oldest and delete the newer copies; dryRun previews. Reachable
only at /extra_actions/removeDuplicateNotes.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Contract + edge-case tests

These lock in the behaviours that distinguish this action from Anki's single-field `find_dupes` and confirm the extra-only surface. They run against the Task 1 implementation; if any fails, fix the implementation before committing.

**Files:**
- Test: `tests/ankiconnect/test_extra_actions.py`

- [ ] **Step 1: Write the tests**

Append to `tests/ankiconnect/test_extra_actions.py`:

```python
def test_remove_duplicate_notes_all_fields_participate(client):
    # same first field, different second field -> NOT duplicates (built-in find_dupes WOULD
    # flag these because it only compares the first field)
    _post(client, "/actions/createDeck", deck="AllF")
    a = _add_note(client, "AllF", "Basic", {"Front": "Q", "Back": "A1"})
    b = _add_note(client, "AllF", "Basic", {"Front": "Q", "Back": "A2"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="AllF")["result"]
    assert r["duplicateGroups"] == 0 and r["deleted"] == 0
    remaining = client.post("/actions/findNotes", json={"query": "deck:AllF"}).json()["result"]
    assert sorted(remaining) == sorted([a, b])


def test_remove_duplicate_notes_cross_notetype_not_merged(client):
    # identical field values but different note types -> NOT duplicates
    _post(client, "/actions/createDeck", deck="XType")
    a = _add_note(client, "XType", "Basic", {"Front": "Q", "Back": "A"})
    b = _add_note(client, "XType", "Basic (and reversed card)", {"Front": "Q", "Back": "A"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="XType")["result"]
    assert r["duplicateGroups"] == 0 and r["deleted"] == 0
    remaining = client.post("/actions/findNotes", json={"query": "deck:XType"}).json()["result"]
    assert sorted(remaining) == sorted([a, b])


def test_remove_duplicate_notes_includes_subdecks(client):
    _post(client, "/actions/createDeck", deck="Parent")
    _post(client, "/actions/createDeck", deck="Parent::Child")
    a = _add_note(client, "Parent", "Basic", {"Front": "S", "Back": "B"})
    b = _add_note(client, "Parent::Child", "Basic", {"Front": "S", "Back": "B"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="Parent")["result"]
    assert r["duplicateGroups"] == 1 and r["deleted"] == 1
    assert r["groups"][0]["kept"] == a              # oldest (in Parent) kept
    assert r["groups"][0]["deleted"] == [b]         # subdeck copy removed
    remaining = client.post("/actions/findNotes", json={"query": "deck:Parent"}).json()["result"]
    assert remaining == [a]


def test_remove_duplicate_notes_strip_html_equivalent(client):
    # HTML-different but strip-equivalent first field -> duplicates
    _post(client, "/actions/createDeck", deck="Strip")
    a = _add_note(client, "Strip", "Basic", {"Front": "Q", "Back": "A"})
    b = _add_note(client, "Strip", "Basic", {"Front": "<b>Q</b>", "Back": "A"})
    r = _post(client, "/extra_actions/removeDuplicateNotes", deck="Strip")["result"]
    assert r["duplicateGroups"] == 1 and r["deleted"] == 1
    assert r["groups"][0]["kept"] == a


def test_remove_duplicate_notes_not_on_canonical_root(client):
    # the canonical POST / dispatcher must NOT know removeDuplicateNotes
    body = client.post("/", json={"action": "removeDuplicateNotes", "version": 6,
                                  "params": {"deck": "Default"}}).json()
    assert body["result"] is None and "unsupported action" in body["error"]
    # and it is not a typed /actions/ route either
    assert client.post("/actions/removeDuplicateNotes", json={"deck": "x"}).status_code == 404


def test_remove_duplicate_notes_in_openapi(client):
    schema = client.get("/openapi.json").json()
    assert "/extra_actions/removeDuplicateNotes" in schema["paths"]
    assert "/actions/removeDuplicateNotes" not in schema["paths"]
    assert "RemoveDuplicateNotesParams" in schema["components"]["schemas"]
    assert "extra_actions" in schema["paths"]["/extra_actions/removeDuplicateNotes"]["post"]["tags"]
```

- [ ] **Step 2: Run the new tests**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_extra_actions.py -k remove_duplicate -v`
Expected: PASS — all eleven `remove_duplicate` tests green. If a contract test fails, fix `notes.py` (not the test) and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/ankiconnect/test_extra_actions.py
git commit -m "test(extra_actions): removeDuplicateNotes contract + edge cases

All-fields (vs single-field find_dupes), cross-notetype isolation,
subdecks, strip-equivalent dupes, extra-only surface + OpenAPI.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the whole AnkiConnect test suite**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/ -q`
Expected: PASS — no regressions across the AnkiConnect surface (the prior count was 113 passing; this adds 11).

- [ ] **Step 2: Run the rest-docs guard**

Run: `conda run -n ankiweb python -m pytest tests/ankiconnect/test_rest_docs.py -q`
Expected: PASS — the new extra action is documented/typed consistently with the others.

- [ ] **Step 3: Run the full project test suite**

Run: `conda run -n ankiweb python -m pytest -q`
Expected: PASS — full suite green (no regressions anywhere).

- [ ] **Step 4: Final confirmation (no commit needed if suite is green)**

If everything passes, the feature is complete on the `feat/remove-duplicate-notes` branch. If any unrelated test was already failing on `master` before this work, note it rather than "fixing" it here.

---

## Self-Review Notes (author)

- **Spec coverage:** dedup key (Task 1 handler + Task 2 all-fields/cross-type/strip tests), keep-oldest/delete-newer (Task 1 keeps_oldest), deck+subdecks (Task 2 subdecks), dryRun (Task 1 dry_run), response shape incl. 种数/个数 (Task 1 keeps_oldest asserts every field), deck-not-found (Task 1), extra-only surface + OpenAPI (Task 2). Empty-note skip is implemented defensively (`if not any(stripped)`) but not unit-tested because the public `addNote` API rejects all-empty notes, so they cannot be created over HTTP — documented here intentionally.
- **Placeholder scan:** none.
- **Type consistency:** handler returns `(result, op)` consumed by `run_emit`; response keys (`notesScanned`, `duplicateGroups`, `duplicateNotes`, `deleted`, `dryRun`, `groups[].model/kept/deleted`) match the tests exactly; `RemoveDuplicateNotesParams` fields (`deck`/`deckId`/`dryRun`) match the handler signature.
