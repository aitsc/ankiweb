from __future__ import annotations
from ankiweb.ankiconnect.registry import action, ACTIONS


@action("version")
async def version(rt):
    return 6


@action("apiReflect")
async def api_reflect(rt, scopes=None, actions=None):
    scopes = scopes or []
    out = {"scopes": [], "actions": []}
    if "actions" in scopes:
        out["scopes"] = ["actions"]
        names = sorted(ACTIONS.keys()) + ["multi"]
        if actions is not None:
            names = [n for n in names if n in actions]
        out["actions"] = names
    return out


@action("requestPermission")
async def request_permission(rt, allowed=False, origin=None):
    # CORS result is injected by the app. Single-user local → auto-grant when allowed.
    if not allowed:
        return {"permission": "denied"}
    return {"permission": "granted",
            "requireApikey": rt.config.api_key is not None,
            "version": 6}


@action("reloadCollection")
async def reload_collection(rt):
    # col.reset() is a deprecated no-op in anki 25.9.4; the single shared collection is
    # always live, so there's nothing to reload. Return None (AnkiConnect returns null).
    return None


@action("getProfiles")
async def get_profiles(rt):
    return ["User 1"]


@action("getActiveProfile")
async def get_active_profile(rt):
    return "User 1"


@action("loadProfile")
async def load_profile(rt, name=None):
    return True


@action("sync")
async def sync(rt):
    raise Exception("sync is not supported by ankiweb")
