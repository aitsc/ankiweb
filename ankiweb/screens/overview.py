from __future__ import annotations
import html
from ankiweb.screens.congrats import render_congrats_html


def make_overview_handler(service, hub):
    async def handler(arg: str):
        if arg == "study":
            await service.run(lambda col: col.startTimebox())
            await hub.push_call("overview", "ankiwebNavigate", ["/reviewer"])
        elif arg == "decks":
            await hub.push_call("overview", "ankiwebNavigate", ["/deckbrowser"])
        elif arg == "unbury":
            def unbury(col):
                from anki.scheduler.base import UnburyDeck
                return col.sched.unbury_deck(col.decks.get_current_id(), UnburyDeck.Mode.ALL)
            await service.run_op(unbury, initiator="overview")
            await hub.push_call("overview", "ankiwebReload", [])
        elif arg in ("refresh", "empty"):
            did = await service.run(lambda col: col.decks.get_current_id())
            is_dyn = await service.run(lambda col: bool(col.decks.get(did).get("dyn")))
            if is_dyn:  # rebuild/empty raise FilteredDeckError on a normal deck
                if arg == "refresh":
                    await service.run_op(lambda col: col.sched.rebuild_filtered_deck(did),
                                         initiator="overview")
                else:
                    await service.run_op(lambda col: col.sched.empty_filtered_deck(did),
                                         initiator="overview")
                await hub.push_call("overview", "ankiwebReload", [])
        elif arg == "studymore":
            await hub.push_call("overview", "ankiwebNavigate", ["/custom-study"])
        elif arg == "opts":
            did = await service.run(lambda col: col.decks.get_current_id())
            await hub.push_call("overview", "ankiwebNavigate", ["/deck-options/" + str(did)])
        # 'description' deferred to later plans.
        return None

    return handler


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
