"""ankiweb-original AnkiConnect-style actions.

These are exposed ONLY at /extra_actions/<name> (and documented in /docs); they are
deliberately NOT registered in the canonical ACTIONS, so the root POST / dispatcher reports
them as unsupported. Keeps the canonical AnkiConnect surface byte-identical to upstream.
"""
from ankiweb.ankiconnect.extra_actions import models  # noqa: F401 — registers extra actions
from ankiweb.ankiconnect.extra_actions import notify  # noqa: F401 — registers extra actions
