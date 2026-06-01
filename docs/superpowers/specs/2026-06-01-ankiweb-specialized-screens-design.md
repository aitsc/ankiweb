# ankiweb Sub-project E — Specialized Screens Design

**Status:** design (2026-06-01). Decomposed into E1–E7; each its own plan → implement cycle.

## Goal
Port Anki desktop's remaining specialized screens: statistics/graphs, deck options, change-notetype, custom study, filtered-deck options, import/export, image occlusion.

## Key architectural finding (recon vs the aqt 25.9.4 wheel)
aqt 25.9.4 ships **one unified SvelteKit SPA**, NOT per-page bundles. The SPA (`web_assets/sveltekit/index.html` + `_app/immutable/{entry,chunks,nodes,assets}`) is **already fully vendored** (`fetch_web_assets.py` copies the whole `_aqt/data/web/` tree). graphs/deck-options/change-notetype/card-info/import-*/image-occlusion are **routes** inside it (`/graphs`, `/deck-options/[deckId]`, `/change-notetype/[...ids]`, `/import-csv/[...path]`, …). custom-study and filtered-deck options are **Qt-only dialogs** (no web bundle).

**Serve model (REUSE the SPA):** serve `sveltekit/index.html` at the route path (SPA fallback; the client router reads `location.pathname`) + serve `/_app/{path}` at ROOT (the SPA imports `/_app/immutable/entry/start.*.mjs` at absolute root). ankiweb's existing `assets._resolve`/`_mime` already do the mediasrv `_app/`→`sveltekit/_app/` rewrite and serve `.mjs` as `application/javascript`; the only gap is that the SPA fetches at ROOT (`/_app/...`) while ankiweb served only `/_anki/...`. Data flows over the existing `POST /_anki/<camelMethod>` RPC (protobuf). A spike PROVED the graphs SPA boots + renders end-to-end this way (zero errors, 46 `/_app/` assets + 3 RPC POSTs all 200).

**Parameterization** is via URL PATH params (`/deck-options/{deckId}`, `/change-notetype/{oldId}/{newId}`) — the page's `+page.ts load()` reads them and issues the backend RPC. graphs has no param (whole-collection).

**Bridge/close:** the SPA pages talk to the backend purely over `/_anki/` RPC (no pycmd for data). The only host coupling is deck-options' `deckOptionsReady`/`deckOptionsRequireClose` — these are **Qt-only FrontendService RPCs that RAISE `InvalidServiceIndex` on the headless backend**, so ankiweb implements them as CUSTOM handlers (ready→no-op; requireClose→navigate back), NOT passthrough. graphs/change-notetype need no close bridge.

**Write RPCs need `run_op`:** `update_deck_configs` (deck-options) and `change_notetype` return populated OpChanges and must broadcast (so the deck browser/UI refresh); `set_graph_preferences` returns Empty (no broadcast). `update_deck_configs`/`change_notetype` are NOT yet in the passthrough — add as CUSTOM `run_op` handlers (or passthrough + run_op wiring). Read/compute methods (`get_change_notetype_info`, `get_deck_configs_for_update`, FSRS `compute_*`/`simulate_*`, `get_ignored_before_count`) are read-only → plain passthrough.

## Decomposition (dependency-ordered; each ships a working screen)
- **E1 — Statistics / Graphs (FOUNDATION + first screen).** Serve the SPA at `GET /graphs` + the root `GET /_app/{path}` + `GET /favicon.ico`; all RPC already passes through; read-only, no bridge. Stats link from the deck browser. Establishes the SPA-serve foundation E2/E3 reuse. **← first.**
- **E2 — Deck Options.** Reuse the foundation; `GET /deck-options/{deck_id}`; CUSTOM `deck_options_ready` (no-op) + `deck_options_require_close` (navigate back) + `update_deck_configs` (run_op, broadcasts). Wire the deck-browser gear menu (a Plan-2 deferral) to deep-link `/deck-options/{did}`. Defer FSRS compute-progress streaming.
- **E3 — Change Notetype.** `GET /change-notetype/{ids}`; CUSTOM `change_notetype` (run_op). Deep-link from the browser's change-notetype action (a D4 deferral).
- **E4 — Custom Study** (REBUILD as a server-rendered form, like overview — no web bundle): a form + WS handler over `col.sched.custom_study(...)`.
- **E5 — Filtered-Deck options** (REBUILD, server-rendered form): `get_or_create_filtered_deck` + `add_or_update_filtered_deck`/`rebuild_filtered_deck`; routed from a dyn deck's gear menu.
- **E6 (DEFERRED) — Import/Export:** the SvelteKit import-* routes + file upload + `import_*` handlers + AnkiConnect `export_anki_package`/import. Its own spec.
- **E7 (DEFERRED) — Image Occlusion:** the IO canvas (fabric.js) + image methods + host bridge; partly editor (Sub-project D) territory. Its own spec.

Ship order: E1 → E2 → E3 → (E4, E5) → defer E6, E7.

## Risks
Route ordering (SPA routes before the media catch-all); strict module MIME for `.mjs`; the deck-options close bridge + FSRS long-running compute under the single-worker executor; content-hashed asset names (tests glob, never hardcode); the Qt-only FrontendService methods must be CUSTOM (not passthrough).
