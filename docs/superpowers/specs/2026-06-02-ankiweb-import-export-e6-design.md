# ankiweb Sub-project E6 — Import / Export Design

**Status:** design (2026-06-02). Decomposed into E6a (GUI import), E6b (GUI export), E6c (AnkiConnect import/export). Each its own plan → implement cycle.

## Goal
Port Anki's import and export: (1) GUI **import** of CSV and `.apkg` files by reusing Anki's real compiled SvelteKit import pages; (2) GUI **export** to `.apkg` / `.colpkg` / notes-CSV / cards-CSV as a rebuilt server-rendered form (export is Qt-only — no web bundle); (3) the AnkiConnect **`importPackage`/`exportPackage`** HTTP actions. **Scope (chosen "core set"):** excludes destructive `.colpkg` collection *import* (restore) and the niche Mnemosyne `.db` / `.anki-json` import-page route — both deferred.

## Key architectural findings (recon vs anki 25.9.4 + anki-connect)

**Import = reuse the SvelteKit SPA (the E1–E3 pattern).** Three real import routes exist in `ts/routes/`; the core set uses two:
- `import-csv/[...path]` — `+page.ts` loads via `getNotetypeNames` + `getDeckNames` + `getCsvMetadata({path})`; re-fetches `getCsvMetadata` (full params: delimiter/notetypeId/deckId/isHtml) + `getFieldNames({ntid})` on option changes (the column-mapping round-trip); submits `importCsv({path, metadata})`, then `importDone({})`.
- `import-anki-package/[...path]` — loads `getImportAnkiPackagePresets({})`; submits `importAnkiPackage({packagePath, options})`, then `importDone({})`.
- (`import-page/[...path]` for Mnemosyne/JSON — DEFERRED.)
The pages take a **filesystem path in the URL** (`[...path]` rest param) and use it immediately on load. **No host-bridge/pycmd.**

**The one novel mechanism — upload-to-temp.** Every backend import/export op takes a **server-side filesystem path string, not bytes** (`import_csv(request.path)`, `import_anki_package(request.package_path)`, `export_*(out_path=...)`). In Qt these are local paths from a file picker. In the browser:
- **Import:** the user uploads a file (multipart) BEFORE the page loads (the path is in the URL and read on load) → the server saves it to a **managed temp dir** and the client navigates to `/import-csv/<temp-path>`.
- **Export:** the backend writes to a **temp out_path** → the server streams it back as an HTTP download.

**Export = rebuild as a server-rendered form (renders like E4–E5 but submits via a plain HTML form POST, NOT the WS bridge).** E4 (`custom_study.py`)/E5 (`filtered_deck.py`) submit over pycmd/WebSocket; E6b deliberately diverges to a real `POST /export` because a binary file download needs an HTTP response body that the pycmd/WS channel cannot carry. Export is a pure Qt dialog (`qt/aqt/import_export/exporting.py`) — no SvelteKit page. Backend methods (`pylib/anki/collection.py`):
- `export_anki_package(*, out_path, options: ExportAnkiPackageOptions, limit: ExportLimit) -> int` (note count; keyword-only). `ExportAnkiPackageOptions` fields: `with_scheduling`, `with_deck_configs`, `with_media`, `legacy`.
- `export_collection_package(out_path, include_media, legacy) -> None` (POSITIONAL args). **WARNING (verified): this CLOSES the live collection** — afterward `col.card_count()` raises `AttributeError` (the collection object is dead). The server must reopen it (a fresh `Collection(path)` restores it cleanly). E6b adds `CollectionService.reopen()` for exactly this.
- `export_note_csv(*, out_path, limit, with_html, with_tags, with_deck, with_notetype, with_guid) -> int` (keyword-only).
- `export_card_csv(*, out_path, limit, with_html) -> int` (keyword-only).
- `ExportLimit` is a oneof: `whole_collection` | `deck_id` | `note_ids` | `card_ids`. **`whole_collection` is a `google.protobuf.Empty` MESSAGE, not a bool** — construct it as `lim = ExportLimit(); lim.whole_collection.SetInParent()` (verified: `ExportLimit(whole_collection=True)` raises `TypeError`). `deck_id` is an int field. The core set uses **whole_collection** (`SetInParent`) or **deck_id** (the target dropdown). Note/card-id limits are not wired in core (no Browser changes).

