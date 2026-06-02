"""Optional password gate for the web UI.

If `ANKIWEB_PASSWORD` (Settings.password) is empty, the app is fully open (default).
If set, every web request needs a valid session cookie; the cookie value is a hash of
the password (not the password itself). Single-user, local-first — a light gate, not a
hardened auth system. The AnkiConnect server (:8765) keeps its own `apiKey`, separate.
"""
from __future__ import annotations
import hashlib
import hmac

COOKIE = "ankiweb_auth"
# Paths reachable without a session cookie even when a password is set.
OPEN_PATHS = frozenset({"/login", "/logout", "/healthz"})


def auth_token(password: str) -> str:
    """The cookie value set on successful login: a salted hash of the password (stable
    across restarts so sessions survive a restart; never the plaintext password)."""
    return hashlib.sha256(b"ankiweb-auth-v1:" + password.encode("utf-8")).hexdigest()


def password_ok(submitted: str, password: str) -> bool:
    """Constant-time check of a submitted password against the configured one."""
    return hmac.compare_digest(submitted or "", password or "")


def cookie_ok(cookie_value: str | None, password: str) -> bool:
    """True when no password is configured, or the cookie matches the expected token."""
    if not password:
        return True
    return hmac.compare_digest(cookie_value or "", auth_token(password))
