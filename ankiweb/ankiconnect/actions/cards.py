"""AnkiConnect card actions."""
from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.actions._helpers import card_to_info


@action("findCards")
async def find_cards(rt, query=""):
    return await rt.service.run(lambda col: list(col.find_cards(query or "")))


@action("cardsInfo")
async def cards_info(rt, cards=None):
    cards = cards or []
    return await rt.service.run(
        lambda col: [card_to_info(col, col.get_card(cid)) for cid in cards])


@action("cardsModTime")
async def cards_mod_time(rt, cards=None):
    cards = cards or []
    return await rt.service.run(
        lambda col: [{"cardId": cid, "mod": col.get_card(cid).mod} for cid in cards])
