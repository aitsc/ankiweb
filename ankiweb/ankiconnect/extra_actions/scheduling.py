"""Scheduling extra actions."""
from __future__ import annotations
from ankiweb.ankiconnect.registry import extra_action
from ankiweb.ankiconnect.actions._helpers import run_emit
from ankiweb.ankiconnect.schemas.extra import ExtendCardLimitsParams


def _find_node(node, did):
    if node.deck_id == did:
        return node
    for child in node.children:
        found = _find_node(child, did)
        if found is not None:
            return found
    return None


@extra_action("extendCardLimits", params=ExtendCardLimitsParams,
              summary="Add to/subtract from today's new/review card limits for a deck")
async def extend_card_limits(rt, deck=None, deckId=None, new=0, review=0):
    """Temporarily change today's new and/or review card limits for a deck — the API form of
    Custom Study's 'Increase today's … card limit' (negative reduces). Returns the deck's
    resulting counts. ankiweb-original: reachable only at /extra_actions/extendCardLimits."""
    import anki.scheduler_pb2 as sp

    def fn(col):
        did = deckId if (deckId is not None and col.decks.get(deckId) is not None) else None
        if did is None and deck:
            d = col.decks.by_name(deck)
            did = d["id"] if d is not None else None
        if did is None:
            raise Exception("deck was not found: " + str(deck if deck else deckId))
        last_op = None
        if new:
            last_op = col.sched.custom_study(
                sp.CustomStudyRequest(deck_id=did, new_limit_delta=int(new)))
        if review:
            last_op = col.sched.custom_study(
                sp.CustomStudyRequest(deck_id=did, review_limit_delta=int(review)))
        node = _find_node(col.sched.deck_due_tree(), did)
        result = {
            "deck": col.decks.name(did), "deckId": did,
            "new_count": node.new_count if node else 0,
            "learn_count": node.learn_count if node else 0,
            "review_count": node.review_count if node else 0,
        }
        return result, last_op
    return await run_emit(rt, fn)
