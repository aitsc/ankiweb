from __future__ import annotations
from typing import Sequence


def render_page(context: str, body: str, css_files: Sequence[str] = ()) -> str:
    """Wrap a server-rendered fragment in a full shell HTML document.

    Sets window.__ankiwebContext BEFORE loading bootstrap.js so the Bridge connects
    to /ws?context=<context>. Links the given vendored CSS (paths relative to /_anki/).
    """
    links = "".join(
        f'<link rel="stylesheet" href="/_anki/{c}">' for c in css_files
    )
    return (
        "<!doctype html>\n"
        '<html><head><meta charset="utf-8">'
        f'<script>window.__ankiwebContext="{context}"</script>'
        f"{links}"
        '<script src="/shell/static/bootstrap.js"></script>'
        "</head>"
        f"<body>{body}</body></html>"
    )
