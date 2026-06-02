from __future__ import annotations
import html
from ankiweb.i18n import tr
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
            is_dyn = await service.run(lambda col: bool(col.decks.get(did).get("dyn")))
            path = (f"/filtered-deck/{did}") if is_dyn else (f"/deck-options/{did}")
            await hub.push_call("overview", "ankiwebNavigate", [path])
        elif arg.startswith("setdesc:"):
            import json
            try:
                p = json.loads(arg[len("setdesc:"):])
            except Exception:
                return None

            def save_desc(col):
                did = col.decks.get_current_id()
                d = col.decks.get(did)
                d["desc"] = p.get("desc", "")
                d["md"] = bool(p.get("md", False))
                return col.decks.update_dict(d)

            await service.run_op(save_desc, initiator="overview")
            await hub.push_call("overview", "ankiwebReload", [])
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
        f"<th>{tr.statistics_counts_new_cards()}</th><th>{tr.statistics_counts_learning_cards()}</th>"
        f"<th>{tr.studying_to_review()}</th></tr><tr>"
        f"{_number_cell(new, 'new-count')}"
        f"{_number_cell(learn, 'learn-count')}"
        f"{_number_cell(review, 'review-count')}"
        "</tr></table>"
    )
    study = ("<button id='study' class='but' autofocus "
             f"onclick=\"pycmd('study');return false;\">{tr.studying_study_now()}</button>")

    bottom = [f"<button onclick='pycmd(\"opts\")'>{tr.actions_options()}</button>"]
    if deck.get("dyn"):
        bottom.append(f"<button onclick='pycmd(\"refresh\")'>{tr.actions_rebuild()}</button>")
        bottom.append(f"<button onclick='pycmd(\"empty\")'>{tr.studying_empty()}</button>")
    else:
        bottom.append(f"<button onclick='pycmd(\"studymore\")'>{tr.actions_custom_study()}</button>")
    if col.sched.have_buried():
        bottom.append(f"<button onclick='pycmd(\"unbury\")'>{tr.studying_unbury()}</button>")
    bottom.append("<button onclick=\"document.getElementById('descedit').style.display=''\">"
                  f"{tr.studying_edit()} {tr.fields_description()}</button>")
    bottom.append(f"<button onclick='pycmd(\"decks\")'>{tr.actions_decks()}</button>")

    md_checked = "checked" if deck.get("md") else ""
    descedit = (
        "<div id='descedit' style='display:none;margin-top:10px;'>"
        f"<textarea id='descbox' rows='4' cols='50'>{html.escape(raw)}</textarea><br>"
        f"<label><input type='checkbox' id='descmd' {md_checked}> Render as markdown</label><br>"
        f"<button onclick='saveDesc()'>{tr.actions_save()}</button> "
        f"<button onclick=\"document.getElementById('descedit').style.display='none'\">{tr.actions_cancel()}</button>"
        "</div>"
        "<script>function saveDesc(){"
        "var d=document.getElementById('descbox').value,"
        "m=document.getElementById('descmd').checked;"
        "pycmd('setdesc:'+JSON.stringify({desc:d,md:m}));}</script>"
    )

    return (
        f"<center><h3>{name}</h3>{desc}{table}"
        f"<div class='studybtn'>{study}</div>"
        f"<div class='bottom-buttons'>{''.join(bottom)}</div>{descedit}</center>"
    )
