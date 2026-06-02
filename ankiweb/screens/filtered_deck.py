from __future__ import annotations
import html
import json
from ankiweb.i18n import tr


def render_filtered_deck_html(col, deck_id: int) -> str:
    g = col.sched.get_or_create_filtered_deck(deck_id)
    cfg = g.config
    labels = list(col.sched.filtered_deck_order_labels())
    terms = list(cfg.search_terms)
    t0 = terms[0] if terms else None
    t1 = terms[1] if len(terms) > 1 else None
    is_edit = g.id != 0

    def order_select(sel_id: str, selected: int) -> str:
        opts = "".join(
            f"<option value='{i}'{' selected' if i == selected else ''}>{html.escape(l)}</option>"
            for i, l in enumerate(labels))
        return f'<select id="{sel_id}">{opts}</select>'

    name = html.escape(g.name)
    search1 = html.escape(t0.search if t0 else "")
    limit1 = t0.limit if t0 else 100
    order1 = t0.order if t0 else 0
    has2 = t1 is not None
    search2 = html.escape(t1.search if t1 else "")
    limit2 = t1.limit if t1 else 20
    order2 = t1.order if t1 else 5
    resched = "checked" if cfg.reschedule else ""
    allow_empty = "checked" if g.allow_empty else ""
    second_checked = "checked" if has2 else ""
    second_disp = "" if has2 else "display:none;"
    preview_disp = "display:none;" if cfg.reschedule else ""
    oklabel = tr.actions_rebuild() if is_edit else tr.decks_build()
    # "Filtered Deck" has no clean Anki key → keep as a keyless English suffix; only the
    # verb is translated (Edit) / kept English (Create, to preserve byte-identical default).
    heading = f"{tr.studying_edit() if is_edit else 'Create'} Filtered Deck"
    L_name = html.escape(tr.deck_config_name_prompt())
    L_filter = html.escape(tr.actions_filter())
    L_search = html.escape(tr.actions_search())
    L_limit = html.escape(tr.decks_limit_to())
    L_order = html.escape(tr.scheduling_order())

    body = f"""
<div class='filtered-deck'>
  <h3>{heading}</h3>
  <form id="fd" onsubmit='return false;'>
    <input type='hidden' id="did" value='{g.id}'>
    <div><label>{L_name} <input type='text' id="name" value="{name}" size='30'></label></div>
    <fieldset><legend>{L_filter}</legend>
      <div><label>{L_search} <input type='text' id="search1" value="{search1}" size='40'></label></div>
      <div><label>{L_limit} <input type='number' id="limit1" value='{limit1}' min='1' style='width:6em;'></label>
           &nbsp; {L_order} {order_select('order1', order1)}</div>
    </fieldset>
    <div><label><input type='checkbox' id="second" {second_checked} onchange='onSecond()'> {html.escape(tr.decks_enable_second_filter())}</label></div>
    <fieldset id="filter2" style='{second_disp}'><legend>{html.escape(tr.decks_filter_2())}</legend>
      <div><label>{L_search} <input type='text' id="search2" value="{search2}" size='40'></label></div>
      <div><label>{L_limit} <input type='number' id="limit2" value='{limit2}' min='1' style='width:6em;'></label>
           &nbsp; {L_order} {order_select('order2', order2)}</div>
    </fieldset>
    <div style='margin-top:8px;'><label><input type='checkbox' id="resched" {resched} onchange='onResched()'> {html.escape(tr.decks_reschedule_cards_based_on_my_answers())}</label></div>
    <fieldset id="previewblock" style='{preview_disp}'><legend>Preview delays (seconds)</legend>
      <label>{html.escape(tr.studying_again())} <input type='number' id="preview_again" value='{cfg.preview_again_secs}' min='0' style='width:6em;'></label>
      <label>{html.escape(tr.studying_hard())} <input type='number' id="preview_hard" value='{cfg.preview_hard_secs}' min='0' style='width:6em;'></label>
      <label>{html.escape(tr.studying_good())} <input type='number' id="preview_good" value='{cfg.preview_good_secs}' min='0' style='width:6em;'></label>
    </fieldset>
    <div style='margin-top:8px;'><label><input type='checkbox' id="allow_empty" {allow_empty}> {html.escape(tr.decks_create_even_if_empty())}</label></div>
    <div style='margin-top:10px;'>
      <button type='button' id="go" onclick='submitFd()'>{html.escape(oklabel)}</button>
      <button type='button' onclick="pycmd('cancel')">{html.escape(tr.actions_cancel())}</button>
    </div>
    <div id="err" style='color:#c00;margin-top:8px;'></div>
  </form>
</div>
<script>
function chk(id) {{ return document.getElementById(id).checked; }}
function val(id) {{ return document.getElementById(id).value; }}
function num(id) {{ return parseInt(document.getElementById(id).value || '0'); }}
function onSecond() {{ document.getElementById('filter2').style.display = chk('second') ? '' : 'none'; }}
function onResched() {{ document.getElementById('previewblock').style.display = chk('resched') ? 'none' : ''; }}
function submitFd() {{
  document.getElementById('err').textContent = '';
  var p = {{
    id: parseInt(val('did')), name: val('name'), reschedule: chk('resched'),
    search1: val('search1'), limit1: num('limit1'), order1: parseInt(val('order1')),
    second: chk('second'), search2: val('search2'), limit2: num('limit2'), order2: parseInt(val('order2')),
    preview_again: num('preview_again'), preview_hard: num('preview_hard'), preview_good: num('preview_good'),
    allow_empty: chk('allow_empty')
  }};
  pycmd('submit:' + JSON.stringify(p));
}}
window.ankiwebFilteredDeckError = function(msg) {{ document.getElementById('err').textContent = msg; }};
</script>
"""
    return body


def make_filtered_deck_handler(service, hub):
    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "cancel":
            await hub.push_call("filtereddeck", "ankiwebNavigate", ["/overview"])
            return None
        if cmd != "submit":
            return None
        try:
            p = json.loads(rest)
        except Exception:
            return None

        def build_and_run(col):
            import anki.decks_pb2 as dp
            g = col.sched.get_or_create_filtered_deck(int(p.get("id", 0)))
            g.name = p.get("name", g.name)
            g.allow_empty = bool(p.get("allow_empty"))
            cfg = g.config
            cfg.reschedule = bool(p.get("reschedule"))
            cfg.preview_again_secs = int(p.get("preview_again", 0))
            cfg.preview_hard_secs = int(p.get("preview_hard", 0))
            cfg.preview_good_secs = int(p.get("preview_good", 0))
            del cfg.delays[:]
            terms = [dp.Deck.Filtered.SearchTerm(
                search=p.get("search1", ""), limit=int(p.get("limit1", 100)),
                order=int(p.get("order1", 0)))]
            if p.get("second"):
                terms.append(dp.Deck.Filtered.SearchTerm(
                    search=p.get("search2", ""), limit=int(p.get("limit2", 20)),
                    order=int(p.get("order2", 5))))
            del cfg.search_terms[:]
            cfg.search_terms.extend(terms)
            out = col.sched.add_or_update_filtered_deck(g)
            col.decks.set_current(out.id)
            return out

        try:
            await service.run_op(build_and_run, initiator="filtereddeck")
        except Exception as e:
            from anki.errors import FilteredDeckError
            msg = str(e) if isinstance(e, FilteredDeckError) else "Could not build the filtered deck."
            await hub.push_call("filtereddeck", "ankiwebFilteredDeckError", [msg])
            return None
        await hub.push_call("filtereddeck", "ankiwebNavigate", ["/overview"])
        return None

    return handler
