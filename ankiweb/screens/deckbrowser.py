from __future__ import annotations
import html


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
        "<tr><th colspan='1' align='left'>Decks</th>"
        "<th class='count'>New</th><th class='count'>Learn</th><th class='count'>Due</th>"
        "<th></th></tr>"
    ]
    if tree is not None:
        for child in tree.children:
            _render_node(child, current_id, rows)
    table = "<table cellspacing='0' cellpadding='3' class='decks'>" + "".join(rows) + "</table>"
    studied = f"<div id='studiedToday'><span>{html.escape(col.studied_today())}</span></div>"
    create = "<button onclick='ankiwebCreateDeck()'>Create Deck</button>"
    return f"<center>{table}{studied}<div class='dyn-buttons'>{create}</div></center>"
