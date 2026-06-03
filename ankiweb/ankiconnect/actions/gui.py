from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import run_emit, build_note
from ankiweb.ankiconnect.schemas.gui import (
    GuiReviewActiveParams, GuiCurrentCardParams, GuiStartCardTimerParams, GuiShowQuestionParams,
    GuiShowAnswerParams, GuiAnswerCardParams, GuiDeckBrowserParams, GuiDeckOverviewParams,
    GuiDeckReviewParams, GuiUndoParams, GuiCheckDatabaseParams, GuiBrowseParams,
    GuiSelectCardParams, GuiSelectNoteParams, GuiSelectedNotesParams, GuiPlayAudioParams,
    GuiAddNoteSetDataParams, GuiEditNoteParams, GuiAddCardsParams, GuiImportFileParams,
    GuiExitAnkiParams,
)


def _ui(rt):
    return rt.hub.ui_state


# ---------- reviewer state queries ----------
@action("guiReviewActive", params=GuiReviewActiveParams, returns=bool,
        summary="Is the reviewer active")
async def gui_review_active(rt):
    return _ui(rt).review_active


@action("guiCurrentCard", params=GuiCurrentCardParams, summary="Info for the current reviewer card")
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
@action("guiStartCardTimer", params=GuiStartCardTimerParams, returns=bool,
        summary="Start the current card timer")
async def gui_start_card_timer(rt):
    if not _ui(rt).review_active:
        return False
    await rt.hub.dispatch_cmd("reviewer", "starttimer")
    return True


@action("guiShowQuestion", params=GuiShowQuestionParams, returns=bool,
        summary="Show the question side")
async def gui_show_question(rt):
    if not _ui(rt).review_active:
        return False
    await rt.hub.dispatch_cmd("reviewer", "show")
    return True


@action("guiShowAnswer", params=GuiShowAnswerParams, returns=bool, summary="Show the answer side")
async def gui_show_answer(rt):
    if not _ui(rt).review_active:
        return False
    await rt.hub.dispatch_cmd("reviewer", "ans")
    return True


@action("guiAnswerCard", params=GuiAnswerCardParams, returns=bool,
        summary="Answer the current card")
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


@action("guiDeckBrowser", params=GuiDeckBrowserParams, summary="Open the deck browser")
async def gui_deck_browser(rt):
    await _navigate(rt, "/deckbrowser")
    return None


@action("guiDeckOverview", params=GuiDeckOverviewParams, returns=bool,
        summary="Open a deck overview")
async def gui_deck_overview(rt, name=None):
    did = await rt.service.run(lambda col: col.decks.id_for_name(name or ""))
    if did is None:
        return False
    await rt.service.run(lambda col: col.decks.set_current(did))
    await _navigate(rt, "/overview")
    return True


@action("guiDeckReview", params=GuiDeckReviewParams, returns=bool, summary="Start reviewing a deck")
async def gui_deck_review(rt, name=None):
    did = await rt.service.run(lambda col: col.decks.id_for_name(name or ""))
    if did is None:
        return False
    await rt.service.run(lambda col: col.decks.set_current(did))
    await rt.service.run(lambda col: col.startTimebox())
    await _navigate(rt, "/reviewer")
    return True


# ---------- backend ops (work headless; broadcast so open screens refresh) ----------
@action("guiUndo", params=GuiUndoParams, summary="Undo the last operation")
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


@action("guiCheckDatabase", params=GuiCheckDatabaseParams, returns=bool,
        summary="Check the database integrity")
async def gui_check_database(rt):
    await rt.service.run(lambda col: col.fix_integrity())
    return True


# ---------- degraded browser-domain actions (faithful to AnkiConnect's "no window" values) ----------
@action("guiBrowse", params=GuiBrowseParams, returns=list[int],
        summary="Open the browser and search")
async def gui_browse(rt, query=None, reorderCards=None):
    if reorderCards is not None:  # reference checks 1-3; columnId-resolves (4) needs the table (Plan D)
        if not isinstance(reorderCards, dict):
            raise Exception("reorderCards should be a dict")
        if "columnId" not in reorderCards or "order" not in reorderCards:
            raise Exception('Must provide a "columnId" and an "order" property')
        if reorderCards["order"] not in ("ascending", "descending"):
            raise Exception("invalid card order: " + str(reorderCards["order"]))
        valid = await rt.service.run(lambda col: {c.key for c in col.all_browser_columns()})
        if reorderCards["columnId"] not in valid:
            raise Exception("invalid columnId: " + str(reorderCards["columnId"]))
    # findCards(None) returns [] (ref); only a real query searches.
    cids = await rt.service.run(
        lambda col: [] if query is None else list(col.find_cards(query)))
    ui = _ui(rt)
    ui.browser_open = True          # guiBrowse opens the Browser regardless of the query
    ui.last_browse_query = query
    ui.matched_card_ids = cids
    return cids