**Write-RPC broadcast.** `import_csv`/`import_anki_package`/`import_json_file` return `ImportLogWithChanges` (the Python alias in `anki.collection` for `import_export_pb2.ImportResponse`) — a message with `.changes: OpChanges` and `.log`. The CUSTOM handlers parse `.changes` and broadcast (mirroring `updateDeckConfigs`). `export_*` mutate nothing (no broadcast).

**`importDone` raises on the headless backend.** `import_done_raw(b"")` RAISES `anki.errors.InvalidInput` (whose message string is `"InvalidServiceIndex"` — that is the message, NOT a distinct exception class; there is no `FrontendService`/`ImportExportService` class in the wheel — `import_done` lives on `RustBackendGenerated`). So it MUST be a CUSTOM no-op returning `b""`→204, exactly like `deckOptionsReady`/`deckOptionsRequireClose`. NOT passthrough. (The SvelteKit pages call `importDone` from the shared `import-page/ImportPage.svelte` wrapper that both import pages render; serving the SPA shell + `/_app` bundle wholesale already covers it.)

**AnkiConnect (`anki-connect/plugin/__init__.py`).** `importPackage(path)` uses the legacy `AnkiPackageImporter(col, path).run()`; `exportPackage(deck, path, includeSched=False)` uses the legacy `AnkiPackageExporter` with `.did`/`.includeSched`/`.exportInto(path)`. Both take **server-side filesystem paths** and return `True`. The legacy `anki.importing.AnkiPackageImporter` / `anki.exporting.AnkiPackageExporter` are still importable in 25.9.4 → replicate the contract faithfully (consistent with B1–B4). There are no CSV AnkiConnect actions.

## Serve model + RPC wiring (E6a)
- Add `GET /import-csv/{path:path}` and `GET /import-anki-package/{path:path}` to `build_sveltekit_router` → serve `sveltekit/index.html` (the SPA client-routes on `location.pathname`; `{path:path}` captures the temp path, incl. slashes). `/_app/{path}` already served (E1).
- **Passthrough** (read): `get_csv_metadata`, `get_deck_names`, `get_field_names`, `get_import_anki_package_presets` (and `get_notetype_names`, already present). All have backend `*_raw` methods.
- **CUSTOM** (write, broadcast the `.changes` of the returned `ImportLogWithChanges`): `importCsv`→`import_csv`, `importAnkiPackage`→`import_anki_package` (`importJsonFile` only if the deferred import-page is added later).
- **CUSTOM no-op**: `importDone` → `b""`→204.

## Components (by plan)

