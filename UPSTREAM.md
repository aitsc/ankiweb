# Upstream reference pins

ankiweb is a *translation-style* port of Anki + AnkiConnect. This file records the exact
upstream sources it was built against, so that when Anki or AnkiConnect publish updates you
can diff against these points and decide whether ankiweb needs to follow.

## Runtime dependency — the source of truth for behavior

- **anki (pylib) + the vendored frontend: `25.9.4`** — pinned in `pyproject.toml` as `anki==25.9.4`.
- The compiled frontend under `ankiweb/web_assets/` (gitignored) is vendored from the **aqt `25.9.4`**
  wheel by `tools/fetch_web_assets.py`.

> **The version pin is load-bearing.** `_rsbridge.so` and the compiled frontend carry a *buildhash*
> that must match (`anki.buildinfo`). So `anki`, `aqt`, and the vendored `web_assets/` must all be the
> **same** version — bumping one means re-vendoring the others.

## Reference source repos (read-only, used while porting)

These are the local checkouts the port was written against (read for understanding, not run):

| repo | remote | commit | tag / version | date |
|---|---|---|---|---|
| **Anki** | github.com/ankitects/anki | `1822a7c76c6751575144bbb0996a07006080da24` | `25.09.2-204-g1822a7c` (`main`; `.version` = 25.09.2) | 2026-05-29 |
| **AnkiConnect** | git.sr.ht/~foosoft/anki-connect | `de6e6e1b8aaf4ae195eb1d1ff6db5409b99b2a3e` | `25.11.9.0` (+1, `master`) | 2025-12-05 |

> ⚠️ The Anki **source** checkout above (`main`, 25.09.2 + 204 commits) is *newer* than the pinned
> **runtime** `25.9.4` — it was read to understand the code, not version-matched. For an exact
> source↔runtime diff, check out the `25.9.4` release tag in the anki repo before comparing.

## When upstream updates — what to re-check

### Anki (a new aqt/anki release, e.g. 25.9.5 / 26.x)
1. **Bump + re-vendor + retest.** Change `anki==X` in `pyproject.toml`, re-run
   `python tools/fetch_web_assets.py` (re-vendors `web_assets/` from the new aqt wheel), rebuild the
   shell (`npm run build`), run the full pytest suite. The buildhash pin means a version bump
   *requires* re-vendoring — you cannot mix versions.
2. **SvelteKit routes.** `ankiweb/assets.py` (`SVELTEKIT_PAGES` + `build_sveltekit_router`): did any
   reused page get added/renamed/removed (deck-options, change-notetype, import-*, image-occlusion,
   card-info, graphs)?
3. **Backend RPC names.** `ankiweb/anki_rpc/passthrough.py` (`PASSTHROUGH` / `CONCURRENT`) +
   `handlers.py` (`CUSTOM`) dispatch to `col._backend.<method>_raw`. A renamed/removed backend method
   silently 404s the dispatch — re-verify the method names.
4. **Reused-frontend bridge commands.** `editor.js` / `reviewer.js` toolbars emit `bridgeCommand`s;
   a new button = a new command ankiweb may need to handle (see the dead-control audit:
   `docs/superpowers/specs/2026-06-03-ankiweb-editor-reviewer-completeness-design.md`).
5. **Translation keys.** Anki occasionally renames `tr.<key>()` keys; a missing key raises
   `AttributeError` at render. Re-verify the i18n maps (the I2 spec) and the new Tools/notetype labels.

### AnkiConnect (new commits / actions)
1. Diff `plugin/__init__.py` `@util.api()` actions against `ankiweb/ankiconnect/actions/*.py` and port
   any new ones. ankiweb already covers ~the full action surface minus sync.
2. The reference commit above added a *"set fields in the Add Note dialog"* endpoint — already
   mirrored by ankiweb's `guiAddNoteSetData` (sub-project D6).
3. **OpenAPI schemas are ankiweb-specific** (upstream AnkiConnect has no `/docs`). A new action
   needs a `<Action>Params` model in `ankiweb/ankiconnect/schemas/<file>.py` wired via
   `@action(..., params=...)`; until then it falls back to a loose body. The
   `test_params_model_matches_handler_signature` test fails if a model's fields drift from its
   handler signature, so it flags any action whose params changed upstream. See
   `docs/superpowers/specs/2026-06-03-ankiconnect-openapi-schemas-design.md`.

---

**Update this file whenever you re-vendor or re-base ankiweb against a newer upstream.**
