# ankiweb — Sub-project B: AnkiConnect API (design)

- Date: 2026-06-01
- Status: design; to be split into Plans B1–B4.
- Scope: replicate AnkiConnect's full HTTP API (122 actions) on top of the existing `CollectionService`, faithful enough that existing AnkiConnect clients (Yomitan/Yomichan, etc.) work unchanged. **No sync.** Built in the `ankiweb` conda env.

This is the second headline feature. Sub-project A (Foundation) and C (Study Loop) are already done & merged. Reference: AnkiConnect source `/mnt/sda/git/tools/anki-connect/plugin/{__init__,web,util,edit}.py` and the in-session recon map.

---

## 1. Architecture decisions

### 1.1 Separate app on port 8765 (sharing the collection)
AnkiConnect clients hardcode `http://127.0.0.1:8765/` and POST JSON to `/`. Our web UI already uses `GET /` (deck browser) on port 8000. So the AnkiConnect API is a **separate FastAPI app** served on **8765**, POSTing to `/`, with its **own** CORS/auth model (NOT the web UI's host-guard). Both apps share **one** `CollectionService` (single open `Collection`, serialized) so an API `addNote` is instantly visible in the web UI and vice-versa.

**Shared-service wiring.** Refactor `create_app(settings, service=None, hub=None)`: when `service`/`hub` are injected, the lifespan uses them and does NOT open/close them (the caller owns the lifecycle); when omitted, the lifespan creates+opens+closes its own (preserves the standalone/test path). Add `create_ankiconnect_app(settings, service=None, hub=None, ui_state=None)` with the same convention. The `python -m ankiweb` entrypoint creates one `CollectionService` + `BridgeHub`, `await service.open()`, builds both apps with them injected, runs **two uvicorn servers in one asyncio event loop** (`asyncio.gather(web.serve(), api.serve())` — so the service's `asyncio.Lock` is shared across both), and `await service.close()` on shutdown. Tests use the standalone form (`create_ankiconnect_app(settings)` + `TestClient`).

### 1.2 The JSON-RPC contract (faithful to AnkiConnect)
- Single endpoint **`POST /`** (and `GET /` empty-body and `OPTIONS /`). Request body JSON: `{action: str(required, non-empty), version?: int (default 4), params?: object (default {}), key?: str}`.
- Dispatch: look up `action` in a flat `{name: handler}` registry; call `handler(rt, **params)` (params splatted as kwargs; handlers declare action-specific kwargs with defaults; unknown action → error). `rt` is a small runtime context exposing `.service`, `.hub`, `.ui_state`, `.settings`.
- **Response envelope** (switch on request `version`): `version <= 4` → the bare result value; `version >= 5` (clients use 6) → `{"result": <value>, "error": null}`. **Errors are ALWAYS enveloped** regardless of version: `{"result": null, "error": "<str(exc)>"}`. HTTP status stays **200** for in-band errors (403 only for disallowed CORS origin). Replicate this asymmetry exactly.
- **`version` action** returns `6`. **Empty-body GET/POST `/`** returns `{"apiVersion": "AnkiConnect v.6"}` (liveness probe).
- **`multi(actions)`**: `params.actions` is a list of full request objects; dispatch each through the same handler path (each enveloped per its own version; per-item try/except so one failure doesn't abort the batch); return the list of replies.
- **`apiReflect(scopes, actions=None)`**: if `"actions"` in scopes → `{"scopes":["actions"], "actions":[<registry names>]}`, optionally filtered to `actions`.
- The legacy version-rename machinery (`@util.api((v,"altName"))`) is unused in current AnkiConnect (all 122 are bare `@api()`), so we use a flat name→handler registry; action name == method name.

### 1.3 Auth + CORS (faithful)
- **apiKey**: config value, default `null` (disabled). If set, every action except `requestPermission` must include matching `key` (plain string equality) else error.
- **CORS** (`allowOrigin` logic): `webCorsOriginList` default `["http://localhost"]`; `*` → allow all; exact `Origin` match → allow; if `http://localhost` listed, also auto-allow `127.0.0.1` (any scheme/port) + `chrome-extension://`/`moz-extension://`/`safari-web-extension://`; **no `Origin` header → allowed** (curl/server-to-server). Disallowed origin (and not `requestPermission`) → **403**. `OPTIONS` preflight returns the CORS headers (+ `Access-Control-Allow-Private-Network: true` when requested). Responses always include `Access-Control-Allow-Origin` + `Access-Control-Allow-Headers: *`.
- **`requestPermission`**: special-cased — runs even on a disallowed origin; the server injects `allowed` (CORS result) + `origin`. Single-user local → **auto-grant** (return `{permission:"granted", requireApikey: <bool>, version:6}` when allowed; `{permission:"denied"}` otherwise); persist approved origins to config. (No Qt dialog.)
- Config lives in a plain JSON file (NOT Anki's add-on manager): `apiKey`, `webCorsOriginList`, `webBindAddress` (default 127.0.0.1), `webBindPort` (default 8765), `ignoreOriginList`.

### 1.4 The `gui*` actions (UI-coupled)
The `gui*` actions drive/read the **live web UI** (the reviewer's current card, the browser's selection, opening dialogs). They require: (a) the `BridgeHub` (to push commands to the web UI over WebSocket) and (b) a server-side **UI-state mirror** that the web screens report into (e.g. the reviewer reports its current card + side; the browser reports its selection). Plan B4 builds a minimal `ui_state` (current reviewer card/side, review-active flag) populated by the reviewer screen, and maps each `gui*` action to: (a) a web-UI command via the hub, (b) a backend op + refresh, or (c) unsupported/no-op. This couples B to C's screens, so gui* comes last (Plan B4).

---

## 2. Action catalog (122) — grouping & mapping approach

Every action is a thin wrapper over the `CollectionService` (the high-level `Collection` API or `col.db` SQL). Full per-action params/returns/mapping are in the recon map; the plans carry the exact code. Counts approximate.

| Group | ~count | Examples → mapping |
|---|---|---|
| **Misc/Collection/Profiles** | ~12 | `version`→6; `requestPermission`; `getProfiles`/`getActiveProfile`/`loadProfile`→single-profile constants; `multi`; `reloadCollection`→`col.reset()`; `apiReflect`; `exportPackage`/`importPackage`→`col.export/import_anki_package`; `sync`→**excluded** |
| **Statistics** | ~7 | `getNumCardsReviewedToday`/`...ByDay`/`getCollectionStatsHTML`/`cardReviews`/`getReviewsOfCards`/`getLatestReviewID`/`insertReviews` → `col.db` SQL on `revlog` + `col.sched.day_cutoff` |
| **Decks** | ~13 | `deckNames`/`deckNamesAndIds`/`getDecks`/`createDeck`→`col.decks.id`; `changeDeck`→`col.set_deck`; `deleteDecks`→`col.decks.remove`; `getDeckConfig`/`saveDeckConfig`/`setDeckConfigId`/`cloneDeckConfigId`/`removeDeckConfigId`; `getDeckStats`→`deck_due_tree` walk; `deckNameFromId` |
| **Notes** | ~22 | `addNote`/`addNotes`(rollback-all-on-error)/`canAddNote(s)`(+ErrorDetail); `updateNoteFields`/`updateNote`/`updateNoteModel`; tags (`addTags`/`removeTags`/`getTags`/`clearUnusedTags`/`replaceTags`/`updateNoteTags`/`getNoteTags`); `findNotes`→`col.find_notes`; `notesInfo`/`notesModTime`; `deleteNotes`→`col.remove_notes`; `removeEmptyNotes`; `cardsToNotes` |
| **Cards** | ~20 | `findCards`→`col.find_cards`; `cardsInfo`(uses `col._backend.get_scheduling_states`+`describe_next_states`); `cardsModTime`; `getEaseFactors`/`setEaseFactors`/`setSpecificValueOfCard`; `suspend`/`unsuspend`/`suspended`/`areSuspended`/`areDue`/`getIntervals`; `forgetCards`→`schedule_cards_as_new`; `relearnCards`(SQL); `answerCards`(`start_timer`+`answerCard`); `setDueDate`→`col.sched.set_due_date` |
| **Models/Note-types** | ~25 | `modelNames`/`...AndIds`/`modelFieldNames`/`...Descriptions`/`...Fonts`/`modelFieldsOnTemplates`/`modelTemplates`/`modelStyling`/`findModelsBy{Id,Name}`/`modelNameFromId`; `createModel`; `updateModelTemplates`/`updateModelStyling`; `findAndReplaceInModels`; template & field mutators (`modelTemplate{Rename,Reposition,Add,Remove}`, `modelField{Rename,Reposition,Add,Remove,SetFont,SetFontSize,SetDescription}`) |
| **Media** | 5 | `storeMediaFile`(base64/path/url→`col.media.write_data`; `util.download`→`httpx`)/`retrieveMediaFile`/`getMediaFilesNames`/`getMediaDirPath`/`deleteMediaFile` |
| **gui\*** | ~22 | `guiBrowse`/`guiSelectCard`/`guiSelectedNotes`/`guiAddCards`/`guiAddNoteSetData`/`guiEditNote`/`guiCurrentCard`/`guiReviewActive`/`guiStartCardTimer`/`guiShowQuestion`/`guiShowAnswer`/`guiAnswerCard`/`guiPlayAudio`/`guiUndo`/`guiDeckOverview`/`guiDeckBrowser`/`guiDeckReview`/`guiImportFile`/`guiExitAnki`/`guiCheckDatabase` → bridge commands + ui_state (see §1.4) |

**Faithful-behavior gotchas (from recon) to preserve:** field matching case-insensitive on add/change but case-sensitive on `updateNoteFields`; `addNotes` rolls back all created notes if any fails; `version` field defaults to 4; success of `version<=4` is bare; `notesInfo`/`getReviewsOfCards` batch SQL vars at 999; `forgetCards`/`cardsInfo` use `col._backend`; raw `revlog` SQL for stats; `setDueDate` days is a string range (e.g. `"3"`, `"1-7"`).

---

## 3. Decomposition into plans

- **Plan B1 — Infrastructure + Decks + Misc + Statistics.** The 8765 app, shared-service wiring + entrypoint running both servers, the JSON-RPC dispatcher (envelope/version/multi/apiReflect/version/empty-probe), CORS+apiKey middleware, `requestPermission` (auto-grant), the config file, the action registry; then the Decks (~13), Misc/Collection/Profiles (~12, minus sync), and Statistics (~7) actions. Delivers a runnable, client-pingable API.
- **Plan B2 — Notes + Cards.** The heavy CRUD (~42 actions), incl. the `createNote` builder (duplicate/empty detection, media fields), `addNotes` rollback, `cardsInfo` scheduling states.
- **Plan B3 — Models + Media.** Note-type introspection + mutators (~25) and the 5 media actions (base64/path/url, `httpx` download).
- **Plan B4 — gui\* actions.** The `ui_state` mirror (reviewer reports current card/side; review-active), hub-driven UI commands, and the ~22 `gui*` actions mapped per §1.4.

Each plan: write → adversarial verification (anki API in env, FastAPI/contract, consistency) → fix → subagent-driven TDD → merge.

---

## 4. Out of scope / deferrals

- **`sync`** action — excluded (no sync); returns an error.
- Anki **add-on manager** config → replaced by a plain JSON config file.
- `requestPermission` interactive Qt dialog → auto-grant for single-user local.
- `guiExitAnki` → no-op/unsupported (no clean web analog); `guiImportFile`/`guiEditNote`/`guiAddCards` depend on D's editor/import UI — B4 routes what it can and stubs the rest with faithful response shapes.
- `getCollectionStatsHTML` uses legacy `col.stats()` — verify it still exists in `anki==25.9.4`; if removed, return a minimal report or defer.
- Testing uses `httpx`/`TestClient` against the standalone ankiconnect app; a small set of real-client-shaped requests (Yomitan's `deckNames`/`findNotes`/`addNote`/`guiBrowse`) as integration checks.
