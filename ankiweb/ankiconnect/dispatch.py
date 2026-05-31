from __future__ import annotations
from typing import Any
from ankiweb.ankiconnect.registry import ACTIONS


def _envelope(version: int, result: Any) -> Any:
    # success: version<=4 → bare value; version>=5 → {result, error:None}
    if version <= 4:
        return result
    return {"result": result, "error": None}


async def dispatch_one(rt, req: dict) -> Any:
    """Dispatch a single AnkiConnect request object → its reply (enveloped per version)."""
    version = req.get("version", 4)
    try:
        action_name = req.get("action") or ""
        params = req.get("params") or {}
        # apiKey gate (requestPermission is always exempt)
        if rt.config.api_key is not None and action_name != "requestPermission":
            if req.get("key") != rt.config.api_key:
                raise Exception("valid api key must be provided")
        if action_name == "multi":
            result = [await dispatch_one(rt, sub) for sub in (params.get("actions") or [])]
        elif action_name in ACTIONS:
            result = await ACTIONS[action_name](rt, **params)
        else:
            raise Exception(f"unsupported action: {action_name}")
        return _envelope(version, result)
    except Exception as exc:  # errors are ALWAYS enveloped, regardless of version
        return {"result": None, "error": str(exc)}
