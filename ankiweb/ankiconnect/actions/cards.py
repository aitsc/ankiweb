"""AnkiConnect card actions (filled in Task 4)."""
from __future__ import annotations
from ankiweb.ankiconnect.registry import action


@action("findCards")
async def find_cards(rt, query=""):
    return await rt.service.run(lambda col: list(col.find_cards(query or "")))
