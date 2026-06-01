# ankiweb Sub-project D — Browser + Editor Design

**Status:** design (2026-06-01). Decomposed into D1–D4; each its own plan → implement cycle.

## Goal
Replicate Anki desktop's **Browser** (the card/note browse window: search, results table, sidebar, row actions) and **note Editor** (Add/Edit) in the browser, faithfully, on the existing FastAPI + WebSocket-bridge foundation.

## Two architectural decisions (grounded by recon vs the real Anki source)

1. **Editor — REUSE the real compiled `editor.js`** (same approach ① as `reviewer.js`). It is already vendored at `ankiweb/web_assets/js/editor.js` (~3.5MB, self-contained esbuild/Svelte IIFE) + `css/editor.css` + `css/editable.css`. It exposes `setupEditor("add"|"browse"|"review")` and per-instance globals (`setFields`, `setTags`, `focusField`, `saveNow`, `setNoteId`, `setNotetypeMeta`, `setFonts`, `triggerChanges`, `pasteHTML`, …) on `window`, and sinks all field events to `window.bridgeCommand` — which ankiweb's `pycmd_shim` already aliases to the WS bridge. Translations come from the already-wired `POST /_anki/i18nResources` passthrough.
   - **JS→server bridge surface (small, enumerated):** `focus:{ord}`, `blur:{ord}:{nid}:{html}`, `key:{ord}:{nid}:{html}` (debounced), `saveTags:{json}`, `setTagsCollapsed:{bool}` + a flat table of toolbar button strings (`bold`/`italic`/`cloze`/`attach`/colour/etc.). HTML carries colons → parse with `split(":", 3)`.
   - **server→JS (loadNote):** ~18 setter calls (`setFields([...])`, `setNotetypeMeta`, `setTags`, `focusField`, `setFonts`, `triggerChanges`, …) pushed via the bridge, **gated on `require("anki/ui").loaded`** (a second, finer gate inside the bundle beyond the shim's domDone gate).
   - **Persistence:** `blur:/key:` → munge HTML (drop bare `<br>`/`<div><br></div>`, null-byte strip, `col.media.escape_media_filenames(txt, unescape=True)`) → `note.fields[ord]=…` → `col.update_note(skip_undo_entry=True)`; `saveTags:` → `note.tags`. All backend ops ankiweb already proxies (reuse `updateNoteFields`/`updateNoteTags` from B2).
   - **Media paste is SIMPLER in the browser than in Qt:** the browser holds the bytes; ankiweb needs only one "store image bytes → media filename" endpoint (largely already present via the media route + `col.media.write_data`). No QClipboard/QImage/BeautifulSoup pipeline.
   - **Defer (v2):** image-occlusion (`setupMaskEditor`/IO state), remote-URL paste download, server-side paste sanitization. Do not crash on unknown cmds.
   - **De-risk:** like the reviewer, prove the `setupEditor`/`require("anki/ui").loaded`/`setFields` round-trip end-to-end with a Playwright spike BEFORE committing D3.

2. **Browser table — REBUILD as web** (Anki's is Qt-only: `QTableView` + `QAbstractTableModel`, no Svelte to reuse), but as a **thin renderer** over existing backend calls — the table is a caching adaptor (id-list-from-search → lazily fetch one rendered row per id). ankiweb replicates the adaptor, not the Qt classes.
   - **Backend:** `col.find_cards/find_notes(query, order, reverse)`, `col.all_browser_columns()`, `col.browser_row_for_id(id)` (renders cells for the *currently-set active columns* — global per-collection state, set via `col.set_browser_card_columns`/`set_active_browser_columns`), `col.build_search_string(*nodes)` (normalize/validate, raises `SearchError`). Sidebar = assemble from `col.decks.deck_tree()` + `col.tags.tree()` + `col.models.all()` + config `savedFilters` (no single sidebar RPC). Actions map to ops AnkiConnect already wraps (changeDeck/suspend/setDueDate/forgetCards/deleteNotes/addTags/removeTags); a few are net-new (set flag, bury/unbury, reposition, change-notetype, `col.find_and_replace`).
   - **For D1 specifically:** avoid the global active-columns state — render fixed columns (Sort-field / Deck / Due) computed directly from the note/card, NOT `browser_row_for_id`. The real column model (`all_browser_columns` + `browser_row_for_id` + reorder) is deferred to D2/D4.

## Decomposition (dependency-ordered; each shippable + testable)

- **D1 — Browser table READ core.** `/browse` route + a `browser` bridge context + search bar + results table (fixed Sort-field/Deck/Due columns, capped ~500 rows) + a sidebar (decks/tags) + open-card→reviewer. Reuses `find_cards` + a small row builder; writes `hub.ui_state` (browser_open/last_browse_query/matched_card_ids) so the B4 degraded `guiBrowse` becomes faithful. **No mutation, no selection, no editor.**
- **D2 — Selection + bulk card/note actions.** Multi-select (shift/ctrl), action verbs (suspend/unsuspend/forget/setDueDate/changeDeck/deleteNotes/add+remove tags) each a thin handler branch over the already-built B2/B3 op bodies (`run_emit` broadcasts → table reloads). Upgrades `guiSelectCard`/`guiSelectedNotes` to the real selection.
- **D3 — Editor reuse (parallelizable with D2).** A `/edit` route serving vendored `editor.js` like the reviewer page; a de-risking spike; the `editorReady`/`ankiwebLoadNote(setFields…)` push; the `blur:/key:/saveTags:` save path via `updateNoteFields`/`updateNoteTags`; the image-upload endpoint. Ships a working single-note editor.
- **D4 — Add/Edit dialogs + gui\* wiring (depends D2+D3).** Embed the editor in the Browser pane (single-row select → live load), an Add-Note dialog (Add-mode `build_note`/`check_addable`/`add_note`), wire the reviewer Edit button, and make `guiAddCards`/`guiEditNote`/`guiAddNoteSetData`/`guiBrowse`-reorder faithful against the live table+editor — closing the B4 Plan-D deferrals.

## Integration (reuses the proven patterns)
New screen modules `screens/browser.py` + `screens/editor.py` (each `render_*_html` + `make_*_handler` closure), a `/browse` + `/edit` GET route in `routes.py`, and `hub.set_handler('browser'|'editor', …)` — identical shape to the reviewer. Bridge: `push_call`/`dispatch_cmd` (NOT `eval_with_callback` from inside a handler — the documented Plan-4 deadlock; use the reviewer's precommand pattern). Collection work via `CollectionService.run`/`run_op`/`emit`. Actions reuse the B1–B4 ankiconnect op bodies wholesale.

## Risks
3.5MB editor bundle (de-risk with a spike); `eval_with_callback` deadlock (use precommands); field-save debounce + late-blur `nid!=note.id` guard + `skip_undo_entry`; global active-columns collision across sessions (D1 sidesteps via fixed columns); `find_cards` with no LIMIT can return tens of thousands of ids → cap/paginate the row materialization (~500) so the single-worker executor doesn't stall.
