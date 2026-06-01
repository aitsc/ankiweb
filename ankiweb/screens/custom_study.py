from __future__ import annotations
import html
import json


def render_custom_study_html(col) -> str:
    did = col.decks.get_current_id()
    d = col.sched.custom_study_defaults(did)
    avail_new = d.available_new + d.available_new_in_children
    avail_rev = d.available_review + d.available_review_in_children

    radios = [
        (1, "Increase today's new card limit"),
        (2, "Increase today's review card limit"),
        (3, "Review forgotten cards"),
        (4, "Review ahead"),
        (5, "Preview new cards"),
        (6, "Study by card state or tag"),
    ]
    radio_html = "".join(
        f'<div><label><input type="radio" name="r" value="{v}"'
        f'{" checked" if v == 1 else ""} onchange="onRadio()"> {html.escape(t)}</label></div>'
        for v, t in radios
    )

    kinds = [(1, "New cards only"), (0, "Due cards only"),
             (2, "All review cards in random order"),
             (3, "All cards in random order (don't reschedule)")]
    kind_opts = "".join(f"<option value='{k}'>{html.escape(t)}</option>" for k, t in kinds)
    tag_opts = "".join(
        f"<option value='{html.escape(t.name)}'>{html.escape(t.name)}</option>"
        for t in d.tags
    )

    # per-radio config: [label, default, suffix, min]
    cfg = {
        1: ["Increase today's new card limit by", d.extend_new or 0, "cards", -9999],
        2: ["Increase today's review card limit by", d.extend_review or 0, "cards", -9999],
        3: ["Review cards forgotten in the last", 1, "days", 1],
        4: ["Review ahead by", 1, "days", 1],
        5: ["Preview new cards added in the last", 1, "days", 1],
        6: ["Select", 100, "cards from the deck", 1],
    }

    body = f"""
<div class='custom-study'>
  <h3>Custom Study</h3>
  <div class='avail'>New available: {avail_new} &nbsp; Review available: {avail_rev}</div>
  <form id='cs' onsubmit='return false;'>
    {radio_html}
    <div class='spinrow' style='margin:8px 0;'>
      <span id='spinlabel'></span>
      <input type="number" id="spin" value='{cfg[1][1]}' style='width:6em;'>
      <span id='spinsuffix'></span>
    </div>
    <div id='cramblock' style='display:none;'>
      <div>Card state:
        <select id='cramkind'>{kind_opts}</select>
      </div>
      <div style='margin-top:6px;'>Require one or more of these tags:<br>
        <select id='inc' multiple size='4'>{tag_opts}</select></div>
      <div style='margin-top:6px;'>Exclude tags:<br>
        <select id='exc' multiple size='4'>{tag_opts}</select></div>
    </div>
    <div style='margin-top:10px;'>
      <button type='button' id='go' onclick='submitCs()'>OK</button>
      <button type='button' onclick="pycmd('cancel')">Cancel</button>
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
