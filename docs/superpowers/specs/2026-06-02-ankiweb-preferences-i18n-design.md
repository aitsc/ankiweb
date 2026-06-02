# ankiweb Sub-project — Preferences + Internationalization (i18n) Design

**Status:** design (2026-06-02). Decomposed into I1 (language plumbing), I2 (i18n the
hand-written screens), I3 (the Preferences form). Each its own plan → implement cycle.

## Goal
Add the two pieces still missing vs Anki desktop: (1) a **Preferences** screen for the
collection-level settings (scheduling / reviewing / editing / backups), and (2) **full UI
language support** — the chosen language drives both the reused Anki frontend AND ankiweb's
own hand-written screens, so the whole app can be Chinese (or any of Anki's 53 locales).

**Language is chosen at startup via `ANKIWEB_LANG`** (an env var). There is **no in-UI live
switcher**; changing language = change `ANKIWEB_LANG` + restart. (User decision — keeps it
simple and avoids a runtime collection reopen just for language.)

**Out of scope:** Anki sync, add-ons, and a runtime language switcher.

## Key findings (live-probed)
- **`col.get_preferences()` / `col.set_preferences(prefs)`** carry exactly 4 sections:
  - `scheduling`: `rollover`, `learn_ahead_secs`, `new_review_mix` (enum), `new_timezone` (bool), `day_learn_first` (bool)
  - `reviewing`: `hide_audio_play_buttons`, `interrupt_audio_when_answering`, `show_remaining_due_counts`, `show_intervals_on_buttons`, `time_limit_secs` (int), `load_balancer_enabled`, `fsrs_short_term_with_steps_enabled`
  - `editing`: `adding_defaults_to_current_deck`, `paste_images_as_png`, `paste_strips_formatting`, `default_search_text` (str), `ignore_accents_in_search`, `render_latex`
  - `backups`: `daily`, `weekly`, `monthly`, `minimum_interval_mins` (all int)
- **Language requires the locale to be set BEFORE the collection is opened.** Probed:
  `anki.lang.set_lang("zh-CN")` does **not** change an already-open collection's `col.tr`
  (still "Add"), but a **freshly-opened** collection picks it up (`col.tr.actions_add()` →
  "添加", `qt_misc_browse()` → "浏览", `decks_study()` → "学习"). Since ankiweb fixes the
  language at startup, calling `set_lang(settings.lang)` **before** `Collection(path)` in
  `CollectionService.open()` is sufficient — **no runtime reopen needed for language**.
  `set_lang` is process-global; one call suffices (later `reopen()`s inherit it).
- **`anki.lang.tr_legacyglobal`** is a **collection-free global translator** that reflects
  the current `set_lang` (probed: `.actions_add()` → "添加" after `set_lang("zh-CN")`). This
  lets ankiweb's hand-written pages AND the toolbar (which has no `col`) translate via a
  single global helper instead of threading `col.tr` everywhere. **It is a singleton whose
  `.backend` weakref `set_lang` mutates in place** — so a bound `from anki.lang import
  tr_legacyglobal as tr` import tracks the active language (no re-read needed) — **BUT it is
  `None` and CRASHES until `set_lang` is called at least once** (see the unconditional-`set_lang`
  requirement in I1). `col.tr` is a separate per-collection backend that works in English even
  without `set_lang`.
- **`col.set_preferences(prefs)` returns an `OpChanges`** (config/browser_table/study_queues/
  mtime), and it writes each PRESENT section's scalars **wholesale** (omitted scalars in a present
  section revert to proto3 defaults) — so the handler must merge onto a fresh `get_preferences()`.
- **Anki ships 1732 translation keys** (directly enumerated via `dir(tr_legacyglobal)`) —
  coverage of ankiweb's hand-written labels is very high. Confirmed direct hits (zh-CN): `actions_decks`→牌组, `actions_add`→添加,
  `qt_misc_browse`→浏览, `qt_misc_stats`→统计, `actions_options`→选项,
  `actions_custom_study`→自定义学习, `actions_rebuild`→重建, `actions_import`→导入,
  `actions_export`→导出, `actions_save`→保存, `actions_cancel`→取消,
  `statistics_counts_new_cards`→未学习, `statistics_counts_learning_cards`→学习中
  (note `actions_name`→"名称：" carries a trailing fullwidth colon — it's a field-label key, not
  a bare noun). The previously-unresolved labels were also resolved by the verification:
  `studying_study_now`→开始学习, `studying_empty`→清空, `studying_unbury`→取消搁置,
  `preferences_preferences`→设置, `decks_create_deck`→创建牌组,
  `qt_misc_create_filtered_deck`→创建筛选牌组, `fields_description`→描述. The full per-screen
  map is in the I2 plan; truly keyless ankiweb-specific labels (e.g. "Source") stay English.