### E6a — GUI Import
| Unit | Responsibility |
|---|---|
| `POST /import/upload` (new endpoint) | accept a multipart file; save to the managed temp dir as `<token><ext>`; detect type by extension; return `{route, path}` (`.csv/.tsv/.txt`→`import-csv`, `.apkg/.zip`→`import-anki-package`; unknown→400) |
| temp-file manager | a single managed import dir under a NEW `Settings.import_tmp_dir` field (default `<data_dir>/import-tmp/`, env-overridable `ANKIWEB_IMPORT_TMP_DIR`); helpers to allocate `<token><ext>`, validate a candidate path resolves inside it (realpath-prefix check, mirroring the media router's `relative_to` in `assets.py`), and a lazy TTL GC that deletes files older than ~60 min on each new upload (since `importDone` is a no-op and receives no path, it cannot delete) |
| `build_sveltekit_router` (+2 routes) | serve the two import pages' SPA shell |
| `anki_rpc` passthrough/CUSTOM (+methods) | the read passthroughs + the import-write CUSTOM handlers + `importDone` no-op. **Path confinement applies to THREE distinct proto fields** — validate each resolves inside `import_tmp_dir` BEFORE calling the backend: `ImportCsvRequest.path`, `CsvMetadataRequest.path`, and `ImportAnkiPackageRequest.package_path`. (`get_deck_names`/`get_field_names` carry NO path — plain passthrough.) |
| deck-browser "Import" entry | a button → hidden `<input type=file>` → `POST /import/upload` → navigate to `{route}/{encodeURIComponent(path)}` |

### E6b — GUI Export
| Unit | Responsibility |
|---|---|
| `GET /export` (server-rendered form) | target `<select>` (Whole Collection / each non-filtered deck via `col.decks.all_names_and_ids`); format radios (.apkg / .colpkg / Notes CSV / Cards CSV); option checkboxes (apkg: include scheduling/media/deck-configs/legacy; csv: html/tags/deck/notetype/guid) with JS show/hide per format |
| `POST /export` | build the `ExportLimit` (whole_collection via `lim.whole_collection.SetInParent()`, vs `deck_id=int`) + the format-specific request; write to a temp out_path via the backend export method; **for `.colpkg`, call `CollectionService.reopen()` immediately after** (export_collection_package kills the live collection); return `FileResponse(temp, filename, media_type, background=delete-temp)`; on error re-render the form with a message |
| `CollectionService.reopen()` (new) | re-acquire `self._col = Collection(path)` INSIDE the live single-worker executor WITHOUT shutting it down — note current `close()` ALSO `executor.shutdown()`s, so `reopen()` must NOT reuse `close()`; used by `POST /export` after a `.colpkg` export to revive the bricked collection |
| deck-browser "Export" entry | a button → navigate to `/export` |

### E6c — AnkiConnect import/export
| Unit | Responsibility |
|---|---|
| `importPackage(path)` | `AnkiPackageImporter(col, path).run()` run ON the single-worker executor (the importer opens a 2nd `Collection` on the extracted temp .anki2 and mutates+saves the live `col` — must be serialized); return `True`; broadcast a refresh. Upstream wraps this in `startEditing()`→`requireReset()` (a Qt GUI call) — **intentionally dropped** (no Qt mainwindow), consistent with B1–B4 |
| `exportPackage(deck, path, includeSched=False)` | `d = col.decks.by_name(deck)`; **if `d is None` return `False`** (faithful to upstream's `{result:False}`); else `AnkiPackageExporter(col)` with `.did = d["id"]`, `.includeSched = includeSched`, `.exportInto(path)`, run ON the executor (it opens a dst `Collection` + reads the live col); return `True`. **Pass the live service-owned `Collection`** — the exporter stores only `col.weakref()`, so a transient would die mid-export. Uses ONLY `AnkiPackageExporter` (.apkg), which does NOT close the collection — the colpkg-close/reopen concern is E6b-only |

## Data flow
**Import:** Import button → file picker → `POST /import/upload` (multipart) → temp path + route → client navigates to `/import-csv/<temp>` → SvelteKit page loads → `getCsvMetadata` (path-confined) + `getDeckNames`/`getFieldNames` (no path) → user maps columns → `importCsv` (CUSTOM: confirm `ImportCsvRequest.path` is in `import_tmp_dir` → `import_csv` → broadcast `.changes`) → `importDone` (no-op) → page shows the import log. (Uploaded temp files are reaped by the upload endpoint's lazy TTL GC — `importDone` gets no path so cannot delete them.)
**Export:** Export button → `/export` form → user picks target/format/options → `POST /export` → backend writes temp out_path → `FileResponse` download (Content-Disposition: attachment) → `BackgroundTask` deletes temp.
**AnkiConnect:** HTTP `importPackage`/`exportPackage` with server-side paths → legacy importer/exporter → `True`.

## Error handling
- Import RPC errors (bad CSV, etc.) → the dispatch already returns 500 + message; the SvelteKit page renders its own error UI. A path OUTSIDE the managed temp dir → the handler returns an error (rejected) without touching the backend.
- Upload of an unknown extension → `POST /import/upload` 400.
- Export of an invalid target/format → re-render `/export` with an inline error; never stream a partial file.
- `export_collection_package` KILLS the live collection (verified: `card_count()` raises `AttributeError` after) — `POST /export` runs it on the single-worker executor, then calls `CollectionService.reopen()` to revive it. An E6b test asserts the collection is still usable post-export.

## Security
- **Path confinement:** import RPCs receive a server path from the URL; the handlers must confirm it resolves inside `import_tmp_dir` (realpath prefix check) before use — preventing the page from reading/importing arbitrary server files. Enforce on the three path-bearing fields: `ImportCsvRequest.path`, `CsvMetadataRequest.path`, `ImportAnkiPackageRequest.package_path`. Low risk in a single-user local app, but a clean enforced boundary.
- AnkiConnect `importPackage`/`exportPackage` take arbitrary server paths by design (faithful to AnkiConnect's local-first contract — the server IS the user's machine). Documented, not constrained (matches upstream).

## Testing
- **E6a:** TestClient — upload a CSV → 200 + `{route:"import-csv", path:<temp>}`; the path is inside the temp dir; unknown ext → 400; `/import-csv/{path}` serves the SPA shell; passthrough/CUSTOM membership; an `importCsv` round-trip imports notes + broadcasts; `importDone`→204; a path outside the temp dir is rejected. Playwright — upload a real CSV, the import-csv SPA boots, maps a column, imports, and the notes appear.
- **E6b:** TestClient — `GET /export` renders the form (targets + formats); `POST /export` (apkg, whole collection) returns 200 with `Content-Disposition: attachment` + non-empty body; per-deck + each CSV format produce a file; **a `.colpkg` export returns a non-empty file AND the collection is still usable afterward (assert `card_count`/an RPC succeeds — the `reopen()` guard)**; bad target → form re-render with error. Playwright — the form renders, submitting triggers a download (assert the response/download event).
- **E6c:** TestClient over the AnkiConnect app — `exportPackage` writes a real `.apkg` at a temp path (file exists, non-empty) + returns `True`; an unknown deck name returns `False`; `importPackage` of that file round-trips notes back into a fresh collection + returns `True`. (Both actions run their importer/exporter on the collection executor.)

## Decomposition (dependency-ordered; each ships working functionality)
- **E6a — GUI Import** (FOUNDATION for the upload-to-temp mechanism + the import SPA routes). **← first.**
- **E6b — GUI Export** (independent; the rebuilt form + download). Can follow E6a.
- **E6c — AnkiConnect import/export** (independent; 2 HTTP actions). Smallest; can be last.

Ship order: E6a → E6b → E6c.

## Risks
Route ordering (the two import SPA routes before the media catch-all — same as E1/E2); the upload-to-temp path-safety boundary (must be enforced on all three path fields, not assumed); `export_collection_package` killing the collection — needs the new `CollectionService.reopen()` (NOT `close()`, which also shuts the executor) + a post-export health-check test; the E6c importer/exporter must run on the single-worker executor (they open secondary `Collection`s on the live DB) and `exportPackage` must hold the live `col` (exporter keeps only a `weakref`); content-hashed `/_app/` asset names (tests glob, never hardcode); `importDone` must be CUSTOM (raises `InvalidInput` via passthrough); large file uploads/downloads (acceptable for local single-user; no streaming-chunk optimization in core); temp-file cleanup (import: lazy TTL GC in the upload endpoint, since `importDone` gets no path; export: response `BackgroundTask`).
