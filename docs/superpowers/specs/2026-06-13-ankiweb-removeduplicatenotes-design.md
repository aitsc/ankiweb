# Design: `removeDuplicateNotes` extra action

**Date:** 2026-06-13
**Status:** Approved (brainstorming)
**Surface:** ankiweb-original AnkiConnect extra action, reachable ONLY at
`POST /extra_actions/removeDuplicateNotes` (never via canonical `POST /` or `/actions/`).

## Problem

Anki's built-in duplicate detection (`Collection.find_dupes(field_name, search)`) compares
notes by a **single** field only (the named field, defaulting to the sort field), after
`strip_html_media`. There is no first-class way to find notes that are duplicates across
**all** their fields. We want a deck-scoped action that joins every field of a note into the
dedup key, finds duplicate notes, and removes the redundant (newer) copies.

## Behaviour

Given a deck (by name or id), scan all notes in that deck **and its subdecks**, group them by
an all-fields key, and within each group of ≥2 notes keep the **oldest** note and delete the
rest. Return counts plus per-group detail.

### Dedup key

For each note the key is `(mid, tuple(strip_html_media(f) for f in fields))`:

- **Per note type.** The note-type id (`mid`) is part of the key, so two notes are duplicates
  only when they share the same note type AND every field is equal. Cross-type collisions are
  impossible.
- **All fields.** Every field participates (not just the first/sort field).
- **Normalization.** Each field value is passed through `anki.utils.strip_html_media` before
  comparison — the exact function Anki's `find_dupes` uses, so behaviour matches it. It strips
  HTML tags and HTML media elements (e.g. `<b>Q</b>` → `Q`, `<img>` removed) but **preserves
  `[sound:…]` text** (verified: `strip_html_media("<b>Q</b>[sound:a.mp3] x")` → `"Q[sound:a.mp3] x"`).
  Comparison is then exact: case-sensitive and whitespace-sensitive.
  - Runtime note: `strip_html_media` calls `anki.lang.current_i18n`, which is `None` on a bare
    headless import. This is safe here because every action runs through `CollectionService`,
    whose `open()` calls `anki.lang.set_lang(...)` before any `fn(col)` executes (confirmed).
- **Empty notes skipped.** If every field is empty after stripping, the note is excluded from
  dedup entirely (an all-empty note is never a "duplicate"). Matches Anki's `find_dupes`.

### Which note is kept

`nid` is the creation timestamp (ms) in Anki, so within a duplicate group:

- **Keep** the note with the smallest `nid` (oldest / first added).
- **Delete** every other note in the group (the more recently added copies), via
  `col.remove_notes(redundant_nids)` (which also removes their cards).

### Deck scope

- Resolve the deck: prefer `deckId` if it resolves to an existing deck, else `deck` (name).
  If neither resolves → raise `Exception("deck was not found: <deck|deckId>")` (enveloped as
  `error`, like `deleteModel` / `extendCardLimits`).
- Search includes subdecks: build the query with
  `col.build_search_string(SearchNode(deck=<name>))` and `col.find_notes(...)`. `deck:Name`
  semantics include all descendant decks, matching Anki's search/UI.
- For `deckId`, resolve to the deck name first, then search by name (so subdecks are included).

### dryRun

- `dryRun=False` (default): perform the deletions; `deleted` = number removed; the action
  returns its `OpChanges` from `remove_notes` so the bus broadcasts and an open web UI
  refreshes.
- `dryRun=True`: compute and return the same statistics but delete nothing; `deleted` is `0`
  and the action returns `op=None` (no broadcast).

## Response shape

```json
{
  "deck": "MyDeck",
  "deckId": 1700000000001,
  "notesScanned": 1000,
  "duplicateGroups": 7,
  "duplicateNotes": 10,
  "deleted": 10,
  "dryRun": false,
  "groups": [
    {"model": "Basic", "kept": 1700000000002,
     "deleted": [1700000000050, 1700000000090]}
  ]
}
```

