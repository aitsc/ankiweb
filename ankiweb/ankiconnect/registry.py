from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

# action name -> async handler(rt, **params). This is the hot dispatch path (dispatch.py);
# its shape is intentionally unchanged so POST / behavior cannot regress.
ACTIONS: dict[str, Callable[..., Awaitable]] = {}


@dataclass
class ActionSpec:
    """Documentation/typing metadata for an action, used to build the typed /actions/<name>
    REST routes and their OpenAPI schemas. Parallel to ACTIONS; never touched by dispatch."""
    name: str
    handler: Callable[..., Awaitable]
    params_model: type | None = None   # a pydantic BaseModel subclass, or None (loose)
    result_type: Any = None            # python type for the response `result` field, or None
    summary: str = ""
    description: str = ""


ACTION_SPECS: dict[str, ActionSpec] = {}


def action(name: str, *, params: type | None = None, returns: Any = None,
           summary: str = "", description: str = ""):
    def deco(fn):
        ACTIONS[name] = fn
        ACTION_SPECS[name] = ActionSpec(
            name=name, handler=fn, params_model=params, result_type=returns,
            summary=summary, description=(description or (fn.__doc__ or "")).strip())
        return fn
    return deco