@action("guiSelectCard", params=GuiSelectCardParams, returns=bool,
        summary="Select a card in the browser")
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


@action("guiSelectNote", params=GuiSelectNoteParams, returns=bool,
        summary="Select a card in the browser (alias)")
async def gui_select_note(rt, note=None):
    # deprecated alias: AnkiConnect forwards to guiSelectCard (selects by CARD id)
    return await gui_select_card(rt, card=note)


@action("guiSelectedNotes", params=GuiSelectedNotesParams, returns=list[int],
        summary="Selected note ids in the browser")
async def gui_selected_notes(rt):
    return list(_ui(rt).selected_note_ids)


@action("guiPlayAudio", params=GuiPlayAudioParams, returns=bool,
        summary="Replay the current card audio")
async def gui_play_audio(rt):
    ui = _ui(rt)
    if not ui.review_active:
        return False
    # replay the current side's audio via the reviewer's own player (mirrors qt guiPlayAudio)
    await rt.hub.dispatch_cmd("reviewer", "replay")
    return True


@action("guiAddNoteSetData", params=GuiAddNoteSetDataParams,
        summary="Prefill the open Add Note dialog")
async def gui_add_note_set_data(rt, note=None, append=False):
    # Live-prefill the OPEN Add dialog (the /add page, connected at context=="add").
    # When it isn't open, return AnkiConnect's "dialog not open" payload.
    # (append is accepted for contract compatibility; this sets the fields.)
    if _ui(rt).current_screen != "add":
        return {"error": "Add Note dialog is not open", "code": 1}
    from ankiweb.screens.add import load_data_for_spec
    data = await rt.service.run(lambda col: load_data_for_spec(col, note or {}))
    if data is None:
        return {"error": "Add Note dialog is not open", "code": 1}
    await rt.hub.push_call("add", "ankiwebLoadNote", [data])
    return None


@action("guiEditNote", params=GuiEditNoteParams, summary="Open the edit dialog for a note")
async def gui_edit_note(rt, note=None):
    screen = _ui(rt).current_screen
    if screen:
        await rt.hub.push_call(screen, "ankiwebNavigate", ["/edit?nid=" + str(note)])
    return None


@action("guiAddCards", params=GuiAddCardsParams, returns=int,
        summary="Preset the Add Cards dialog")
async def gui_add_cards(rt, note=None):
    # The interactive Add dialog is Plan D. Preserve the contract (returns an int note id)
    # without the surprising side effect of actually adding: validate deck/model/fields and
    # return the prospective (unsaved) note id — like the reference, which returns the
    # not-yet-saved ankiNote.id. The note is NOT added to the collection.
    if note is None:
        return 0  # blank dialog → fresh unsaved note

    open_ = _ui(rt).current_screen == "add"
    from ankiweb.screens.add import load_data_for_spec

    def build(col):
        did = col.decks.id_for_name(note.get("deckName", ""))
        if did is None:
            raise Exception("deck was not found: " + str(note.get("deckName")))
        n, _ = build_note(col, note)  # raises on unknown model/fields (faithful validation)
        data = load_data_for_spec(col, note) if open_ else None
        return n.id, data             # unsaved note id; prefill payload if the dialog is open
    nid, data = await rt.service.run(build)
    if data is not None:              # live-prefill the open Add dialog
        await rt.hub.push_call("add", "ankiwebLoadNote", [data])
    return nid


# ---------- server-incompatible (refuse / no-op) ----------
@action("guiImportFile", params=GuiImportFileParams, summary="Invoke the import dialog")
async def gui_import_file(rt, path=None):
    raise Exception("guiImportFile is not supported in ankiweb (no GUI file picker)")


@action("guiExitAnki", params=GuiExitAnkiParams, summary="Schedule a graceful Anki shutdown")
async def gui_exit_anki(rt):
    # Never shut down the shared local server on a client request (spec §4). No-op.
    return None
