# ankiweb i18n — I2: Internationalize the hand-written screens

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace hard-coded English in ankiweb's hand-written server-rendered screens with `tr.<key>()` calls (`tr` from `ankiweb.i18n`, shipped in I1), so the whole hand-written UI follows `ANKIWEB_LANG`. The reused SvelteKit/reviewer/editor frontend already localizes (I1).

**Architecture:** Each screen imports `from ankiweb.i18n import tr` and substitutes verified Anki translation keys for user-visible literals. `page.py`'s module-level `_TOOLBAR_HTML` constant becomes a per-request builder so the toolbar reflects the active language. Strings with no suitable Anki key (ankiweb-specific: the /about AGPL prose, free-text prompts, some error messages) stay hard-coded English.

**Policy — faithful-to-Anki (decided in the spec, user-approved):** where an Anki key's English differs slightly from the current literal (e.g. `actions_forget_card` renders "Reset Card", `exporting_include_deck` renders "Include deck name"), **adopt the Anki key and accept the visible-English change** — this makes ankiweb a more faithful translation and is required for full localization. Update the few existing tests that assert the old literal. **Exception:** strings with NO Anki key stay English (listed per-screen as "keyless").

**Tech Stack:** Python 3.12, `anki==25.9.4` (`tr.<key>()` from `ankiweb.i18n`), pytest (`asyncio_mode=auto`). All keys below were live-verified (en + zh-CN). Run: `conda run -n ankiweb python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-06-02-ankiweb-preferences-i18n-design.md` (I2). **Recon source:** workflow `wyxs019ll` enumerated every user-visible string per screen with its verified key — the tables below are that result.

**Conventions for every task:**
- Add `from ankiweb.i18n import tr` to the screen module (col-bearing render fns MAY use `col.tr` instead — equivalent; prefer `tr` for consistency).
- Substitute ONLY user-visible text. NEVER change: element ids/classes/CSS, JS names, attribute names, route paths/hrefs, `pycmd(...)` payloads, `data-*` values.
- For inline `<script>` inside f-strings, keep `{{`/`}}` escaping intact.
- A non-existent key raises `AttributeError` at render (no fallback) — every key below is verified, but if a typo slips in, tests catch it immediately.

---

### Task 1: `page.py` — per-request toolbar builder + 4 labels

**Files:** Modify `ankiweb/screens/page.py`; Test: `tests/test_global_toolbar.py` (existing, must stay green).

**Why:** `_TOOLBAR_HTML` is built once at import (before any `set_lang`), so `tr.` inside it would freeze to import-time English. It must become a function called per `render_page`.

- [ ] **Step 1 — Convert the constant to a builder.** Replace the module-level `_TOOLBAR_HTML = "..."` constant with a function, and update `render_page`'s reference. Add `from ankiweb.i18n import tr` at the top. The builder returns the same byte structure with the 4 labels from keys:

```python
def _toolbar_html() -> str:
    return (
        "<div id='ankiweb-toolbar'>"
        f"<a href='/deckbrowser'>{tr.actions_decks()}</a>"
        f"<a href='/add'>{tr.actions_add()}</a>"
        f"<a href='/browse'>{tr.qt_misc_browse()}</a>"
        f"<a href='/graphs'>{tr.qt_misc_stats()}</a>"
        "<a href='/about' title='Source code (AGPL)'>Source</a>"
        "<button class='nm' title='Toggle night mode' onclick='ankiwebToggleNight()'>\U0001f319</button>"
        "</div>"
    )
```
(Match the EXACT current markup of `_TOOLBAR_HTML` — copy its attributes/order verbatim, only swapping the 4 label texts for `tr` calls. "Source", the `title=` tooltips, and the 🌙 emoji stay hard-coded (keyless).) Then in `render_page` change `bar_html = _TOOLBAR_HTML if toolbar else ""` to `bar_html = _toolbar_html() if toolbar else ""`.

