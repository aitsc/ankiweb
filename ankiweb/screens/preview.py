from __future__ import annotations
import html
from anki.sound import AV_REF_RE
from ankiweb.i18n import tr

_STYLE = (
    "<style>"
    ".preview{max-width:760px;margin:0 auto;}"
    ".preview-card{border:1px solid #ccc;border-radius:6px;padding:12px;margin:12px 0;}"
    ".preview-card h4{margin:0 0 8px;font-size:13px;color:#666;}"
    ".preview-label{font-size:12px;color:#888;text-transform:uppercase;margin:6px 0 2px;}"
    ".preview-side{padding:6px 0;}"
    ".preview hr{border:0;border-top:1px solid #ddd;margin:8px 0;}"
    "html.night-mode .preview-card{border-color:#555;}"
    "</style>"
)


def _strip_av(s: str) -> str:
    # preview is static (no reviewer JS) -> drop [anki:play:..] refs so they don't render as text
    return AV_REF_RE.sub("", s or "")


def render_preview_html(col, nid: int) -> str:
    """Read-only preview of every card of a note: each card's rendered question + answer
    (with the card's own CSS), reusing card.render_output(). No scheduling, no mutation."""
    note = col.get_note(nid)
    cards = note.cards()
    if not cards:
        return f"{_STYLE}<div class='preview'>(no cards)</div>"
    blocks = []
    for c in cards:
        o = c.render_output()
        tmpl = c.template()["name"]
        blocks.append(
            "<div class='preview-card'>"
            f"<h4>{html.escape(tmpl)}</h4>"
            f"<div class='preview-label'>Front</div>"
            f"<div class='preview-side'>{_strip_av(o.question_and_style())}</div>"
            "<hr>"
            f"<div class='preview-label'>Back</div>"
            f"<div class='preview-side'>{_strip_av(o.answer_and_style())}</div>"
            "</div>"
        )
    title = html.escape(tr.actions_preview())
    return f"{_STYLE}<div class='preview'><h3>{title}</h3>{''.join(blocks)}</div>"
