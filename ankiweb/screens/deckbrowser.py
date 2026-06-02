from __future__ import annotations
import html

from ankiweb.i18n import tr


def _count_span(n: int, cls: str) -> str:
    return f"<span class='{cls}'>{n}</span>" if n else "<span class='zero-count'>0</span>"


def _render_node(node, current_id: int, out: list) -> None:
    indent = "&nbsp;" * 6 * (node.level - 1)
    row_class = "deck current" if node.deck_id == current_id else "deck"
    if node.children:
        prefix = "+" if node.collapsed else "−"  # − minus sign
        collapse = (f"<a class='collapse' href='#' "
                    f"onclick='return pycmd(\"collapse:{node.deck_id}\")'>{prefix}</a>")
    else:
        collapse = "<span class='collapse'></span>"
    filtered = " filtered" if node.filtered else ""
    name = (f"<a class='deck{filtered}' href='#' "
            f"onclick=\"return pycmd('open:{node.deck_id}')\">{html.escape(node.name)}</a>")
    gears = (f"<a class='opts' href='#' onclick='return pycmd(\"opts:{node.deck_id}\")'>"
             f"<img src='/_anki/imgs/gears.svg' class='gears'></a>")
    out.append(
        f"<tr class='{row_class}' id='{node.deck_id}'>"
        f"<td class='decktd'>{indent}{collapse}{name}</td>"
        f"<td align='right' class='count'>{_count_span(node.new_count, 'new-count')}</td>"
        f"<td align='right' class='count'>{_count_span(node.learn_count, 'learn-count')}</td>"
        f"<td align='right' class='count'>{_count_span(node.review_count, 'review-count')}</td>"
        f"<td align='center' class='opts'>{gears}</td>"
        f"</tr>"
    )
    if not node.collapsed:
        for child in node.children:
            _render_node(child, current_id, out)


def render_deckbrowser_html(col) -> str:
    tree = col.sched.deck_due_tree()
    current_id = col.decks.get_current_id()
    rows = [
        f"<tr><th colspan='1' align='left'>{tr.actions_decks()}</th>"
        f"<th class='count'>{tr.actions_new()}</th><th class='count'>{tr.decks_learn_header()}</th>"
        f"<th class='count'>{tr.decks_review_header()}</th>"
        "<th></th></tr>"
    ]
    if tree is not None:
        for child in tree.children:
            _render_node(child, current_id, rows)
    table = "<table cellspacing='0' cellpadding='3' class='decks'>" + "".join(rows) + "</table>"
    studied = f"<div id='studiedToday'><span>{html.escape(col.studied_today())}</span></div>"
    # Deck-management actions only — Decks/Add/Browse/Stats/night live in the global
    # top toolbar (render_page), shown on every screen.
    create = (f"<button onclick='ankiwebCreateDeck()'>{tr.decks_create_deck()}</button>"
              f" <button onclick='pycmd(\"createfiltered\")'>{tr.qt_misc_create_filtered_deck()}</button>"
              f" <button onclick='ankiwebImportFile()'>{tr.actions_import()}</button>"
              f" <a href='/export'>{tr.actions_export()}</a>"
              f" <button onclick='ankiwebImageOcclusion()'>{tr.notetypes_image_occlusion_name()}</button>")
    return f"<center>{table}{studied}<div class='dyn-buttons'>{create}</div></center>"


def make_deckbrowser_handler(service, hub):
    """Returns an async bridge handler(arg) for the 'deckbrowser' context."""
    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "open" or cmd == "select":
            did = int(rest)
            await service.run_op(lambda col: col.decks.set_current(did), initiator="deckbrowser")
            if cmd == "open":
                await hub.push_call("deckbrowser", "ankiwebNavigate", ["/overview"])
            else:
                await hub.push_call("deckbrowser", "ankiwebReload", [])
        elif cmd == "collapse":
            did = int(rest)

            def toggle(col):
                from anki.decks import DeckCollapseScope
                # Read persisted state from the deck dict, NOT the due-tree node:
                # deck_due_tree() prunes empty decks, so a node may be missing.
                collapsed = bool(col.decks.get(did).get("collapsed", False))
                return col.decks.set_collapsed(did, not collapsed, DeckCollapseScope.REVIEWER)

            await service.run_op(toggle, initiator="deckbrowser")
            await hub.push_call("deckbrowser", "ankiwebReload", [])
        elif cmd == "create":
            name = rest.strip()
            if name:
                await service.run_op(
                    lambda col: col.decks.add_normal_deck_with_name(name),
                    initiator="deckbrowser",
                )
                await hub.push_call("deckbrowser", "ankiwebReload", [])
        elif cmd == "opts":
            did = int(rest)
            is_dyn = await service.run(lambda col: bool(col.decks.get(did).get("dyn")))
            path = (f"/filtered-deck/{did}") if is_dyn else (f"/deck-options/{did}")
            await hub.push_call("deckbrowser", "ankiwebNavigate", [path])
        elif cmd == "createfiltered":
            await hub.push_call("deckbrowser", "ankiwebNavigate", ["/filtered-deck"])
        return None

    return handler
