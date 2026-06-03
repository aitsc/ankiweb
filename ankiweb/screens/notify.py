"""Web form + status panel for the deck push notifier (Extras menu).

ankiweb-original feature — labels are intentionally English/keyless (like "Source"), not Anki
translation keys."""
from __future__ import annotations
import html
import time

from ankiweb.notifier import NotifyConfig


def config_from_form(enabled: bool, url: str, token: str,
                     poll_sec: float, retry_sec: float, scope: str = "leaf") -> NotifyConfig:
    return NotifyConfig(
        enabled=bool(enabled), url=(url or "").strip(), token=(token or "").strip(),
        poll_sec=float(poll_sec or 0), retry_sec=float(retry_sec or 0),
        scope=scope if scope in ("leaf", "all") else "leaf")


def _fmt_ts(ts) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "—"


def header_safe(token: str) -> bool:
    """A Bearer token must be encodable into an HTTP header (latin-1), or httpx raises on
    every send — a forever-failing config. Reject such tokens at save time."""
    try:
        ("Bearer " + (token or "")).encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


def _num(v) -> str:
    try:
        return f"{float(v):g}"
    except (ValueError, TypeError):
        return html.escape(str(v))


_SCHEMA_DOC = (
    "POST &lt;url&gt;\n"
    "Authorization: Bearer &lt;token&gt;        # omitted when token is empty\n"
    "Content-Type: application/json\n\n"
    "{ \"source\": \"ankiweb\", \"ts\": 1780500000,\n"
    "  \"changes\": [\n"
    "    { \"deck\": \"A::B\", \"deckId\": 17800, \"learnable\": true,\n"
    "      \"new_count\": 12, \"learn_count\": 3, \"review_count\": 40 } ] }\n\n"
    "Success = HTTP 200 AND a JSON body with `ok` exactly true; anything else is retried."
)


def render_notify_html(state, error: str = "", form=None) -> str:
    cfg: NotifyConfig = state.config
    st = state.status
    # On a rejected save, prefill from the submitted values (so input isn't lost); else config.
    src = form if form is not None else {
        "enabled": cfg.enabled, "url": cfg.url, "token": cfg.token,
        "poll_sec": cfg.poll_sec, "retry_sec": cfg.retry_sec, "scope": cfg.scope}
    checked = "checked" if src.get("enabled") else ""
    scope = src.get("scope", "leaf")
    leaf_sel = "selected" if scope != "all" else ""
    all_sel = "selected" if scope == "all" else ""
    active = "yes" if cfg.active() else "no"
    err = html.escape(st.last_error) if st.last_error else "—"
    banner = (f"<div style='background:#fdd;border:1px solid #c00;color:#900;"
              f"padding:8px;margin:8px 0'>{html.escape(error)}</div>") if error else ""
    return (
        "<div style='max-width:760px;margin:0 auto;padding:8px 16px;'>"
        "<h2>Push notifications</h2>"
        f"{banner}"
        "<p style='color:#666'>An ankiweb-original feature (not part of the Anki/AnkiConnect "
        "port). POSTs to your endpoint whenever a deck becomes learnable or stops being "
        "learnable. Configuration is live — saving applies without a restart.</p>"

        "<form method='post' action='/notify'>"
        "<table style='border-collapse:collapse'>"
        f"<tr><td style='padding:6px 10px 6px 0'>Enabled</td>"
        f"<td><input type='checkbox' name='enabled' {checked}></td></tr>"
        f"<tr><td style='padding:6px 10px 6px 0'>POST URL</td>"
        f"<td><input type='text' name='url' size='52' value='{html.escape(str(src.get('url', '')))}' "
        f"placeholder='https://example.com/anki-hook'></td></tr>"
        f"<tr><td style='padding:6px 10px 6px 0'>Token (Bearer)</td>"
        f"<td><input type='text' name='token' size='52' value='{html.escape(str(src.get('token', '')))}' "
        f"placeholder='(optional)'></td></tr>"
        f"<tr><td style='padding:6px 10px 6px 0'>Poll interval (sec)</td>"
        f"<td><input type='number' name='poll_sec' min='1' step='1' value='{_num(src.get('poll_sec', 60))}'></td></tr>"
        f"<tr><td style='padding:6px 10px 6px 0'>Retry interval (sec)</td>"
        f"<td><input type='number' name='retry_sec' min='1' step='1' value='{_num(src.get('retry_sec', 30))}'></td></tr>"
        f"<tr><td style='padding:6px 10px 6px 0'>Scope</td>"
        f"<td><select name='scope'>"
        f"<option value='leaf' {leaf_sel}>Leaf only (last-level decks)</option>"
        f"<option value='all' {all_sel}>All levels (parents count subdecks)</option>"
        f"</select></td></tr>"
        "</table>"
        "<p><button type='submit' name='action' value='save'>Save</button> "
        "<button type='submit' name='action' value='resync' "
        "title='Re-push every currently-learnable deck now'>Save &amp; re-push all</button></p>"
        "</form>"

        "<h3>Status</h3>"
        "<table style='border-collapse:collapse'>"
        f"<tr><td style='padding:4px 16px 4px 0'>Active</td><td>{active}</td></tr>"
        f"<tr><td style='padding:4px 16px 4px 0'>Decks watched</td><td>{st.watching}</td></tr>"
        f"<tr><td style='padding:4px 16px 4px 0'>Learnable now</td><td>{st.learnable}</td></tr>"
        f"<tr><td style='padding:4px 16px 4px 0'>Pending (unacked)</td><td>{st.pending}</td></tr>"
        f"<tr><td style='padding:4px 16px 4px 0'>Last attempt</td><td>{_fmt_ts(st.last_attempt_ts)}</td></tr>"
        f"<tr><td style='padding:4px 16px 4px 0'>Last success</td><td>{_fmt_ts(st.last_success_ts)}</td></tr>"
        f"<tr><td style='padding:4px 16px 4px 0'>Last error</td><td>{err}</td></tr>"
        "</table>"

        "<h3>Request format</h3>"
        f"<pre style='background:#f5f5f5;padding:10px;border:1px solid #ddd;overflow:auto'>{_SCHEMA_DOC}</pre>"
        "</div>"
    )
