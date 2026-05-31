from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import run_emit, build_note


def _ui(rt):
    return rt.hub.ui_state


# ---------- reviewer state queries ----------
@action("guiReviewActive")
async def gui_review_active(rt):
    return _ui(rt).review_active


@action("guiCurrentCard")
async def gui_current_card(rt):
    ui = _ui(rt)
    if not ui.review_active:
        raise Exception("Gui review is not currently active.")
    cid = ui.current_card_id

    def build(col):
        # nextReviews: prefer the queued top card's states (reviewer-faithful source);
        # if the queue top has drifted from the mirror, fall back to get_scheduling_states.
        labels = []
        queued = col.sched.get_queued_cards(fetch_limit=1)
        if queued.cards and queued.cards[0].card.id == cid:
            labels = list(col.sched.describe_next_states(queued.cards[0].states))
        else:
            try:
                labels = list(col.sched.describe_next_states(
                    col._backend.get_scheduling_states(cid)))
            except Exception:
                labels = []
        card = col.get_card(cid)
        note = card.note()
        model = note.note_type()
        fields = {name: {"value": note.fields[o], "order": o}
                  for name, (o, _f) in col.models.field_map(model).items()}
        return {
            "cardId": cid,
            "fields": fields,
            "fieldOrder": card.ord,
            "question": card.question(),
            "answer": card.answer(),
            "buttons": [1, 2, 3, 4],          # v3 always has 4 answer buttons (shape-stable)
            "nextReviews": labels,
            "modelName": model["name"],
            "deckName": col.decks.name(card.did),
            "css": model.get("css", ""),
            "template": card.template()["name"],
        }
    return await rt.service.run(build)


# ---------- reviewer control (drive the real reviewer handler; keeps the browser in sync) ----------
@action("guiStartCardTimer")
async def gui_start_card_timer(rt):
    if not _ui(rt).review_active:
        return False
    await rt.hub.dispatch_cmd("reviewer", "starttimer")
    return True


@action("guiShowQuestion")
async def gui_show_question(rt):
    if not _ui(rt).review_active:
        return False
    await rt.hub.dispatch_cmd("reviewer", "show")
    return True


@action("guiShowAnswer")
async def gui_show_answer(rt):
    if not _ui(rt).review_active:
        return False
    await rt.hub.dispatch_cmd("reviewer", "ans")
    return True


@action("guiAnswerCard")
async def gui_answer_card(rt, ease=None):
    ui = _ui(rt)
    if not ui.review_active or ui.side != "answer":
        return False
    # v3 answerButtons() is hardcoded to 4 in anki 25.9.4; also reject bool/non-int ease.
    if not isinstance(ease, int) or isinstance(ease, bool) or not (1 <= ease <= 4):
        return False
    await rt.hub.dispatch_cmd("reviewer", f"ease{ease}")
    return True


# ---------- navigation (push to the active screen's context) ----------
async def _navigate(rt, url):
    target = _ui(rt).current_screen or "deckbrowser"
    await rt.hub.push_call(target, "ankiwebNavigate", [url])


@action("guiDeckBrowser")
async def gui_deck_browser(rt):
    await _navigate(rt, "/deckbrowser")
    return None


@action("guiDeckOverview")
async def gui_deck_overview(rt, name=None):
    did = await rt.service.run(lambda col: col.decks.id_for_name(name or ""))
    if did is None:
        return False
    await rt.service.run(lambda col: col.decks.set_current(did))
    await _navigate(rt, "/overview")
    return True


@action("guiDeckReview")
async def gui_deck_review(rt, name=None):
    did = await rt.service.run(lambda col: col.decks.id_for_name(name or ""))
    if did is None:
        return False
    await rt.service.run(lambda col: col.decks.set_current(did))
    await rt.service.run(lambda col: col.startTimebox())
    await _navigate(rt, "/reviewer")
    return True


# ---------- backend ops (work headless; broadcast so open screens refresh) ----------
@action("guiUndo")
async def gui_undo(rt):
    def do(col):
        from anki.errors import UndoEmpty
        if not col.undo_status().undo:
            return True, None          # nothing to undo → no-op (mw.undo is a no-op)
        try:
            return True, col.undo()
        except UndoEmpty:
            return True, None
    return await run_emit(rt, do)