- [ ] **Step 2 — Run toolbar + suite.** `conda run -n ankiweb python -m pytest tests/test_global_toolbar.py tests/test_license_about.py tests/test_night_mode.py tests/test_screens_page.py -q`. Expected: PASS (English byte-identical: Decks/Add/Browse/Stats unchanged; `>Source</a>` unchanged). Then full suite green.

- [ ] **Step 3 — Commit.** `git add ankiweb/screens/page.py && git commit -m "i18n(I2): per-request toolbar builder with tr labels"`

**Toolbar key map (verified):** Decks=`actions_decks`, Add=`actions_add`, Browse=`qt_misc_browse`, Stats=`qt_misc_stats`. Keyless: "Source", `title=` tooltips, 🌙.

---

### Task 2: `deckbrowser.py`

**Files:** Modify `ankiweb/screens/deckbrowser.py`. Tests: none assert these labels except Export (see below) — full suite must stay green.

**Substitutions (verified key → English):**
| literal | tr expression | note |
|---|---|---|
| Decks (col header) | `tr.actions_decks()` | "Decks" |
| New (col header) | `tr.actions_new()` | "New" (no `decks_new_header` key exists) |
| Learn | `tr.decks_learn_header()` | "Learn" |
| Due | `tr.decks_review_header()` | "Due" |
| Create Deck | `tr.decks_create_deck()` | "Create Deck" |
| Create Filtered Deck | `tr.qt_misc_create_filtered_deck()` | **TEXT CHANGES** → "Create Filtered Deck..." (adds ellipsis; matches Anki desktop) |
| Import | `tr.actions_import()` | "Import" |
| Export | `tr.actions_export()` | "Export" — `test_export_integration.py:51` asserts on the /export page, not here; unchanged English |
| Image Occlusion | `tr.notetypes_image_occlusion_name()` | "Image Occlusion" |

Leave `col.studied_today()` (already backend-localized) and the `−`/`&nbsp;` formatting glyphs untouched.

- [ ] Add `from ankiweb.i18n import tr`; substitute each row. Run `pytest tests/test_deckbrowser.py -q` + full suite. Commit `i18n(I2): deckbrowser`.

---

### Task 3: `overview.py`

**Substitutions:**
| literal | tr expression | note |
|---|---|---|
| New | `tr.statistics_counts_new_cards()` | "New" |
| Learning | `tr.statistics_counts_learning_cards()` | "Learning" |
| To Review | `tr.studying_to_review()` | "To Review" |
| Study Now | `tr.studying_study_now()` | `test_study_loop_home.py:54`, `test_overview.py:21` assert "Study Now" — unchanged |
| Options | `tr.actions_options()` | "Options" |
| Rebuild | `tr.actions_rebuild()` | `test_filtered_deck.py:63` — unchanged |
| Empty | `tr.studying_empty()` | "Empty" |
| Custom Study | `tr.actions_custom_study()` | `test_custom_study_integration.py:51` — unchanged |
| Unbury | `tr.studying_unbury()` | "Unbury" |
| Edit Description | `tr.studying_edit() + " " + tr.fields_description()` | **composite** → "Edit Description"; `test_overview_description.py:30` asserts it — stays "Edit Description" in English |
| Decks | `tr.actions_decks()` | "Decks" |
| Save | `tr.actions_save()` | "Save" |
| Cancel | `tr.actions_cancel()` | "Cancel" |
| Render as markdown | keyless | no key — keep hard-coded English |

- [ ] Substitute; `pytest tests/test_overview.py tests/test_overview_description.py tests/test_study_loop_home.py -q` + full suite. Commit `i18n(I2): overview`.

---

### Task 4: `reviewer.py` + `type_answer.py`

**reviewer.py substitutions:**
| literal | tr expression | note |
|---|---|---|
| Show Answer | `tr.studying_show_answer()` | `test_reviewer.py:58`, `test_screen_routes.py:103`, `test_reviewer_integration.py:46` — unchanged |
| Again | `tr.studying_again()` | `test_reviewer.py:65` |
| Hard | `tr.studying_hard()` | |
| Good | `tr.studying_good()` | |
| Easy | `tr.studying_easy()` | |

