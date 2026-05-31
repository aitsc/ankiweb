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
