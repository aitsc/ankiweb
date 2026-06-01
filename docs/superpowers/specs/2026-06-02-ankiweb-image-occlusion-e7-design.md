# ankiweb Sub-project E7 — Image Occlusion Design

**Status:** design (2026-06-02). Decomposed into E7a (route + IO RPC wiring) and E7b (entry points: Add upload + Edit browser-routing + Playwright). Each its own plan → implement cycle.

## Goal
Port Anki 25.9.4's **Image Occlusion** editor by REUSING Anki's already-compiled, already-vendored SvelteKit image-occlusion route (fabric.js bundled) — supporting both **Add** (upload an image → draw masks → create an IO note) and **Edit** (re-open an existing IO note's masks). No editor-embedded path, no canvas rebuild.

## Key feasibility finding (recon + live probes)
Image occlusion is a **reuse**, not a rebuild. The standalone SvelteKit route `ts/routes/image-occlusion/[...imagePathOrNoteId]/` compiles to the vendored node bundle `web_assets/sveltekit/_app/immutable/nodes/8.*.mjs` (379 KB, **fabric.js 5.4.0 inlined**); `image-occlusion` is already in `SVELTEKIT_PAGES` (`assets.py`), but **no URL route is wired** (would 404 today). The standalone route is **self-contained**: it has **zero `pycmd`/`bridgeCommand`** (the file-picker/clipboard coupling lives in the Qt *editor host* `NoteEditor.svelte`, which the standalone route does not use), it loads via `getImageForOcclusion`/`getImageOcclusionNote`, and it **saves via direct `addImageOcclusionNote`/`updateImageOcclusionNote` RPCs**. So E7 = **E1–E3 (SPA reuse) + E2 (CUSTOM write→broadcast) + E6a (upload an image into a managed temp dir + path-confinement)** — all proven.

The route's URL param `[...imagePathOrNoteId]` is **either a note-id (edit mode) or a filesystem image path (add mode)**; `+page.ts` branches on it.

**Backend surface (live-probed, `ImageOcclusionService`):**
- `col.get_image_for_occlusion(path: str) -> GetImageForOcclusionResponse{data: bytes, name: str}` — READ; `path` is an absolute filesystem path or a media-relative filename.
- `col.get_image_occlusion_note(note_id: int) -> GetImageOcclusionNoteResponse` (oneof `note`|`error: str`; `note` has `image_data`, `occlusions`, `header`, `back_extra`, `tags`, `image_file_name`, `occlude_inactive`) — READ; takes a note-id, returns the image bytes inline (no path).
- `col._backend.get_image_occlusion_fields(notetype_id: int) -> ImageOcclusionFieldIndexes` — READ. **Backend-only** (no `col.*` wrapper — call via `*_raw` / passthrough; probed: image=1 header=2 back_extra=3, occlusions=0).
- `col.add_image_occlusion_notetype() -> None` (raw → `OpChanges`) — idempotent ("adds the IO notetype if none exists"). **In anki 25.9.4 the "Image Occlusion" notetype already ships in every fresh collection** (probed), so this call is normally a NO-OP returning an EMPTY `OpChanges` (no flags). It's a safe ensure, not a real broadcast source. The IO notetype is named **"Image Occlusion"**, `type==1` (shared with Cloze) but `originalStockKind==6` (unique — the robust IO marker; Cloze=5, Basic=1).
- `col.add_image_occlusion_note(notetype_id, image_path, occlusions, header, back_extra, tags) -> OpChanges` — WRITE. **`image_path` is an ABSOLUTE FILESYSTEM PATH** (probed: a bare `"pic.png"` raises `BackendIOError: Failed to read`); the backend reads the image from that path and copies it into the collection's media dir, then creates the note. Probed: `op.note=True`, `op.card=True`, the image appears in `col.media.dir()`.
- `col.update_image_occlusion_note(note_id, occlusions, header, back_extra, tags) -> OpChanges` — WRITE. Probed: updates the note (header round-trips).

**Add-mode notetype-id — RESOLVED (verified in `+page.ts:20`, `add-or-update-note.svelte.ts:44`, and `rslib/.../imagedata.rs:50-59`):** add-mode **hardcodes `notetypeId: 0`** and passes it straight to `addImageOcclusionNote({notetypeId: 0, imagePath, …})`. The BACKEND treats `notetype_id == 0` as a SENTINEL: it runs `add_image_occlusion_notetype_inner()` (idempotent create-if-missing) then uses `get_first_io_notetype()`. So **add-mode needs ZERO notetype-id plumbing** — the URL carries ONLY the image path, the upload handler returns ONLY `{path}`, no query param, and `add_image_occlusion_note(notetype_id=0, …)` self-resolves the IO notetype (probed: works).

**Add/edit discriminator (verified `+page.ts:15`):** the route classifies via `/^\d+/.test(param)` — a **leading digit ⇒ edit (noteId)**, otherwise ⇒ **add (image path)**. Absolute Linux temp paths start with `/`, so an uploaded image path correctly classifies as add. The upload handler MUST produce a path that does not start with a digit (it won't — it's an absolute path under the temp dir); a test asserts this.

## Serve model + RPC wiring (E7a)
- Add `GET /image-occlusion/{path:path}` to `build_sveltekit_router` → serve `sveltekit/index.html` (the SPA client-routes on `location.pathname`; `{path:path}` captures a note-id OR an encoded temp image path). `/_app/{path}` already served (E1).
- **Passthrough** (reads, no path): `get_image_occlusion_note` (note_id), `get_image_occlusion_fields` (notetype_id). Both have backend `*_raw` methods.
- **CUSTOM path-confined READ**: `get_image_for_occlusion` — confine `GetImageForOcclusionRequest.path` to the managed upload temp dir (reuse E6a's `import_tmp.is_within(service.settings, path)`) before the backend reads it (prevents the page reading arbitrary server files). **Also `os.utime` (touch) the file on each read** so an active drawing session keeps its temp image fresh (see Security — GC mitigation).
- **CUSTOM write + broadcast** (parse `OpChanges` → `op_changes_to_flags` → `service.emit`, like `updateDeckConfigs`):
  - `add_image_occlusion_note` — confine `AddImageOcclusionNoteRequest.image_path` to the temp dir, then backend + broadcast.
  - `update_image_occlusion_note` — backend + broadcast (note-id; no path).
  - `add_image_occlusion_notetype` — a CUSTOM **ensure** handler (backend + emit). NOTE: in 25.9.4 the IO notetype ships by default, so this returns an EMPTY `OpChanges` and emits nothing in the common case — it's a safe idempotent ensure, not a real broadcast source. (The SPA never POSTs it; only E7b's upload handler calls it server-side.)

## Components (by plan)

### E7a — route + IO RPC wiring
| Unit | Responsibility |
|---|---|
| `build_sveltekit_router` (+1 route) | `GET /image-occlusion/{path:path}` → serve the SPA shell |
| `anki_rpc/passthrough.py` (+2) | `get_image_occlusion_note`, `get_image_occlusion_fields` |
| `anki_rpc/handlers.py` (+4 CUSTOM) | `getImageForOcclusion` (path-confined read + touch-on-read), `addImageOcclusionNote` (path-confined write+broadcast), `updateImageOcclusionNote` (write+broadcast), `addImageOcclusionNotetype` (idempotent ensure) |

### E7b — entry points (Add + Edit) + Playwright
| Unit | Responsibility |
|---|---|
| IO temp subdir + GC | put IO uploads in a dedicated **`<import_tmp_dir>/io/` subdir** (helpers in `import_tmp.py` or alongside): the E6a import GC is non-recursive (`iterdir()`+`is_file()`), so it NEVER sweeps the `io/` subdir (verified) — eliminating the cross-flow deletion risk. A dedicated IO GC (long TTL, e.g. 24 h) runs on IO upload; `is_within` still accepts `io/` paths (they're under `import_tmp_dir`). |
| `POST /image-occlusion/upload` | accept a multipart image; reject non-images → 400; save to the IO temp subdir; call `add_image_occlusion_notetype` (safe idempotent ensure); return **`{path}` only** (no notetype_id — add-mode self-resolves notetype 0) |
| `shell_src/bootstrap.ts` (+`ankiwebImageOcclusion()`) + rebuild | file picker (`accept="image/*"`) → upload → `window.location = "/image-occlusion/" + encodeURIComponent(path)` (NO notetype id — the SPA sends `notetypeId: 0` itself) |
| `ankiweb/screens/deckbrowser.py` (+button) | an "Image Occlusion" button → `ankiwebImageOcclusion()` |
| `ankiweb/screens/browser.py` (edit-routing) | when the opened note's notetype has **`originalStockKind == 6`** (the robust IO marker — NOT name equality; `type==1` is shared with Cloze), route to `/image-occlusion/<noteId>` (via `ankiwebNavigate`) instead of the normal editor iframe |
| `tests/test_image_occlusion_integration.py` | Playwright: add-mode (upload→canvas boots→`getImageForOcclusion` fired) + edit-mode (open IO note→`getImageOcclusionNote` fired) |

## Data flow
**Add:** deck-browser "Image Occlusion" → file picker → `POST /image-occlusion/upload` (image → IO temp subdir; ensure IO notetype) → `{path}` → navigate to `/image-occlusion/<encodeURIComponent(path)>` (an absolute path ⇒ no leading digit ⇒ the route classifies it as add-mode) → SPA loads the image via `getImageForOcclusion(path)` (path-confined + touch-on-read) → user draws masks → `addImageOcclusionNote(notetypeId=0, imagePath=path, occlusions, header, backExtra, tags)` (the SPA hardcodes `0`; the backend self-resolves the IO notetype; the handler confines the path; the backend copies the temp image into media + creates the note) → broadcast → the note exists.
**Edit:** browser → open an "Image Occlusion" note → `ankiwebNavigate("/image-occlusion/<noteId>")` → SPA loads via `getImageOcclusionNote(noteId)` (image bytes inline) → edits masks → `updateImageOcclusionNote(noteId, …)` → broadcast.

## Error handling
- IO RPC backend errors (bad image, malformed occlusions) → the dispatch returns 500 + message; the SvelteKit page renders its own error UI. `get_image_occlusion_note` of a non-IO/missing note returns its `error` oneof — the page handles it.
- A path OUTSIDE the managed temp dir (`get_image_for_occlusion` / `add_image_occlusion_note`) → the handler raises → 500, before the backend reads the file.
- Upload of a non-image / unsupported file → `POST /image-occlusion/upload` 400.
- A browser-opened note that is NOT an IO note → unchanged (the normal editor iframe); only IO-notetype notes route to the IO editor.

## Security
- **Path confinement:** `get_image_for_occlusion` and `add_image_occlusion_note` receive a filesystem path from the URL/request; confine it inside the managed upload temp dir (`import_tmp.is_within`) before the backend touches it — same boundary as E6a. (Edit mode uses a note-id, no path.)
- **GC mid-edit data-loss mitigation (a real risk the design MUST handle):** E6a's `import_tmp.gc()` runs lazily on every upload (60-min mtime TTL) and never refreshes mtime during drawing — so a *concurrent* upload during a long IO session could delete the still-needed IO temp image before save, making `add_image_occlusion_note` raise `BackendIOError`. Mitigations (both): (1) IO uploads live in the **`<import_tmp_dir>/io/` subdir**, which the import GC's non-recursive `iterdir()` never visits (verified); (2) the `getImageForOcclusion` handler **touches the file's mtime on each read**. A test simulates a stale-mtime IO temp file + a triggered import `gc()` and asserts the file survives and the save succeeds.
- The uploaded image lands in the IO temp subdir; `add_image_occlusion_note` copies it into the collection media dir, so the note's image **persists independently of the temp file** — verified by a test that deletes the temp file post-save and confirms the note's image remains in `col.media.dir()`.

## Testing
- **E7a:** TestClient — `GET /image-occlusion/{x}` serves the SPA shell (both a note-id and an encoded path); passthrough/CUSTOM membership; `get_image_for_occlusion` accepts an in-temp-dir path / rejects an out-of-dir path (500); an `addImageOcclusionNote` round-trip (a real image in the temp dir → note created, image copied to media, broadcast); an `updateImageOcclusionNote` round-trip (header changes); `addImageOcclusionNotetype` creates the "Image Occlusion" notetype.
- **E7b:** TestClient — `POST /image-occlusion/upload` (an image → 200 + `{path}` inside the IO subdir, path does NOT start with a digit so it classifies as add-mode; a non-image → 400); the browser routes a note whose notetype has `originalStockKind==6` to `/image-occlusion/<id>` AND a renamed/cloned IO notetype still routes (name-independent) while a Cloze note does NOT; the **GC-survival** test (stale IO temp file + import `gc()` → survives + save works); the **media-persistence** test (delete the temp post-save → the note's image remains in media). Playwright — add-mode (upload an image → the IO canvas SPA boots, `getImageForOcclusion` POST fired, fabric `<canvas>` present, zero errors) + edit-mode (seed an IO note via the backend → open `/image-occlusion/<noteId>` → the SPA boots, `getImageOcclusionNote` fired).

## Decomposition (dependency-ordered; each ships working functionality)
- **E7a — route + IO RPC wiring** (the SPA-reuse data plumbing). **← first.**
- **E7b — entry points** (Add upload + deck-browser button + the `ankiwebImageOcclusion` shell fn; Edit browser-routing) + Playwright boot proofs.

Ship order: E7a → E7b. After E7, Sub-project E (E1–E7) is complete.

## Risks
Route ordering — the new `GET /image-occlusion/{path:path}` goes in `build_sveltekit_router`, which `create_app` mounts BEFORE `build_media_router`'s catch-all `/{path:path}`; without the explicit route the IO URL falls through to media → 404 (same precedence concern as E1/E6a, but spell out the two-router ordering). The **GC mid-edit data-loss risk** (concurrent upload sweeping the IO temp image before save) — mitigated by the `io/` subdir (non-recursive GC skips it) + touch-on-read (see Security); MUST be tested. **IO-note edit-detection MUST use `originalStockKind==6`, not name equality** (the notetype is user-renameable; `type==1` is shared with Cloze). `image_path` MUST be an absolute readable path that still exists at save time (the backend reads it). The add/edit discriminator is `/^\d+/.test(param)` — absolute paths (leading `/`) classify as add; assert this. Path-confinement on the two path-bearing IO fields. Content-hashed `/_app/` asset names + the 379 KB fabric node 8 (tests glob, never hardcode). The occlusions string is produced by the SvelteKit canvas (`exportShapesToClozeDeletions`) — TestClient round-trip tests use a minimal valid string (probed: `{{c1::image-occlusion:rect:left=.1:top=.1:width=.2:height=.2}}` works) while Playwright exercises the real canvas. `image-occlusion` is already in `SVELTEKIT_PAGES` so only the GET route + RPC wiring are missing. `get_image_occlusion_fields` is backend-only (no `col.*` wrapper) — passthrough uses the `*_raw` method, so this is fine.
