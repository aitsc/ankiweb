from __future__ import annotations

_EXTENSION_SCHEMES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


def allow_origin(origin: str | None, cors_list: list) -> tuple[bool, str]:
    """Replicate AnkiConnect's allowOrigin. Returns (allowed, ACAO-header-value)."""
    if "*" in cors_list:
        return True, "*"
    if origin is None:  # curl / server-to-server (no Origin) is allowed
        return True, (cors_list[0] if cors_list else "*")
    if origin in cors_list:
        return True, origin
    if "http://localhost" in cors_list:
        # AnkiConnect treats localhost and 127.0.0.1 symmetrically, any scheme/port.
        if origin.startswith(("http://localhost", "https://localhost",
                              "http://127.0.0.1", "https://127.0.0.1")):
            return True, origin
        if origin.startswith(_EXTENSION_SCHEMES):
            return True, origin
    return False, origin