| field            | meaning |
|------------------|---------|
| `deck`           | resolved deck name |
| `deckId`         | resolved deck id |
| `notesScanned`   | total notes found in the deck + subdecks (before empty-key exclusion) |
| `duplicateGroups`| 种数 — number of distinct keys occurring ≥2 times |
| `duplicateNotes` | 个数 — redundant copies = Σ(group_size − 1); the delete candidates |
| `deleted`        | notes actually removed (equals `duplicateNotes`; `0` when `dryRun`) |
| `dryRun`         | echo of the request flag |
| `groups`         | per-group detail: note-type name, the kept noteId, the deleted noteIds (sorted oldest→newest) |

`groups` lists only groups with ≥2 notes. Within each group, `kept` is the smallest nid and
`deleted` is the remaining nids in ascending nid order.

## Implementation

Mirrors the existing extra-action pattern (`deleteModel`, `extendCardLimits`).

- **Schema** — `RemoveDuplicateNotesParams` in `ankiweb/ankiconnect/schemas/extra.py`:
  - `deck: Optional[str]` — deck name.
  - `deckId: Optional[int]` — deck id (alternative to `deck`).
  - `dryRun: bool = False` — when true, report but delete nothing.
- **Action** — `ankiweb/ankiconnect/extra_actions/notes.py` (new file), imported in
  `extra_actions/__init__.py` for registration:
  - `@extra_action("removeDuplicateNotes", params=RemoveDuplicateNotesParams, summary="…")`
  - Body is `async def remove_duplicate_notes(rt, deck=None, deckId=None, dryRun=False)` →
    `return await run_emit(rt, fn)` where `fn(col) -> (result_dict, op_or_None)`.
  - Inside `fn`:
    1. Resolve the deck id/name (raise if not found).
    2. `nids = col.find_notes(col.build_search_string(SearchNode(deck=name)))`.
    3. Fetch `id, mid, flds` rows efficiently:
       `col.db.all(f"select id, mid, flds from notes where id in {ids2str(nids)}")`
       (same approach as `find_dupes`, avoids loading Note objects).
    4. For each row: `vals = split_fields(flds)`; `key = (mid, tuple(strip_html_media(v) for v
       in vals))`; skip if all stripped values are empty; `groups.setdefault(key, []).append(nid)`.
    5. For each group with ≥2 nids: sort ascending; kept = first; redundant = rest. Accumulate
       counts + per-group detail (model name via `col.models.get(mid)["name"]`).
    6. If not `dryRun` and there are redundant nids: `op = col.remove_notes(all_redundant)`;
       else `op = None`.
    7. Build and return `(result_dict, op)`.
  - Imports (all verified against pinned anki 25.9.4):
    `from anki.utils import ids2str, split_fields, strip_html_media` and
    `from anki.collection import SearchNode`.

## Testing

Add to `tests/ankiconnect/test_extra_actions.py`:

- **deletes redundant, keeps oldest** — add 3 identical Basic notes to a deck; call the action;
  assert `duplicateGroups==1`, `duplicateNotes==2`, `deleted==2`, and the surviving note is the
  first-added (smallest nid).
- **dryRun reports but does not delete** — same setup with `dryRun=True`; assert counts match
  but `deleted==0` and all notes still exist.
- **all fields participate** — two notes share field 1 but differ in field 2 → NOT duplicates
  (the single-field built-in would have flagged them).
- **cross note type not merged** — identical-looking content in two different note types → not
  duplicates.
- **subdecks included** — duplicates split across `Parent` and `Parent::Child` are found when
  the action targets `Parent`.
- **strip-equivalent duplicates** — `Q` vs `<b>Q</b>` (HTML stripped) are treated as
  duplicates; note `[sound:…]` text is preserved, so a `[sound:x.mp3]` value and a plain value
  are NOT duplicates (faithful to `find_dupes`).
- **empty notes skipped** — multiple all-empty notes are not reported as duplicates.
- **deck not found** — `result is None` and `"deck was not found"` in `error`.
- **not on canonical root / not under /actions/** — `POST /` reports `unsupported action`;
  `POST /actions/removeDuplicateNotes` → 404.
- **present in OpenAPI** — `/extra_actions/removeDuplicateNotes` path and
  `RemoveDuplicateNotesParams` schema exist; tagged `extra_actions`.

## Out of scope

- No UI / Extras-menu entry (API only).
- No cross-note-type dedup, no configurable per-field selection, no merge/keep-strategy options
  beyond keep-oldest.
- No change to the canonical AnkiConnect surface (`POST /`, `/actions/`).
