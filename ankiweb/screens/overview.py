from __future__ import annotations
import html
from ankiweb.screens.congrats import render_congrats_html


def _number_cell(n: int, cls: str) -> str:
    return f"<td align='center'><span class='{cls}'>{n}</span></td>"


def render_overview_html(col) -> str:
    deck = col.decks.current()
    new, learn, review = col.sched.counts()
    if new + learn + review == 0:
        # Nothing queued (counts already reflect limits/buried) → finished. Public-API
        # alternative to the private col.sched._is_finished().
        return render_congrats_html(col)

    name = html.escape(deck["name"])

    desc = ""
    raw = deck.get("desc", "")
    if raw:
        rendered = col.render_markdown(raw) if deck.get("md") else html.escape(raw)
        desc = f"<div class='descfont descmid description'>{rendered}</div>"

    table = (
        "<table cellspacing='0' cellpadding='5' class='overview-counts'><tr>"
        "<th>New</th><th>Learning</th><th>To Review</th></tr><tr>"
        f"{_number_cell(new, 'new-count')}"
        f"{_number_cell(learn, 'learn-count')}"
        f"{_number_cell(review, 'review-count')}"
        "</tr></table>"
    )
    study = ("<button id='study' class='but' autofocus "
             "onclick=\"pycmd('study');return false;\">Study Now</button>")

    bottom = ["<button onclick='pycmd(\"opts\")'>Options</button>"]
    if deck.get("dyn"):
        bottom.append("<button onclick='pycmd(\"refresh\")'>Rebuild</button>")
        bottom.append("<button onclick='pycmd(\"empty\")'>Empty</button>")
    else:
        bottom.append("<button onclick='pycmd(\"studymore\")'>Custom Study</button>")
    if col.sched.have_buried():
        bottom.append("<button onclick='pycmd(\"unbury\")'>Unbury</button>")
    bottom.append("<button onclick='pycmd(\"decks\")'>Decks</button>")

    return (
        f"<center><h3>{name}</h3>{desc}{table}"
        f"<div class='studybtn'>{study}</div>"
        f"<div class='bottom-buttons'>{''.join(bottom)}</div></center>"
    )
