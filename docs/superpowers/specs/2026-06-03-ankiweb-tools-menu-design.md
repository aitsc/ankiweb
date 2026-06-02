# ankiweb Sub-project — Tools menu (Check DB / Check Media / Empty Cards / Manage Note Types)

**Status:** design (2026-06-03). User asked for the desktop **Tools** menu items that aren't in the web UI. Backend ops mostly exist; no web entry points (and Check Media isn't wired at all).

## Goal
Add a **Tools** entry to the global toolbar leading to web equivalents of the desktop Tools menu: Check Database, Check Media, Empty Cards, and Manage Note Types. Server-rendered pages + WS handlers, reusing the E4/E5/I3 pattern and `ankiweb.i18n`. Destructive actions (delete unused media, delete empty cards, delete a notetype) show what will be affected and require confirmation.

## Verified backend APIs (live-probed)
- `col.fix_integrity()` → `(report:str, ok:bool)` tuple (NOT an OpChanges → use `service.run`).
- `col.media.check()` → `CheckMediaResponse{ unused:[str], missing:[str], missing_media_notes, report:str, have_trash:bool }`. Delete unused: `col.media.trash_files(list)` then `col.media.empty_trash()` (both return None).
- `col.get_empty_cards()` → `EmptyCardsReport{ report:str, notes:[ {note_id, will_delete_note, card_ids:[int]} ] }`. Delete: gather `card_ids` from all entries → `col.remove_cards_and_orphaned_notes(card_ids)` (OpChangesWithCount) via `run_op`.
- Notetypes: `col.models.all_names_and_ids()`; `col.models.nids(ntid)` (note count); add = clone a stock dict (`m=col.models.by_name("Basic")` → deep-copy via `col.models.new`? simplest: `nt=col.models.new(name)`+copy fields/templates/css from a chosen base, then `col.models.add_dict(nt)`), OR clone an existing notetype's dict (copy, strip id, set name, `add_dict`); rename = set `m["name"]=newname` + `col.models.update_dict(m)` (no `rename` method); delete = `col.models.remove(ntid)` (OpChanges) — guard: refuse if it's the only notetype.

## Decomposition (each its own plan → implement → review → merge)
- **TA — Tools page** (`/tools`, context `tools`) + toolbar "Tools" link. One page, three tools, each a button + result `<div>`:
  - **Check Database**: `pycmd('checkdb')` → `col.fix_integrity()` via `run` → push the report string to the result area.
  - **Check Media**: `pycmd('checkmedia')` → `col.media.check()` → render the report + the unused/missing lists; a "Delete unused (N)" button → `pycmd('deleteunused')` → `trash_files(unused)`+`empty_trash()` via `run` (stash the last `unused` list in handler state between check→delete). Re-run check after delete.
  - **Empty Cards**: `pycmd('emptycards')` → `col.get_empty_cards()` → show the report + total empty-card count; a "Delete (N)" button → `pycmd('emptycards_delete')` → `remove_cards_and_orphaned_notes(stashed card_ids)` via `run_op` (broadcast). Stash card_ids server-side between check→delete.
  - A link "Manage Note Types" → `/notetypes`.
  - Results pushed via `hub.push_call("tools","ankiwebToolsResult",[which, html])`; errors via the `window.<fn>` pattern.
- **TB — Manage Note Types** (`/notetypes`, context `notetypes`): a list of notetypes (name + "N notes" via `nids`), each row with: **Fields…** → `/fields/{id}` (F5), **Cards…** → `/card-layout/{id}` (F6), **Rename** (inline → `pycmd('rename:id:newname')` → set `m["name"]` + `update_dict` via run_op), **Delete** (confirm, shows note count → `pycmd('delete:id')` → `col.models.remove(id)` via run_op; refuse the last remaining notetype → error callback). An **Add** control: name + a base-notetype `<select>` (existing notetypes to clone) → `pycmd('add:base_id:newname')` → clone the base dict (copy, drop ids, set name, `add_dict`) via run_op. Reload the list after each mutation.

Ship order: TA → TB (TB links to the existing F5/F6 editors).

## i18n
Labels via `tr.<key>()` (verify per plan; keyless English fallback): `qt_misc_check_database`, `qt_misc_check_media`, `qt_misc_empty_cards`/`actions_empty_cards`, `qt_misc_manage_note_types`/`notetypes_notetypes`, `actions_delete`, `actions_rename`, `actions_add`, `actions_save`, `actions_cancel`. The "Tools" toolbar label: `qt_misc_tools`.

## Testing
Each tool: handler unit test (check returns a report; delete actually removes; the stash check→delete round-trip) + a render test (page has the buttons) + a Playwright boot check. Manage Note Types: add clones a working notetype (generates cards), rename persists, delete removes (and is refused for the last one), and the Fields/Cards links point at /fields//card-layout. Destructive ops broadcast via run_op.

## Risks
Check Database `fix_integrity` returns a tuple, not OpChanges → `run`, not `run_op`. Empty-cards + media-delete are destructive → must operate on the *stashed report* (don't recompute-and-delete blindly) and confirm in the UI. Notetype delete cascades to its notes/cards — show the note count + confirm; refuse deleting the only notetype. Adding a notetype must produce a *usable* one (clone an existing dict, not a bare `new()` with no fields/templates).
