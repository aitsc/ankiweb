from __future__ import annotations
import html
import json
from ankiweb.i18n import tr


def render_custom_study_html(col) -> str:
    did = col.decks.get_current_id()
    d = col.sched.custom_study_defaults(did)
    avail_new = d.available_new + d.available_new_in_children
    avail_rev = d.available_review + d.available_review_in_children

    radios = [
        (1, tr.custom_study_increase_todays_new_card_limit()),
        (2, tr.custom_study_increase_todays_review_card_limit()),
        (3, tr.custom_study_review_forgotten_cards()),
        (4, tr.custom_study_review_ahead()),
        (5, tr.custom_study_preview_new_cards()),
        (6, tr.custom_study_study_by_card_state_or_tag()),
    ]
    radio_html = "".join(
        f'<div><label><input type="radio" name="r" value="{v}"'
        f'{" checked" if v == 1 else ""} onchange="onRadio()"> {html.escape(t)}</label></div>'
        for v, t in radios
    )

    kinds = [(1, tr.custom_study_new_cards_only()), (0, tr.custom_study_due_cards_only()),
             (2, tr.custom_study_all_review_cards_in_random_order()),
             (3, tr.custom_study_all_cards_in_random_order_dont())]
    kind_opts = "".join(f"<option value='{k}'>{html.escape(t)}</option>" for k, t in kinds)
    tag_opts = "".join(
        f"<option value='{html.escape(t.name)}'>{html.escape(t.name)}</option>"
        for t in d.tags
    )

    # per-radio config: [label, default, suffix, min]
    cfg = {
        1: [tr.custom_study_increase_todays_new_card_limit_by(), d.extend_new or 0, tr.custom_study_cards(), -9999],
        2: [tr.custom_study_increase_todays_review_limit_by(), d.extend_review or 0, tr.custom_study_cards(), -9999],
        3: [tr.custom_study_review_cards_forgotten_in_last(), 1, tr.scheduling_days(), 1],
        4: [tr.custom_study_review_ahead_by(), 1, tr.scheduling_days(), 1],
        5: [tr.custom_study_preview_new_cards_added_in_the(), 1, tr.scheduling_days(), 1],
        6: [tr.custom_study_select(), 100, tr.custom_study_cards_from_the_deck(), 1],
    }

    body = f"""
<div class='custom-study'>
  <h3>{html.escape(tr.actions_custom_study())}</h3>
  <div class='avail'>New available: {avail_new} &nbsp; Review available: {avail_rev}</div>
  <form id='cs' onsubmit='return false;'>
    {radio_html}
    <div class='spinrow' style='margin:8px 0;'>
      <span id='spinlabel'></span>
      <input type="number" id="spin" value='{cfg[1][1]}' style='width:6em;'>
      <span id='spinsuffix'></span>
    </div>
    <div id='cramblock' style='display:none;'>
      <div>{html.escape(tr.browsing_sidebar_card_state())}
        <select id='cramkind'>{kind_opts}</select>
      </div>
      <div style='margin-top:6px;'>{html.escape(tr.custom_study_require_one_or_more_of_these())}<br>
        <select id='inc' multiple size='4'>{tag_opts}</select></div>
      <div style='margin-top:6px;'>{html.escape(tr.custom_study_select_tags_to_exclude())}<br>
        <select id='exc' multiple size='4'>{tag_opts}</select></div>
    </div>
    <div style='margin-top:10px;'>
      <button type='button' id='go' onclick='submitCs()'>{html.escape(tr.custom_study_ok())}</button>
      <button type='button' onclick="pycmd('cancel')">{html.escape(tr.actions_cancel())}</button>
    </div>
    <div id='err' style='color:#c00;margin-top:8px;'></div>
  </form>
</div>
<script>
var CFG = {json.dumps(cfg)};
function selectedRadio() {{
  var els = document.getElementsByName('r');
  for (var i = 0; i < els.length; i++) if (els[i].checked) return parseInt(els[i].value);
  return 1;
}}
function onRadio() {{
  var r = selectedRadio();
  var c = CFG[r];
  document.getElementById('spinlabel').textContent = c[0];
  document.getElementById('spin').value = c[1];
  document.getElementById('spin').min = c[3];
  document.getElementById('spinsuffix').textContent = c[2];
  document.getElementById('cramblock').style.display = (r === 6) ? '' : 'none';
}}
function multiVals(id) {{
  var out = [], el = document.getElementById(id);
  for (var i = 0; i < el.options.length; i++) if (el.options[i].selected) out.push(el.options[i].value);
  return out;
}}
function submitCs() {{
  document.getElementById('err').textContent = '';
  var r = selectedRadio();
  var payload = {{radio: r, value: parseInt(document.getElementById('spin').value || '0')}};
  if (r === 6) {{
    payload.cram_kind = parseInt(document.getElementById('cramkind').value);
    payload.include = multiVals('inc');
    payload.exclude = multiVals('exc');
  }}
  pycmd('submit:' + JSON.stringify(payload));
}}
window.ankiwebCustomStudyError = function(msg) {{
  document.getElementById('err').textContent = msg;
}};
onRadio();
</script>
"""
    return body


def make_custom_study_handler(service, hub):
    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "cancel":
            await hub.push_call("customstudy", "ankiwebNavigate", ["/overview"])
            return None
        if cmd != "submit":
            return None
        try:
            p = json.loads(rest)
        except Exception:
            return None
        radio = int(p.get("radio", 1))
        value = int(p.get("value", 0))

        def build_and_run(col):
            import anki.scheduler_pb2 as sp
            did = col.decks.get_current_id()
            req = sp.CustomStudyRequest(deck_id=did)
            if radio == 1:
                req.new_limit_delta = value
            elif radio == 2:
                req.review_limit_delta = value
            elif radio == 3:
                req.forgot_days = value
            elif radio == 4:
                req.review_ahead_days = value
            elif radio == 5:
                req.preview_days = value
            elif radio == 6:
                req.cram.kind = int(p.get("cram_kind", 1))
                req.cram.card_limit = value
                req.cram.tags_to_include.extend(p.get("include", []))
                req.cram.tags_to_exclude.extend(p.get("exclude", []))
            return col.sched.custom_study(req)

        try:
            await service.run_op(build_and_run, initiator="customstudy")
        except Exception as e:
            from anki.errors import CustomStudyError
            msg = str(e) if isinstance(e, CustomStudyError) else "Could not create a custom study session."
            await hub.push_call("customstudy", "ankiwebCustomStudyError", [msg])
            return None
        await hub.push_call("customstudy", "ankiwebNavigate", ["/overview"])
        return None

    return handler