@action("guiCheckDatabase")
async def gui_check_database(rt):
    await rt.service.run(lambda col: col.fix_integrity())
    return True


# ---------- degraded browser-domain actions (faithful to AnkiConnect's "no window" values) ----------
@action("guiBrowse")
async def gui_browse(rt, query=None, reorderCards=None):
    if reorderCards is not None:  # reference checks 1-3; columnId-resolves (4) needs the table (Plan D)
        if not isinstance(reorderCards, dict):
            raise Exception("reorderCards should be a dict")
        if "columnId" not in reorderCards or "order" not in reorderCards:
            raise Exception('Must provide a "columnId" and an "order" property')
        if reorderCards["order"] not in ("ascending", "descending"):
            raise Exception("invalid card order: " + str(reorderCards["order"]))
        # columnId validity is checked against the live Browser table → deferred to Plan D.
    # findCards(None) returns [] (ref); only a real query searches.
    cids = await rt.service.run(
        lambda col: [] if query is None else list(col.find_cards(query)))
    ui = _ui(rt)
    ui.browser_open = True          # guiBrowse opens the Browser regardless of the query
    ui.last_browse_query = query
    ui.matched_card_ids = cids
    return cids


@action("guiSelectCard")
async def gui_select_card(rt, card=None):
    ui = _ui(rt)
    if not ui.browser_open:   # no Browser window open → reference returns False
        return False

    def note_of(col):
        try:
            return col.get_card(card).nid
        except Exception:
            return None
    nid = await rt.service.run(note_of)
    ui.selected_card_ids = [card]
    ui.selected_note_ids = [nid] if nid is not None else []
    return True


@action("guiSelectNote")
async def gui_select_note(rt, note=None):
    # deprecated alias: AnkiConnect forwards to guiSelectCard (selects by CARD id)
    return await gui_select_card(rt, card=note)


@action("guiSelectedNotes")
async def gui_selected_notes(rt):
    return list(_ui(rt).selected_note_ids)


@action("guiPlayAudio")
async def gui_play_audio(rt):
    # [sound:] audio playback in the reviewer is deferred to Plan 4; preserve the contract:
    # True while review is active (best-effort side effect), False otherwise.
    return bool(_ui(rt).review_active)


# ---------- deferred to Plan D (editor/import) — faithful stubs now ----------
@action("guiAddNoteSetData")
async def gui_add_note_set_data(rt, note=None, append=False):
    # The Add Note editor dialog is Plan D; it is never open pre-D, so return exactly
    # AnkiConnect's "dialog not open" payload.
    return {"error": "Add Note dialog is not open", "code": 1}


@action("guiEditNote")
async def gui_edit_note(rt, note=None):
    # No editor dialog yet (Plan D); reference returns null. No-op.
    return None


@action("guiAddCards")
async def gui_add_cards(rt, note=None):
    # The interactive Add dialog is Plan D. Preserve the contract (returns an int note id)
    # without the surprising side effect of actually adding: validate deck/model/fields and
    # return the prospective (unsaved) note id — like the reference, which returns the
    # not-yet-saved ankiNote.id. The note is NOT added to the collection.
    if note is None:
        return 0  # blank dialog → fresh unsaved note (deferred to Plan D)

    def build(col):
        did = col.decks.id_for_name(note.get("deckName", ""))
        if did is None:
            raise Exception("deck was not found: " + str(note.get("deckName")))
        n, _ = build_note(col, note)  # raises on unknown model/fields (faithful validation)
        return n.id                   # unsaved note id (0 until added; dialog deferred to D)
    return await rt.service.run(build)


# ---------- server-incompatible (refuse / no-op) ----------
@action("guiImportFile")
async def gui_import_file(rt, path=None):
    raise Exception("guiImportFile is not supported in ankiweb (no GUI file picker)")


@action("guiExitAnki")
async def gui_exit_anki(rt):
    # Never shut down the shared local server on a client request (spec §4). No-op.
    return None
