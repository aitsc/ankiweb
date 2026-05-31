from __future__ import annotations
from ankiweb.ankiconnect.registry import action


@action("version")
async def version(rt):
    return 6
