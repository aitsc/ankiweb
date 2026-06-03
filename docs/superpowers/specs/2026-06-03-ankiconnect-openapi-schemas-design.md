# AnkiConnect OpenAPI Schemas — Design

**Goal:** Give the AnkiConnect server (`:8765`) a complete, browsable `/docs` (Swagger UI)
where every one of the 121 actions has a standard Pydantic request schema, so a human (or a
typed-client generator) can see exactly how to call each action — *without* changing the
canonical `POST /` JSON-RPC wire protocol that real AnkiConnect clients depend on.

## Background / constraint

AnkiConnect is, by design, a **single-endpoint JSON-RPC** API: every call is
`POST /` with body `{"action": <name>, "version": 6, "params": {...}}`, dispatched on the
`action` string. ankiweb mirrors this in `dispatch.py::dispatch_one`. Handlers are untyped
`async def fn(rt, **params)`. Today `/openapi.json` therefore has `paths: ["/"]` and
`components.schemas: []` — the docs are useless for discovering call shapes.

We just hardened `POST /`'s behavior to match canonical AnkiConnect (invalid-id leniency).
**That wire contract is sacred** (review_agent and the wider AnkiConnect ecosystem speak it).
So this feature is **purely additive**: a typed REST surface *alongside* `POST /`, never a
rewrite of it.

## Approach: registry-driven parallel REST routes (option B via D)

`POST /` stays byte-identical. We add a second, documented surface — one route per action,
`POST /actions/<name>` — each with a precise Pydantic request body and an envelope response.
Each route is a thin shell that builds the canonical request dict and calls the **same**
`dispatch_one`, so behavior cannot drift from `POST /` (single source of truth).

### Components

1. **`registry.py` (extend, no hot-path change).** `ACTIONS[name] = handler` is unchanged, so
   `dispatch_one` is untouched. Add a parallel `ACTION_SPECS[name] = ActionSpec(...)`. The
   `@action` decorator gains keyword-only options:
   `@action(name, *, params=<Model>, returns=<type>, summary="", description="")`.

2. **`schemas/` package.** One module per action file (`schemas/cards.py`, `schemas/notes.py`,
   …). Each defines one Pydantic model per action, named `<Action>Params`, extending
   `ACBaseModel` (`model_config = ConfigDict(extra="forbid")`). Field names are the **exact**
   AnkiConnect param names (camelCase, all valid identifiers — no aliases needed); defaults
   match the handler's defaults. Nested shapes (e.g. `answers: list[AnswerItem]`,
   `note: NoteSpec`) are modeled as nested `BaseModel`s.

3. **`rest.py` (new).** `build_actions_router()` iterates `ACTION_SPECS` and, for each, adds a
   route whose endpoint signature is built dynamically (`inspect.Signature` with a `params:
   <Model>` parameter — validated by the POC). The endpoint:
   - constructs `req = {"action": name, "version": 6, "params": params.model_dump(exclude_unset=True, by_alias=True)}`,
   - injects the `X-API-Key` header (via `APIKeyHeader`, `auto_error=False`) as `req["key"]`,
   - returns `await dispatch_one(rt, req)` with `rt` built exactly as the `POST /` handler does.
   `response_model` is a generic `Envelope {result: Any, error: str | None}`, refined to a
   per-action `<Action>Response` when the spec declares `returns=` (request precise; response
   loose-by-default, tightened opportunistically).
   Actions with no `params_model` yet fall back to a permissive `LooseParams`
   (`extra="allow"`, no fields) so they still work with a generic body schema — the rollout is
   incremental.

4. **`app.py` (one line).** `app.include_router(build_actions_router())` after actions import.

### apiKey (`ANKIWEB_AC_KEY`)

`AnkiConnectConfig.load` already reads `ANKIWEB_AC_KEY` → `dispatch_one`'s existing gate
enforces `req["key"] == api_key` (with `requestPermission` exempt). Setting a non-empty key
means **review_agent must send the same key** (`cfg.anki.key`, currently `''`) via
`python -m cfg_setup anki` — otherwise its calls get "valid api key must be provided". This is
called out at restart time; review_agent's code is not modified.

## Completeness guard (testing)

- **Cross-check meta-test:** iterate `ACTION_SPECS`; for every spec with a `params_model`,
  assert the model's field set **equals** the handler's accepted param names (from
  `inspect.signature`, minus `rt`). This catches a missing/extra/misspelled param across all
  121 actions at once and makes `extra="forbid"` safe.
- **OpenAPI shape test:** `app.openapi()` has 121 `/actions/*` paths and ≥121 component schemas.
- **Behavior-parity test:** for a sample of actions, `POST /actions/<name>` and the equivalent
  `POST /` envelope return identical results (incl. invalid-id leniency, error enveloping).
- **apiKey test:** with a key configured, a REST call without `X-API-Key` is rejected and one
  with the right key succeeds; `POST /` body-key path still works.

## Out of scope

Per-action precise *response* models for all 121 (start generic, tighten later); changing
`POST /`; validation on `POST /` (must stay lenient); auth on the web app (`:8000`, separate).

## Rollout

1. Phase 1 — registry + `rest.py` + mount + `schemas/cards.py` (all 16) as the reference; TDD.
2. Phase 2 — author the remaining 8 files' models (workflow fan-out, one agent per file).
3. Phase 3 — set `ANKIWEB_AC_KEY`, restart, live-verify `/docs` + key gate.
4. Phase 4 — README (`/docs`, REST layer, `ANKIWEB_AC_KEY`) + UPSTREAM note (ankiweb-specific).
