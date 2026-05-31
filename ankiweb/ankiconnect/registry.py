from __future__ import annotations
from typing import Awaitable, Callable

# action name -> async handler(rt, **params)
ACTIONS: dict[str, Callable[..., Awaitable]] = {}


def action(name: str):
    def deco(fn):
        ACTIONS[name] = fn
        return fn
    return deco
