"""Process-wide UI translation access for ankiweb's hand-written screens.

`anki.lang.tr_legacyglobal` is a collection-free global translator, but it CRASHES
(`TypeError: 'NoneType' object is not callable`) until `anki.lang.set_lang` has run at
least once — and opening a `Collection` does NOT initialize it. Screens render the toolbar
without a `Collection` (and several tests call `render_page()` directly), so this module
guarantees a one-time, English-default `set_lang` at import. `CollectionService.open()`
still calls `set_lang(settings.lang or "en")` and overrides this default when `ANKIWEB_LANG`
is set (set_lang installs a fresh backend and repoints the shared `tr_legacyglobal`
translator at it, so the `tr` bound below keeps tracking the active language).

Usage:  from ankiweb.i18n import tr   ;   tr.actions_add()
Always import `tr` from here, never from `anki.lang` directly, so the guard runs first.
"""
from __future__ import annotations
import os
import anki.lang


def _ensure_lang() -> None:
    """Idempotent: initialize the global translator to ANKIWEB_LANG (or English) exactly
    once. A no-op if a language is already active (so open() can override, and tests that
    set a language are not clobbered)."""
    if anki.lang.current_i18n is None:
        anki.lang.set_lang(os.environ.get("ANKIWEB_LANG", "") or "en")


_ensure_lang()

from anki.lang import tr_legacyglobal as tr  # noqa: E402  (must follow _ensure_lang)

__all__ = ["tr"]
