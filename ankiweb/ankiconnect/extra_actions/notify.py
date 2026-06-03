"""Push-notifications config extra actions — read/modify the deck notifier over the API.

These edit the same in-memory NotifierState the web form (/notify) and the running notifier
task share, so changes take effect live (and a URL change re-syncs the receiver)."""
from __future__ import annotations
from ankiweb.ankiconnect.registry import extra_action
from ankiweb.notifier import NotifyConfig, header_safe
from ankiweb.ankiconnect.schemas.extra import GetNotifyConfigParams, SetNotifyConfigParams


def _view(state) -> dict:
    cfg, st = state.config, state.status
    return {
        "enabled": cfg.enabled, "url": cfg.url, "token": cfg.token,
        "poll_sec": cfg.poll_sec, "retry_sec": cfg.retry_sec, "scope": cfg.scope,
        "active": cfg.active(),
        "status": {
            "watching": st.watching, "learnable": st.learnable, "pending": st.pending,
            "lastAttempt": st.last_attempt_ts, "lastSuccess": st.last_success_ts,
            "lastError": st.last_error,
        },
    }


def _state(rt):
    state = getattr(rt, "notifier", None)
    if state is None:
        raise Exception("push notifier is not available")
    return state


@extra_action("getNotifyConfig", params=GetNotifyConfigParams,
              summary="Read the Push-notifications config + live status")
async def get_notify_config(rt):
    return _view(_state(rt))


@extra_action("setNotifyConfig", params=SetNotifyConfigParams,
              summary="Modify the Push-notifications config (only the fields you send)")
async def set_notify_config(rt, enabled=None, url=None, token=None,
                            poll_sec=None, retry_sec=None, scope=None, resync=None):
    state = _state(rt)
    if token is not None and not header_safe(token):
        raise Exception("token must be ASCII / latin-1 (it is sent in an HTTP header)")
    cur = state.config
    new = NotifyConfig(
        enabled=cur.enabled if enabled is None else bool(enabled),
        url=cur.url if url is None else str(url).strip(),
        token=cur.token if token is None else str(token).strip(),
        poll_sec=cur.poll_sec if poll_sec is None else float(poll_sec),
        retry_sec=cur.retry_sec if retry_sec is None else float(retry_sec),
        scope=cur.scope if scope is None else (scope if scope in ("leaf", "all") else "leaf"),
    )
    state.update(new)            # persists to notify.json + wakes the running notifier task
    if resync:
        state.request_resync()   # drop the baseline -> re-push every nonzero deck
    return _view(state)