- `ANKIWEB_LANG` takes an Anki language code (`zh-CN`, `ja`, `en`, …; `set_lang` tolerates
  `zh-CN`/`zh_CN`). Empty/unset = Anki's default (English).

## Architecture

### Language plumbing (I1)
- `Settings.lang` (env `ANKIWEB_LANG`, default `""`).
- `CollectionService.open()` calls **`anki.lang.set_lang(settings.lang or "en")` UNCONDITIONALLY,
  before** opening the `Collection`. **It must always run** — verified: if `set_lang` is never
  called, `anki.lang.current_i18n` is `None` and `tr_legacyglobal.<key>()` raises `TypeError:
  'NoneType' object is not callable` (at `anki/_backend.py:192`; **opening a `Collection` does NOT
  initialize the global** — probed: `current_i18n` stays `None` after `Collection(path)`, only
  `set_lang` initializes it). `set_lang("")` / `set_lang("en")` / an unknown code all safely yield
  English without raising. `reopen()` re-applies the same `set_lang` for self-consistency
  (defensive against a future second service with a different lang; the single-service topology
  makes the inherited process-global sufficient today). This call
  localizes `col.tr`, `tr_legacyglobal`, and the reused frontend (`i18n_resources`).
- **`CollectionService.open()` is NOT a sufficient chokepoint by itself.** `render_page`
  (`page.py:46`) is a standalone function with no `Collection`, and the toolbar (made per-request
  in I2) calls `tr.<key>()` — so any code path that renders the toolbar **without opening a
  collection** would hit the `NoneType` crash. The existing suite has exactly such paths:
  `test_license_about.py:32`, `test_global_toolbar.py:10/:18`, `test_night_mode.py:16`,
  `test_screens_page.py:5/:17` call `render_page()` directly and `conftest.py` has no `set_lang`
  fixture. **Therefore `ankiweb/i18n.py` MUST self-initialize**: a guarded one-time
  `set_lang` at import (idempotent — only when not yet set), e.g.
  `import anki.lang; if anki.lang.current_i18n is None: anki.lang.set_lang(_lang_or_en())` **then**
  `from anki.lang import tr_legacyglobal as tr`. `CollectionService.open()` still runs its own
  `set_lang(settings.lang or "en")` — when `ANKIWEB_LANG` is set it overrides the import-time
  English default (in-place backend mutation), and the import-time guard makes the col-free render
  paths safe.
- `ankiweb/i18n.py` exports `tr` (verified safe to bind — `tr_legacyglobal` is a singleton whose
  `.backend` weakref `set_lang` mutates in place, read per call, so a bound import tracks the
  active language; no re-read / `def tr()` indirection needed). Usage `tr.actions_add()`. **All
  screens (and the per-request toolbar) import `tr` from `ankiweb.i18n`, never from `anki.lang`
  directly** — so the self-init guard always runs first. col-bearing render functions may
  equivalently use `col.tr`. (Belt-and-suspenders: an autouse `set_lang("en")` test fixture in
  `conftest.py` documents the default-English contract for the col-free tests.)

### i18n the hand-written screens (I2)
- Replace hardcoded English in `deckbrowser`, `overview`, `reviewer`, `browser`, `add`,
  `custom_study`, `filtered_deck`, `export`, `about`, and the `page.py` toolbar with `tr.<key>()`.
- **`page.py`'s `_TOOLBAR_HTML` / `_TOOLBAR_CSS` are module-level constants built at import
  time (before `set_lang` and before any request)** — a naive `tr.` call inside them would
  freeze the English text. **They MUST become a per-request function** that builds the toolbar
  (calling `tr.<key>()`, with `tr` imported from `ankiweb.i18n` so the self-init guard runs) on
  each `render_page`. (col-bearing render fns already run per request, so `col.tr`/`tr.` there is
  fine.)
