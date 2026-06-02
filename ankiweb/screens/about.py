from __future__ import annotations
import html

_ANKI_SRC = "https://github.com/ankitects/anki"
_AC_SRC = "https://github.com/FooSoft/anki-connect"


def render_about_html(settings) -> str:
    """The AGPL §13 Corresponding-Source offer, shown to every user of the running app."""
    try:
        from importlib.metadata import version
        ver = version("ankiweb")
    except Exception:
        ver = "0.1.0"
    src = (getattr(settings, "source_url", "") or "").strip()
    if src:
        e = html.escape(src)
        src_line = f"<a href='{e}' target='_blank' rel='noopener'>{e}</a>"
    else:
        src_line = ("<em>not configured — set the <code>ANKIWEB_SOURCE_URL</code> environment "
                    "variable to the location of this deployment's source.</em>")
    return (
        "<div class='about' style='max-width:640px;margin:0 auto;'>"
        f"<h2>ankiweb {html.escape(ver)}</h2>"
        "<p><strong>Unofficial, personal, single-user project.</strong> An independent "
        "browser port of Anki — not affiliated with or endorsed by Ankitects, and not the "
        "official AnkiWeb sync service.</p>"
        "<p>ankiweb is free software, licensed under the <strong>GNU Affero General Public "
        "License, version 3 or later</strong> (AGPL-3.0-or-later). It is distributed in the "
        "hope that it will be useful, but WITHOUT ANY WARRANTY.</p>"
        "<h3>Source code (AGPL &sect;13)</h3>"
        "<p>Because ankiweb is a network service, you are entitled to the complete "
        "Corresponding Source of this running version, at no charge.</p>"
        f"<p><strong>This deployment's source:</strong> {src_line}</p>"
        "<p><strong>Upstream sources it derives from and bundles:</strong></p>"
        "<ul>"
        f"<li>Anki / aqt 25.9.4 — AGPL-3.0-or-later — "
        f"<a href='{_ANKI_SRC}' target='_blank' rel='noopener'>{_ANKI_SRC}</a></li>"
        f"<li>AnkiConnect — GPL-3.0-or-later — "
        f"<a href='{_AC_SRC}' target='_blank' rel='noopener'>{_AC_SRC}</a></li>"
        "</ul>"
        "<p>Full attribution is in the project's <code>LICENSE</code> and "
        "<code>THIRD-PARTY-NOTICES.md</code>.</p>"
        "<p><a href='/deckbrowser'>&larr; Back to decks</a></p>"
        "</div>"
    )
