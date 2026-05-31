from __future__ import annotations
from typing import Sequence


def render_page(
    context: str,
    body: str,
    css_files: Sequence[str] = (),
    js_files: Sequence[str] = (),
) -> str:
    """Wrap a server-rendered fragment in a full shell HTML document.

    Sets window.__ankiwebContext BEFORE any script so the Bridge connects to
    /ws?context=<context>. Vendored js_files (served from /_anki/) load BEFORE
    the shell bootstrap.js, so globals they define (e.g. reviewer.js's
    window._showQuestion) exist when the page body's inline script runs.
    """
    links = "".join(f'<link rel="stylesheet" href="/_anki/{c}">' for c in css_files)
    scripts = "".join(f'<script src="/_anki/{j}"></script>' for j in js_files)
    return (
        "<!doctype html>\n"
        '<html><head><meta charset="utf-8">'
        f'<script>window.__ankiwebContext="{context}"</script>'
        f"{links}"
        f"{scripts}"
        '<script src="/shell/static/bootstrap.js"></script>'
        "</head>"
        f"<body>{body}</body></html>"
    )
