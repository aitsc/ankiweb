"""AnkiConnect card actions."""
from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import card_to_info, run_emit


@action("findCards")
async def find_cards(rt, query=""):
    return await rt.service.run(lambda col: list(col.find_cards(query or "")))


@action("cardsInfo")
async def cards_info(rt, cards=None):
    cards = cards or []

    def fn(col):
        out = []
        for cid in cards:
            try:
                out.append(card_to_info(col, col.get_card(cid)))
            except Exception:
                out.append({})
        return out
    return await rt.service.run(fn)


@action("cardsModTime")
async def cards_mod_time(rt, cards=None):
    cards = cards or []

    def fn(col):
        out = []
        for cid in cards:
            try:
                out.append({"cardId": cid, "mod": col.get_card(cid).mod})
            except Exception:
                out.append({})
        return out
    return await rt.service.run(fn)


@action("suspend")
async def suspend(rt, cards=None, suspend=True):
    cards = cards or []

    def fn(col):
        op = col.sched.suspend_cards(cards) if suspend else col.sched.unsuspend_cards(cards)
        return True, op
    return await run_emit(rt, fn)


@action("unsuspend")
async def unsuspend(rt, cards=None):
    cards = cards or []

    def fn(col):
        return None, col.sched.unsuspend_cards(cards)
    await run_emit(rt, fn)
    return None


@action("suspended")
async def suspended(rt, card=None):
    return await rt.service.run(lambda col: col.get_card(card).queue == -1)


@action("areSuspended")
async def are_suspended(rt, cards=None):
    cards = cards or []

    def fn(col):
        out = []
        for cid in cards:
            try:
                out.append(col.get_card(cid).queue == -1)
            except Exception:
                out.append(None)
        return out
    return await rt.service.run(fn)


@action("areDue")
async def are_due(rt, cards=None):
    cards = cards or []
    return await rt.service.run(
        lambda col: [cid in set(col.find_cards("is:due")) or
                     cid in set(col.find_cards("is:new")) for cid in cards])


@action("getEaseFactors")
async def get_ease_factors(rt, cards=None):
    cards = cards or []

    def fn(col):
        out = []
        for cid in cards:
            try:
                out.append(col.get_card(cid).factor)
            except Exception:
                out.append(None)  # faithful: AnkiConnect appends None for missing cards
        return out
    return await rt.service.run(fn)


@action("setEaseFactors")
async def set_ease_factors(rt, cards=None, easeFactors=None):
    cards = cards or []
    easeFactors = easeFactors or []

    def fn(col):
        out = []
        last_op = None
        for cid, factor in zip(cards, easeFactors):
            c = col.get_card(cid)
            c.factor = int(factor)
            last_op = col.update_card(c)
            out.append(True)
        return out, last_op
    return await run_emit(rt, fn)


@action("setSpecificValueOfCard")
async def set_specific_value_of_card(rt, card=None, keys=None, newValues=None, warning_check=False):
    keys = keys or []
    newValues = newValues or []
    risky = {"id", "nid", "did", "ord", "mod", "usn", "type", "queue", "due", "odue",
             "odid", "flags", "data"}

    def fn(col):
        c = col.get_card(card)
        out = []
        for key, val in zip(keys, newValues):
            if key in risky and not warning_check:
                out.append([False, "Can't set this key without explicit warning_check"])
                continue
            try:
                setattr(c, key, val)
                out.append(True)
            except Exception as exc:
                out.append([False, str(exc)])
        op = col.update_card(c)
        return out, op
    return await run_emit(rt, fn)


@action("getIntervals")
async def get_intervals(rt, cards=None, complete=False):
    cards = cards or []
    if not complete:
        return await rt.service.run(lambda col: [col.get_card(cid).ivl for cid in cards])

    def fn(col):
        out = []
        for cid in cards:
            ivls = col.db.list("select ivl from revlog where cid = ? order by id", cid)
            out.append(ivls)
        return out
    return await rt.service.run(fn)


@action("forgetCards")
async def forget_cards(rt, cards=None):
    cards = cards or []

    def fn(col):
        return None, col.sched.schedule_cards_as_new(cards)
    await run_emit(rt, fn)
    return None


@action("relearnCards")
async def relearn_cards(rt, cards=None):
    cards = cards or []

    def fn(col):
        if not cards:  # avoid invalid "where id in ()"
            return None
        col.db.execute(
            "update cards set type=3, queue=1 where id in (%s)" %
            ",".join("?" * len(cards)), *cards)
        return None
    await rt.service.run(fn)
    return None


@action("answerCards")
async def answer_cards(rt, answers=None):
    from anki.scheduler.v3 import CardAnswer
    answers = answers or []
    rating_map = {1: CardAnswer.Rating.AGAIN, 2: CardAnswer.Rating.HARD,
                  3: CardAnswer.Rating.GOOD, 4: CardAnswer.Rating.EASY}

    def fn(col):
        out = []
        last_op = None
        for a in answers:
            cid, ease = a["cardId"], a["ease"]
            card = col.get_card(cid)
            card.start_timer()
            states = col._backend.get_scheduling_states(cid)
            answer = col.sched.build_answer(
                card=card, states=states, rating=rating_map[ease])
            last_op = col.sched.answer_card(answer)
            out.append(True)
        return out, last_op
    return await run_emit(rt, fn)


@action("setDueDate")
async def set_due_date(rt, cards=None, days="0"):
    cards = cards or []

    def fn(col):
        return True, col.sched.set_due_date(cards, str(days))
    return await run_emit(rt, fn)
