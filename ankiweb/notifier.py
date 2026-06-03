"""Deck push notifier — an ankiweb-original feature (not part of the Anki/AnkiConnect port).

Watches deck *learnability* (does a deck have cards to study right now) via the efficient
`deck_due_tree()` and POSTs a notification whenever a deck flips learnable<->not. Configured
live from the web UI (Extras menu), persisted to a `notify.json` sidecar. See
docs/superpowers/specs/2026-06-04-deck-push-notifier-design.md.
"""
from __future__ import annotations
import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional


# ---------------------------------------------------------------------------- config + status
@dataclass
class NotifyConfig:
    enabled: bool = False
    url: str = ""
    token: str = ""           # bearer token; omitted from the request when empty
    poll_sec: float = 60.0    # deck_due_tree() refresh cadence
    retry_sec: float = 30.0   # resend cadence after a failed POST

    def active(self) -> bool:
        """The notifier acts only when fully configured."""
        return bool(self.enabled and self.url and self.poll_sec > 0 and self.retry_sec > 0)

    @classmethod
    def load(cls, path: Path) -> "NotifyConfig":
        # A missing OR corrupt notify.json must degrade to defaults, never crash startup —
        # the whole parse (not just json.loads) is guarded, since float()/.get() on bad data
        # (non-numeric interval, non-dict top level) would otherwise raise.
        try:
            data = json.loads(Path(path).read_text())
            if not isinstance(data, dict):
                return cls()
            return cls(
                enabled=bool(data.get("enabled", False)),
                url=str(data.get("url", "") or ""),
                token=str(data.get("token", "") or ""),
                poll_sec=float(data.get("poll_sec", 60.0) or 0),
                retry_sec=float(data.get("retry_sec", 30.0) or 0),
            )
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps({
            "enabled": self.enabled, "url": self.url, "token": self.token,
            "poll_sec": self.poll_sec, "retry_sec": self.retry_sec,
        }, indent=2))


@dataclass
class NotifyStatus:
    last_attempt_ts: Optional[float] = None
    last_success_ts: Optional[float] = None
    last_error: str = ""
    watching: int = 0     # decks currently tracked
    learnable: int = 0    # of those, how many are learnable now
    pending: int = 0      # decks whose change is not yet acknowledged


class NotifierState:
    """Shared between the web form (edits config, reads status) and the background runner
    (reads config, writes status). Single process / single event loop, so no locking."""

    def __init__(self, config_path: Path, config: Optional[NotifyConfig] = None):
        self.config_path = Path(config_path)
        self.config = config if config is not None else NotifyConfig.load(self.config_path)
        self.status = NotifyStatus()
        self.changed = asyncio.Event()  # set by update() to wake the runner immediately
        self.resync_pending = False     # set by request_resync() -> runner drops its baseline

    def update(self, config: NotifyConfig) -> None:
        self.config = config
        config.save(self.config_path)
        self.changed.set()

    def request_resync(self) -> None:
        """Ask the runner to re-push every currently-learnable deck (drop its baseline)."""
        self.resync_pending = True
        self.changed.set()


# ---------------------------------------------------------------------------- pure logic
def learnable(counts: dict) -> bool:
    return (counts.get("new_count", 0) + counts.get("learn_count", 0)
            + counts.get("review_count", 0)) > 0


def snapshot(col) -> dict:
    """{full_deck_name: {deck_id, new_count, learn_count, review_count}} from deck_due_tree().
    One backend call for the whole tree — scales to thousands of decks. The synthetic root
    (deck_id 0) is skipped; full names disambiguate same-named subdecks."""
    out: dict[str, dict] = {}

    def walk(node):
        did = node.deck_id
        if did:
            out[col.decks.name(did)] = {
                "deck_id": did, "new_count": node.new_count,
                "learn_count": node.learn_count, "review_count": node.review_count,
            }
        for child in node.children:
            walk(child)

    walk(col.sched.deck_due_tree())
    return out