- The **label → Anki-key map is verified (live zh-CN)** — see the table in the I2 plan; ~80–90%
  coverage of ankiweb's ~55 hand-written strings using existing Anki keys. Examples:
  `actions_decks`/`actions_add`/`qt_misc_browse`/`qt_misc_stats` (toolbar);
  `studying_study_now`→开始学习, `studying_empty`→清空, `studying_unbury`→取消搁置,
  `decks_create_deck`→创建牌组, `qt_misc_create_filtered_deck`, `actions_options`,
  `actions_custom_study`, `studying_show_answer`, `studying_again/hard/good/easy` (ease buttons),
  `scheduling_congratulations_finished` (congrats), the `exporting_*` / `custom_study_*` namespaces.
  **Caveats:** `actions_name`→"名称：" carries a trailing colon (for a bare "Name" use a
  colon-free key); "Edit Description" is a composite (`actions_edit`+`fields_description`);
  the filtered-deck OK button uses **`decks_build`** for "Build" (EN `'Build'`, zh `'创建筛选牌组'`)
  and **`actions_rebuild`** for "Rebuild" (EN `'Rebuild'`, zh `'重建'`) — verified against the
  current literals `oklabel = "Rebuild" if is_edit else "Build"` (`filtered_deck.py:34`). Do **NOT**
  use `actions_build_filtered_deck` (EN `'Build Deck'`) — it would change the visible text and break
  `test_filtered_deck.py:54` (`>Build<`). "Forget" maps to `actions_forget_card` which now renders
  **"Reset Card"** (Anki renamed it) — so its English text changes.
- **Keyless ankiweb-specific strings stay English** (no Anki key): "Source" + the `/about`
  AGPL prose, "Limit" / "Preview delays" / "Package options" / "CSV options" form legends,
  "Back to Decks", "Unsuspend" (only a combined Unbury/Unsuspend key), "Type" (add), the
  `(.csv)`/`(.colpkg)` extension suffixes.