Do NOT touch `col.sched.describe_next_states(...)` interval labels (backend-localized; `test_reviewer.py:42/64/69` assert on them — leave as-is).

**type_answer.py:**
| literal | tr expression | note |
|---|---|---|
| `Type-answer field not found: {field}` | `tr.studying_type_answer_unknown_field(val=field)` | **TEXT CHANGES** → "Type answer: unknown field ⁨{field}⁩" (Anki's wording, with FSI/PDI isolate chars). The key already includes the field via `val=`, so DROP the manual `html.escape(field)` concat — pass the field as `val=`. Check no test asserts the old prefix (none found). |

- [ ] Substitute; `pytest tests/test_reviewer.py tests/test_screen_routes.py -q` + full suite. Commit `i18n(I2): reviewer + type-answer`.

---

### Task 5: `browser.py`

**Substitutions:**
| literal | tr expression | note |
|---|---|---|
| Suspend | `tr.studying_suspend()` | `test_browser_integration.py:75` asserts "Suspend" — unchanged |
| Forget | `tr.actions_forget_card()` | **TEXT CHANGES** → "Reset Card" (Anki renamed). No test asserts "Forget". |
| Change Deck | `tr.browsing_change_deck()` | "Change Deck" |
| Remove Tag | `tr.actions_remove_tag()` | "Remove Tag" |
| Delete | `tr.actions_delete()` | "Delete" |
| Sort Field | `tr.browsing_sort_field()` | "Sort Field" (col header) |
| Deck (col header) | `tr.decks_deck()` | "Deck" |
| Due (col header) | `tr.statistics_due_date()` | "Due" |
| Decks (sidebar) | `tr.actions_decks()` | "Decks" |
| Tags (sidebar) | `tr.editing_tags()` | "Tags" |
| `Deck:` (detail label) | `tr.decks_deck() + ":"` | **composite** |
| `Tags:` (detail label) | `tr.editing_tags() + ":"` | **composite** |

**Keyless (no key — keep hard-coded English):** `Search…` placeholder, `Unsuspend`, `Set Due`, `Add Tag`, `Delete selected notes?`, `Due in days (e.g. 0, 3, 1-7):`, `Move to deck:`, `Add tag:`, `Remove tag:`, `invalid search`, `cards` (count suffix).

- [ ] Substitute; `pytest tests/test_browser.py tests/test_browser_integration.py -q` + full suite. Commit `i18n(I2): browser`.

---

### Task 6: `add.py`

**Substitutions:**
| literal | tr expression | note |
|---|---|---|
| Deck | `tr.decks_deck()` | "Deck" |
| Type | `tr.notetypes_type()` | "Type" |
| Add Note | `tr.actions_add_note()` | `test_gui_actions.py:157`, `test_gui_add_prefill.py:38` assert "Add Note" — unchanged |
| Close | `tr.actions_close()` | "Close" |
| Added | `tr.adding_added()` | `test_add_integration.py:46` asserts "Added" — unchanged |

**Keyless:** the empty-note and duplicate toast messages (`cannot create note because it is empty` / `... a duplicate`) — these come from `check_addable`'s English; keep as-is (`test_add.py:65` asserts the empty message). NOTE: these strings originate in the AnkiConnect `_helpers.check_addable`, not in add.py — out of scope for I2; leave.

- [ ] Substitute; `pytest tests/test_add.py tests/test_add_integration.py -q` + full suite. Commit `i18n(I2): add`.

---

### Task 7: `custom_study.py`

**Substitutions (option/label text — all verified):**
| literal | tr expression | note |
|---|---|---|
| Custom Study (heading) | `tr.actions_custom_study()` | `test_custom_study_integration.py:51` |
| Increase today's new card limit | `tr.custom_study_increase_todays_new_card_limit()` | `test_custom_study.py:32` |
| Increase today's review card limit | `tr.custom_study_increase_todays_review_card_limit()` | |
| Review forgotten cards | `tr.custom_study_review_forgotten_cards()` | |
| Review ahead | `tr.custom_study_review_ahead()` | |
| Preview new cards | `tr.custom_study_preview_new_cards()` | |
| Study by card state or tag | `tr.custom_study_study_by_card_state_or_tag()` | `test_custom_study.py:33` |
| Increase today's new card limit by | `tr.custom_study_increase_todays_new_card_limit_by()` | |
| Increase today's review card limit by | `tr.custom_study_increase_todays_review_limit_by()` | **TEXT CHANGES** → "Increase today's review limit by" (drops "card") |
| Review cards forgotten in the last | `tr.custom_study_review_cards_forgotten_in_last()` | **TEXT CHANGES** → "Review cards forgotten in last" (drops "the") |
| Review ahead by | `tr.custom_study_review_ahead_by()` | |
| Preview new cards added in the last | `tr.custom_study_preview_new_cards_added_in_the()` | |
| Select | `tr.custom_study_select()` | |
| cards | `tr.custom_study_cards()` | |
| days | `tr.scheduling_days()` | |
| cards from the deck | `tr.custom_study_cards_from_the_deck()` | |
| Card state: | `tr.browsing_sidebar_card_state()` | **TEXT CHANGES** → "Card State" (case; drop literal colon) |
| New cards only | `tr.custom_study_new_cards_only()` | |
| Due cards only | `tr.custom_study_due_cards_only()` | |
| All review cards in random order | `tr.custom_study_all_review_cards_in_random_order()` | |
| All cards in random order (don't reschedule) | `tr.custom_study_all_cards_in_random_order_dont()` | verify exact en |
| Require one or more of these tags: | `tr.custom_study_require_one_or_more_of_these()` | |
| Exclude tags: | `tr.custom_study_select_tags_to_exclude()` | **TEXT CHANGES** → "Select tags to exclude:" |
| OK | `tr.custom_study_ok()` | |
| Cancel | `tr.actions_cancel()` | |

**Keyless:** `New available:` / `Review available:` (count prefixes — no key), the `Could not create a custom study session...` error (`test_custom_study.py:80` — backend error string, keep). Tag `<option>` names = user data (untouched).

**Important:** these labels are emitted from BOTH the server-rendered HTML and the inline `CFG` JS map. The `CFG` map values are JS string literals inside the f-string `<script>` — substitute `tr.` there too (Python f-string interpolates before the JS sees it), keeping `{{`/`}}` escaping.

- [ ] Substitute; `pytest tests/test_custom_study.py tests/test_custom_study_integration.py -q` + full suite. Commit `i18n(I2): custom-study`.

---

### Task 8: `filtered_deck.py`

**Substitutions:**
| literal | tr expression | note |
|---|---|---|
| Create Filtered Deck (heading, new) | `tr.studying_edit()`-style? NO → keep composite: `"Create Filtered Deck"` heading uses no clean key. Use `tr.qt_misc_create_filtered_deck()` MINUS ellipsis is impossible → **keyless** keep "Create Filtered Deck" | `test_filtered_deck_integration.py:51` asserts "Filtered Deck" substring — keep |
| Edit Filtered Deck (heading, edit) | `tr.studying_edit() + " Filtered Deck"` | **composite** (studying_edit="Edit" + keyless "Filtered Deck"); `test_filtered_deck.py:62` asserts "Filt" — keep |
| Name | `tr.deck_config_name_prompt()` | verify en (likely "Name") |
| Filter | `tr.actions_filter()` | `test_filtered_deck.py:62` asserts "Filter" |
| Search | `tr.actions_search()` | "Search" |
| Limit | `tr.decks_limit_to()` | **TEXT CHANGES** → "Limit to" |
| Order | `tr.scheduling_order()` | "Order" |
| Enable second filter | `tr.decks_enable_second_filter()` | |
| Second filter | `tr.decks_filter_2()` | **TEXT CHANGES** → "Filter 2" |
| Reschedule cards based on my answers | `tr.decks_reschedule_cards_based_on_my_answers()` | **TEXT CHANGES** → adds "in this deck" |
| Again / Hard / Good (preview delays) | `tr.studying_again()` / `tr.studying_hard()` / `tr.studying_good()` | |
| Create even if empty | `tr.decks_create_even_if_empty()` | **TEXT CHANGES** → "Create/update this deck even if empty" |
| Build | `tr.decks_build()` | `test_filtered_deck.py:54` asserts ">Build<" — `decks_build`="Build", unchanged |
| Rebuild | `tr.actions_rebuild()` | `test_filtered_deck.py:63` asserts ">Rebuild<" — unchanged |
| Cancel | `tr.actions_cancel()` | |

**Keyless / backend:** `Preview delays (seconds)` legend (no key), the order `<option>` labels (`col.sched.filtered_deck_order_labels()` — backend-localized, `test_filtered_deck.py:53` asserts "Random"/"Order due", keep), the `Could not build the filtered deck.` error (`test_filtered_deck.py:115`, keep).

NOTE for the headings: keep "Create Filtered Deck" hard-coded English (keyless) to preserve the `test_filtered_deck_integration.py:51` substring; render "Edit Filtered Deck" as `tr.studying_edit() + " Filtered Deck"`.

- [ ] Substitute; `pytest tests/test_filtered_deck.py tests/test_filtered_deck_integration.py -q` + full suite. Commit `i18n(I2): filtered-deck`.

---

### Task 9: `export.py`

**Substitutions:**
| literal | tr expression | note |
|---|---|---|
| Export (heading + buttons) | `tr.actions_export()` | "Export" |
| Whole Collection | `tr.browsing_whole_collection()` | `test_export.py:32` asserts "Whole Collection" — unchanged |
| Anki Deck Package (.apkg) | `f"{tr.exporting_anki_deck_package()} (.apkg)"` | **composite** (key omits the suffix) |
| Anki Collection Package (.colpkg) | `f"{tr.exporting_anki_collection_package()} (.colpkg)"` | composite |
| Notes in Plain Text (.csv) | `f"{tr.exporting_notes_in_plain_text()} (.csv)"` | composite |
| Cards in Plain Text (.csv) | `f"{tr.exporting_cards_in_plain_text()} (.csv)"` | composite |
| Include scheduling information | `tr.exporting_include_scheduling_information()` | |
| Include media | `tr.exporting_include_media()` | |
| Include deck presets | `tr.exporting_include_deck_configs()` | verify en |
| Support older Anki versions | `tr.exporting_support_older_anki_versions()` | **TEXT CHANGES** → "Support older Anki versions (slower/larger files)" |
| Include HTML and media references | `tr.exporting_include_html_and_media_references()` | |
| Include tags | `tr.exporting_include_tags()` | |
| Include deck | `tr.exporting_include_deck()` | **TEXT CHANGES** → "Include deck name" |
| Include notetype | `tr.exporting_include_notetype()` | **TEXT CHANGES** → "Include note type name" |
| Include unique identifier | `tr.exporting_include_guid()` | verify en |
| Cancel | `tr.actions_cancel()` | |

**Keyless:** `Export:` target label, `Format`, `Package options`, `CSV options` legends (no keys).

- [ ] Substitute; `pytest tests/test_export.py tests/test_export_integration.py -q` + full suite. Commit `i18n(I2): export`.

---

### Task 10: `congrats.py`

- [ ] Replace the two literals `<h1>Congratulations!</h1>` + `<p>You have finished this deck for now.</p>` with ONE element rendering the combined key: `f"<h1>{tr.scheduling_congratulations_finished()}</h1>"` (en = "Congratulations! You have finished this deck for now."; the "Congratulations" substring stays present for `test_overview.py:30/33/35` + `test_reviewer_integration.py:59`). Replace `Unbury` → `tr.studying_unbury()`.

**Keyless (documented exceptions — keep English):** `The next learning card will be ready in {mins} minute(s).` (the only key `scheduling_next_learn_due(amount, unit)` needs bidi-isolate chars + a localized unit word — disproportionate for this simplified secondary line; documented exception), `buried cards.` (count suffix), `Back to Decks` (no clean key).

- [ ] Substitute; `pytest tests/test_overview.py -q` + full suite. Commit `i18n(I2): congrats`.

---

### Task 11: `about.py` + `editor.py` — NO-OP (documented)

`about.py` is entirely ankiweb-specific AGPL §13 legal prose with no Anki keys — it stays English by design (the spec's "keyless ankiweb-specific strings stay English"). `editor.py` renders no server-side user-visible text (it mounts the reused `editor.js`). **No changes.** (This task exists so the plan's screen coverage is explicit.)

---

### Task 12: zh-CN render tests + final regression

**Files:** Create `tests/test_i18n_screens.py`.

- [ ] **Step 1 — parametrized default-English vs zh-CN test.** For the key screens, assert default renders English and `set_lang("zh-CN")` renders the CJK string. Use the existing screen fixtures/clients. Example:

```python
import anki.lang
import pytest
from pathlib import Path
from ankiweb.config import Settings
from ankiweb.screens.page import render_page


def test_toolbar_default_english():
    html = render_page("deckbrowser", "<div>x</div>")
    assert ">Decks</a>" in html and ">Browse</a>" in html


def test_toolbar_zh():
    anki.lang.set_lang("zh-CN")
    html = render_page("deckbrowser", "<div>x</div>")
    assert "牌组" in html and "浏览" in html and "统计" in html
    # 'Source' stays English (keyless)
    assert ">Source</a>" in html
```

Add a couple more for a col-bearing screen (e.g. render the overview/custom-study HTML with a temp collection after `set_lang("zh-CN")`, assert a known CJK label like 学习 / 自定义学习 appears; with default lang assert the English). Use the `temp_collection` fixture pattern; call the screen's `render_*_html(col)` directly. The autouse `_default_english_lang` fixture (I1) resets to English before each test, so the zh tests set their own language in-body.

- [ ] **Step 2 — full suite.** `conda run -n ankiweb python -m pytest -q`. Expected: all green (the per-screen tasks already updated any asserting tests). Fix any stragglers.

- [ ] **Step 3 — Commit.** `git add tests/test_i18n_screens.py && git commit -m "test(i18n): zh-CN screen-render tests"`

---

## Self-Review
- **Coverage:** every hand-written screen from the spec's I2 list (deckbrowser, overview, reviewer, browser, add, custom_study, filtered_deck, export, about, page toolbar) + congrats + type_answer + editor is a task. about/editor are explicit no-ops.
- **Text-change inventory (visible English changes, all spec-sanctioned faithful-translation):** Create Filtered Deck→"...", Forget→"Reset Card", type-answer-unknown-field wording, custom-study "review limit by"/"forgotten in last"/"Card State"/"Select tags to exclude:", filtered-deck "Limit to"/"Filter 2"/reschedule "in this deck"/"Create/update this deck even if empty", export "Support older Anki versions (slower/larger files)"/"Include deck name"/"Include note type name". No existing test asserts any of these specific old literals (verified in recon test_refs) EXCEPT where noted as "unchanged" — so no test rewrites are forced; the new zh-CN test (Task 12) covers the translation behavior.
- **Keyless list (stay English, documented):** Source + about prose, prompts (Set Due/Move to deck:/Add tag:/Remove tag:/Search…/Delete selected notes?/Due in days…), Unsuspend, Add Tag, count suffixes (New available:/Review available:/cards/buried cards./Back to Decks), congrats next-learn line, format suffixes ((.apkg) etc.), Render as markdown, Preview delays (seconds), Export:/Format/Package options/CSV options legends, error messages without keys.
- **Verify-en caveats:** a few keys are tagged "verify en" (deck_config_name_prompt, exporting_include_deck_configs, exporting_include_guid, custom_study_all_cards_in_random_order_dont) — confirm the exact English at implementation time with `conda run -n ankiweb python -c "import anki.lang as L; L.set_lang('en'); print(L.tr_legacyglobal.<key>())"`; adjust if a closer key exists.