def diff_changes(current: dict, last_notified: dict) -> list:
    """Decks whose learnable bool differs from what the receiver last acknowledged.
    `last_notified` maps full name -> bool; an absent deck is treated as not-learnable, so an
    empty baseline makes every currently-learnable deck a change (the startup push)."""
    changes = []
    for name, counts in current.items():
        now = learnable(counts)
        if now != last_notified.get(name, False):
            changes.append({
                "deck": name, "deckId": counts["deck_id"], "learnable": now,
                "new_count": counts["new_count"], "learn_count": counts["learn_count"],
                "review_count": counts["review_count"],
            })
    return changes


def build_payload(changes: list, ts: float) -> dict:
    return {"source": "ankiweb", "ts": int(ts), "changes": changes}


def eval_response(status_code: int, body: Any) -> tuple:
    """Success == HTTP 200 AND a JSON body with `ok` exactly true. Returns (ok, error)."""
    if status_code != 200:
        return False, f"HTTP {status_code}"
    if not isinstance(body, dict) or body.get("ok") is not True:
        return False, 'response was not {"ok": true}'
    return True, ""


# ---------------------------------------------------------------------------- async runner
class DeckNotifier:
    def __init__(self, state: NotifierState,
                 fetch: Callable[[], Awaitable[dict]],
                 post: Optional[Callable[[NotifyConfig, dict], Awaitable[tuple]]] = None,
                 now: Callable[[], float] = time.time):
        self.state = state
        self._fetch = fetch                    # async () -> snapshot dict
        self._post = post or self._http_post   # async (cfg, payload) -> (ok, error)
        self._now = now
        self.last_notified: dict[str, bool] = {}
        self._last_url: Optional[str] = None

    async def run(self) -> None:
        try:
            while True:
                cfg = self.state.config
                if not cfg.active():
                    self.last_notified = {}
                    self._last_url = None
                    st = self.state.status
                    st.watching = st.learnable = st.pending = 0  # don't show stale counts
                    await self._wait(None)  # idle until the config changes
                    continue
                if cfg.url != self._last_url or self.state.resync_pending:
                    self.last_notified = {}   # (re)pointed or manual resync -> push all again
                    self._last_url = cfg.url
                    self.state.resync_pending = False
                try:
                    delay = await self._tick(cfg)
                except Exception as exc:  # a fetch/backend error must NOT kill the task
                    self.state.status.last_error = str(exc)
                    delay = cfg.retry_sec
                await self._wait(delay)
        except asyncio.CancelledError:
            pass

    async def _tick(self, cfg: NotifyConfig) -> float:
        """One observe-diff-send cycle. Returns how long to wait before the next cycle."""
        current = await self._fetch()
        st = self.state.status
        st.watching = len(current)
        st.learnable = sum(1 for c in current.values() if learnable(c))
        for gone in set(self.last_notified) - set(current):
            del self.last_notified[gone]  # deleted/renamed decks drop silently
        changes = diff_changes(current, self.last_notified)
        st.pending = len(changes)
        if not changes:
            return cfg.poll_sec
        if self.state.config is not cfg:
            # config was edited (url/token/disable/intervals) during the fetch await — don't
            # POST to a stale target; run()'s next iteration re-reads config and re-baselines.
            return cfg.poll_sec
        st.last_attempt_ts = self._now()
        ok, err = await self._safe_post(cfg, build_payload(changes, self._now()))
        if ok:
            for ch in changes:
                self.last_notified[ch["deck"]] = ch["learnable"]
            st.last_success_ts = self._now()
            st.last_error = ""
            st.pending = 0
            return cfg.poll_sec
        # failure: leave last_notified untouched so the next cycle re-sends the LATEST state
        st.last_error = err
        return cfg.retry_sec

    async def _safe_post(self, cfg: NotifyConfig, payload: dict) -> tuple:
        try:
            return await self._post(cfg, payload)
        except Exception as exc:  # connection error, timeout, etc. -> retry
            return False, str(exc)

    async def _wait(self, timeout: Optional[float]) -> None:
        try:
            await asyncio.wait_for(self.state.changed.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        self.state.changed.clear()

    async def _http_post(self, cfg: NotifyConfig, payload: dict) -> tuple:
        import httpx
        headers = {"Authorization": "Bearer " + cfg.token} if cfg.token else {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(cfg.url, json=payload, headers=headers)
        try:
            body = r.json()
        except Exception:
            body = None
        return eval_response(r.status_code, body)