- **Default-English requirement (load-bearing):** with no `ANKIWEB_LANG`, every label must
  render its current English literal so the existing suite stays green. ~27 assertions across
  `test_global_toolbar.py` (Decks/Add/Browse/Stats), `test_overview.py` / `test_study_loop_home.py`
  ("Study Now"), `test_filtered_deck.py` (`>Build<` at :54, `>Rebuild<` at :63),
  `test_custom_study.py` ("Custom Study
  Session"), `test_deckbrowser_nav.py` (/add link) assert English — I2 keeps them green, updates
  only where the Anki key's English differs from the old literal (e.g. Forget→Reset Card), and
  adds a parametrized test (default→English literal, `ANKIWEB_LANG=zh-CN`→the CJK string).
- Numbers/HTML structure unchanged — only user-visible text is translated.

### Preferences form (I3)
- `GET /preferences` → a server-rendered form (like E4/E5) rendering the 4 `get_preferences()`
  sections. **Control map (verified field types):** the **13 bool** fields → checkboxes; the
  **7 uint32** fields (scheduling `rollover`/`learn_ahead_secs`, reviewing `time_limit_secs`,
  backups `daily`/`weekly`/`monthly`/`minimum_interval_mins`) → number inputs;
  `editing.default_search_text` (string) → text input; `scheduling.new_review_mix` (the only
  enum: `DISTRIBUTE=0`/`REVIEWS_FIRST=1`/`NEW_FIRST=2`, labels
  `scheduling_mix_new_cards_and_reviews`/`scheduling_show_new_cards_after_reviews`/`scheduling_show_new_cards_before_reviews`)
  → `<select>`. **Caveat:** `scheduling.new_timezone` (bool) is shown in Anki as the INVERSE
  checkbox "Legacy timezone handling" (`preferences_legacy_timezone_handling`; checked ⇒ legacy
  ⇒ `new_timezone=False`) — render it as the legacy-inverse or a neutral label, not a raw
  "new_timezone" checkbox. **A second inverse:** `reviewing.hide_audio_play_buttons` (bool) is
  shown as `preferences_show_play_buttons_on_cards_with` ("Show play buttons on cards with audio";
  checked ⇒ show ⇒ `hide_audio_play_buttons=False`) — negate it too.
- **Section headers:** `preferences_scheduling` / `preferences_review` (NO args — it's just
  "Review"/"复习"; the earlier "takes args" note was wrong) / `preferences_editing` /
  `preferences_backups`.
- **Verified per-field label keys** (probed live; **20 of the 22 fields have a real key, 2 need an
  English-literal fallback** — there is no suitable Anki key, see I1's no-runtime-fallback rule):

  | field | key (or ENGLISH-FALLBACK) | en |
  |---|---|---|
  | sched `rollover` | `preferences_next_day_starts_at` | Next day starts at |
  | sched `learn_ahead_secs` | `preferences_learn_ahead_limit` | Learn ahead limit |
  | sched `new_review_mix` (enum) | `scheduling_mix_new_cards_and_reviews` / `_show_new_cards_after_reviews` / `_show_new_cards_before_reviews` | Mix… / Show new after / before |
  | sched `new_timezone` (inverse) | `preferences_legacy_timezone_handling` | Legacy timezone handling… |
  | sched `day_learn_first` | `preferences_show_learning_cards_with_larger_steps` | Show learning cards with larger steps before reviews |
  | rev `hide_audio_play_buttons` (inverse) | `preferences_show_play_buttons_on_cards_with` | Show play buttons on cards with audio |
  | rev `interrupt_audio_when_answering` | `preferences_interrupt_current_audio_when_answering` | Interrupt current audio when answering |
  | rev `show_remaining_due_counts` | `preferences_show_remaining_card_count` | Show remaining card count |
  | rev `show_intervals_on_buttons` | `preferences_show_next_review_time_above_answer` | Show next review time above answer buttons |
  | rev `time_limit_secs` | `preferences_timebox_time_limit` | Timebox time limit |
  | rev `load_balancer_enabled` | **ENGLISH-FALLBACK** "Enable load balancer" | (only `actions_toggle_load_balancer`="Toggle Load Balancer" exists — a menu verb, not a label) |
  | rev `fsrs_short_term_with_steps_enabled` | **ENGLISH-FALLBACK** "Use FSRS for short-term scheduling (with steps)" | (no key exists at all) |
  | edit `adding_defaults_to_current_deck` | `preferences_when_adding_default_to_current_deck` | When adding, default to current deck |
  | edit `paste_images_as_png` | `preferences_paste_clipboard_images_as_png` | Paste clipboard images as PNG |
  | edit `paste_strips_formatting` | `preferences_paste_without_shift_key_strips_formatting` | Paste without shift key strips formatting |
  | edit `default_search_text` | `preferences_default_search_text` | Default search text |
  | edit `ignore_accents_in_search` | `preferences_ignore_accents_in_search` | Ignore accents in search (slower) |
  | edit `render_latex` | `preferences_generate_latex_images_automatically` | Generate LaTeX images (security risk) |
  | backups `daily` | `preferences_daily_backups` | Daily backups to keep: |
  | backups `weekly` | `preferences_weekly_backups` | Weekly backups to keep: |
  | backups `monthly` | `preferences_monthly_backups` | Monthly backups to keep: |
  | backups `minimum_interval_mins` | `preferences_minutes_between_backups` | Minutes between automatic backups: |

  (Codex's claim that hide-audio / show-intervals / render-latex / minimum-interval keys are
  "missing" was wrong — they exist under non-obvious names, above. Only `load_balancer_enabled`
  and `fsrs_short_term_with_steps_enabled` genuinely lack a label key.)
- Submit (WS `pycmd("savePrefs:"+json)`, like custom-study) → a `preferences` handler that
  re-fetches `get_preferences()`, applies the submitted fields, and calls
  `col.set_preferences(prefs)` via `run_op` (verified: it returns an `OpChanges` with
  config/browser_table/study_queues/mtime → broadcast fires), then on success `ankiwebNavigate`s
  back. **Errors follow the E4/E5 pattern, NOT an HTTP 500** (the WS bridge `ws.py:36-37` swallows
  handler exceptions to `None` and there is no HTTP response post-upgrade): the form renders a
  `<div id='err'>` region and a `window.ankiwebPrefsError` JS callback; on a backend error the
  handler calls `hub.push_call("preferences", "ankiwebPrefsError", [msg])` (exactly as
  `custom_study.py:149-155` / `filtered_deck.py:127-133` do) — the form stays in place with its
  values intact and no navigation fires.
  **`set_preferences` writes each PRESENT section's scalars wholesale** (an omitted scalar in a
  present section resets to its proto3 default — verified), so the handler MUST **merge the
  submitted values onto a fresh `get_preferences()` and resend all 4 sections** (the form
  renders all of them) — never a partial section.
- A "Preferences" entry in the global toolbar — key **confirmed**: `preferences_preferences`
  ("Preferences" / "设置"); no fallback needed.

## Decomposition (dependency-ordered; each ships independently)
- **I1 — Language plumbing** (smallest): `Settings.lang` + `set_lang` before open +
  `ankiweb/i18n.py`. Immediately makes the **reused frontend** (SvelteKit / reviewer.js /
  editor.js) render in `ANKIWEB_LANG`. **← first.**
- **I2 — i18n the hand-written screens**: systematic `tr()` substitution + the label→key map.
- **I3 — Preferences form**: `/preferences` + toolbar entry (itself i18n'd via `tr()`).

Ship order: I1 → I2 → I3.

## Data flow
**Startup:** importing `ankiweb.i18n` runs a guarded `set_lang` (English default) so col-free
render paths never crash; then `ANKIWEB_LANG` → `Settings.lang` → `CollectionService.open()` runs
`set_lang(settings.lang or "en")` (overriding the default) before `Collection(path)` → `col.tr` +
`tr_legacyglobal` + frontend `i18n_resources` all localized. Every hand-written screen renders via
`tr` imported from `ankiweb.i18n`.
**Preferences:** `/preferences` GET reads `col.get_preferences()` → form; submit →
`col.set_preferences(merged)` → broadcast → back to the deck list.

## Error handling
- Unknown/empty `ANKIWEB_LANG` → fall back to Anki's default (English); never crash. (Guaranteed
  by `ankiweb/i18n.py`'s import-time guarded `set_lang` — see I1.)
- `set_preferences` with an out-of-range value → the backend raises; the `preferences` WS handler
  catches it and calls `hub.push_call("preferences", "ankiwebPrefsError", [msg])`, which writes the
  message into the in-page `<div id='err'>` region (the custom-study / filtered-deck pattern). **No
  HTTP 500** — submit is over the WS (`ws.py` swallows handler exceptions to `None`); the form
  stays in place with its values intact and no navigation fires. The write is atomic, so there is
  no partial save.
- Translation keys are **pre-verified at design time** (I2 label→key map) and asserted by tests;
  only verified keys are used. `anki._backend.Translations` has no `__getattr__`, so an unverified
  `tr.<key>()` raises `AttributeError` at first render — that is a build-time/test failure to fix,
  **not** a runtime fallback. (There is intentionally no runtime English-literal fallback; labels
  with no Anki key at all are hard-coded English literals in the screen, not `tr.` calls.)

## Testing
- **I1:** `ANKIWEB_LANG=zh-CN` → `col.tr.actions_add()` == "添加"; `i18n_resources` (served to
  the frontend) returns the zh-CN bundle; empty `ANKIWEB_LANG` → English. **Importing
  `ankiweb.i18n` and calling `tr.actions_add()` works WITHOUT opening a collection** (the
  self-init guard) — and `render_page()` called directly (no `Collection`) does not raise.
- **I2:** with `ANKIWEB_LANG=zh-CN`, `GET /deckbrowser` / `/overview` / toolbar contain the
  translated terms (e.g. 学习 / 浏览 / 统计 / 牌组); with default lang they're English.
- **I3:** `GET /preferences` renders the 4 sections' fields; a `savePrefs` round-trip flips a
  value (e.g. `scheduling.learn_ahead_secs`) and `get_preferences()` reflects it; an invalid
  value leaves the form in place and populates the `#err` region via `ankiwebPrefsError` (no
  navigation, no HTTP 500). (Playwright: the form renders + a save persists.)

## Risks
**`tr_legacyglobal` is `None`/uninitialized until `set_lang` runs at least once** — the
verification's CRITICAL finding (raises `TypeError: 'NoneType' object is not callable`; opening a
`Collection` does NOT initialize it). The naive fix — `set_lang` only in `CollectionService.open()`
— is **insufficient**: `render_page()` (and the per-request toolbar that calls `tr.`) runs on
col-free paths, including six existing direct-`render_page` tests, which would then crash. **The
real guarantee is `ankiweb/i18n.py`'s import-time guarded `set_lang`** (idempotent; `open()` still
overrides with `ANKIWEB_LANG`). All screens import `tr` from `ankiweb.i18n` so the guard always
runs first. Once initialized, the singleton's backend is mutated in place by later `set_lang`
calls, so the bound import is safe (no re-read needed) — the only real hazard is the *first* call,
not staleness.

`set_lang` must run before `Collection()` (open + any reopen inherits the process-global) — a
wrong order yields English `col.tr`. The label→key map is the bulk of I2 — 1732 keys exist and
the previously-unresolved labels are now all verified (see Key findings), but each must still be
checked against `col.tr` (wrong key name → wrong/empty string); keyless strings stay English
(documented, not silent). `set_preferences` writes each present section's scalars wholesale, so
the handler must merge submitted values onto a fresh `get_preferences()` and resend all 4
sections (never a partial) to avoid clobbering unexposed fields. The Preferences form is
server-rendered (Qt dialog has no web bundle) — same rebuild pattern as E4/E5. `new_review_mix`
is an enum (select, not checkbox). The reused frontend localizes for free via `i18n_resources`;
ankiweb's own pages are the only ones needing manual i18n (I2).
