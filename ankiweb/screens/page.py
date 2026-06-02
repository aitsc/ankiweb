from __future__ import annotations
import json
from typing import Sequence

from ankiweb.i18n import tr

# Base dark theme for the server-rendered screens. bootstrap.js adds the
# `night-mode` class to <html> when the persisted preference (or #night hash) is set.
_NIGHT_CSS = (
    "<style>"
    "html.night-mode body{background:#2b2b2b;color:#e0e0e0;}"
    "html.night-mode a{color:#6cb6ff;}"
    "html.night-mode button,html.night-mode input,html.night-mode select,"
    "html.night-mode textarea{background:#3a3a3a;color:#e0e0e0;border-color:#555;}"
    "html.night-mode table,html.night-mode th,html.night-mode td{border-color:#555;}"
    "html.night-mode .zero-count{color:#888;}"
    "</style>"
)

# Always-present top toolbar (Anki's main-window Decks/Add/Browse/Stats, minus Sync).
# Fixed at the top of every server-rendered screen; the body gets matching padding.
_TOOLBAR_CSS = (
    "<style>"
    "#ankiweb-toolbar{position:fixed;top:0;left:0;right:0;height:34px;display:flex;"
    "gap:16px;align-items:center;padding:0 12px;background:#f0f0f0;"
    "border-bottom:1px solid #ccc;z-index:2000;font-size:14px;}"
    "#ankiweb-toolbar a{text-decoration:none;color:#333;}"
    "#ankiweb-toolbar a:hover{text-decoration:underline;}"
    "#ankiweb-toolbar .nm{margin-left:auto;border:0;background:transparent;"
    "cursor:pointer;font-size:16px;}"
    "html.night-mode #ankiweb-toolbar{background:#1e1e1e;border-color:#444;}"
    "html.night-mode #ankiweb-toolbar a{color:#ccc;}"
    "body{padding-top:42px;}"
    "</style>"
)
def _toolbar_html() -> str:
    """Built per request so the labels reflect the active language (a module-level
    constant would freeze to the import-time locale). "Source" + the title= tooltips
    + the 🌙 emoji are ankiweb-specific (keyless) and stay English."""
    return (
        "<div id='ankiweb-toolbar'>"
        f"<a href='/deckbrowser'>{tr.actions_decks()}</a>"
        f"<a href='/add'>{tr.actions_add()}</a>"
        f"<a href='/browse'>{tr.qt_misc_browse()}</a>"
        f"<a href='/graphs'>{tr.qt_misc_stats()}</a>"
        f"<a href='/preferences'>{tr.preferences_preferences()}</a>"
        "<a href='/about' title='Source code (AGPL)'>Source</a>"
        "<button class='nm' onclick='ankiwebToggleNight()' title='Toggle night mode'>\U0001F319</button>"
        "</div>"
    )


def render_page(
    context: str,
    body: str,
    css_files: Sequence[str] = (),
    js_files: Sequence[str] = (),
    toolbar: bool = True,
) -> str:
    """Wrap a server-rendered fragment in a full shell HTML document.

    Sets window.__ankiwebContext BEFORE any script so the Bridge connects to
    /ws?context=<context>. Vendored js_files (served from /_anki/) load BEFORE
    the shell bootstrap.js, so globals they define (e.g. reviewer.js's
    window._showQuestion) exist when the page body's inline script runs.

    `toolbar` adds the always-present top toolbar (Decks/Add/Browse/Stats); pass
    False for embedded fragments like the editor iframe inside the Browser.
    """
    links = "".join(f'<link rel="stylesheet" href="/_anki/{c}">' for c in css_files)
    scripts = "".join(f'<script src="/_anki/{j}"></script>' for j in js_files)
    bar_css = _TOOLBAR_CSS if toolbar else ""
    bar_html = _toolbar_html() if toolbar else ""
    return (
        "<!doctype html>\n"
        '<html><head><meta charset="utf-8">'
        f"<script>window.__ankiwebContext={json.dumps(context)}</script>"
        f"{_NIGHT_CSS}"
        f"{bar_css}"
        f"{links}"
        f"{scripts}"
        '<script src="/shell/static/bootstrap.js"></script>'
        "</head>"
        f"<body>{bar_html}{body}</body></html>"
    )
