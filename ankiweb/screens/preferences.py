from __future__ import annotations
import html
import json

from ankiweb.i18n import tr


def _checkbox(field_id: str, label: str, checked: bool) -> str:
    c = " checked" if checked else ""
    return (f"<div><label><input type='checkbox' id='{field_id}'{c}> "
            f"{html.escape(label)}</label></div>")


def _number(field_id: str, label: str, value: int, minv: int = 0, maxv=None) -> str:
    mx = f" max='{maxv}'" if maxv is not None else ""
    return (f"<div><label>{html.escape(label)} "
            f"<input type='number' id='{field_id}' value='{int(value)}' "
            f"min='{minv}'{mx} style='width:6em;'></label></div>")


def render_preferences_html(col) -> str:
    """Server-rendered Preferences form over col.get_preferences()/set_preferences().
    Mirrors the E4/E5 form screens. The 2 INVERSE checkboxes (legacy timezone, show play
    buttons) render the negated proto value; savePrefs() inverts them back."""
    p = col.get_preferences()
    s, r, e, b = p.scheduling, p.reviewing, p.editing, p.backups

    mix_opts = "".join(
        f"<option value='{v}'{' selected' if s.new_review_mix == v else ''}>{html.escape(lbl)}</option>"
        for v, lbl in (
            (0, tr.scheduling_mix_new_cards_and_reviews()),
            (1, tr.scheduling_show_new_cards_after_reviews()),
            (2, tr.scheduling_show_new_cards_before_reviews()),
        ))

    scheduling = (
        f"<fieldset><legend>{html.escape(tr.preferences_scheduling())}</legend>"
        + _number("rollover", tr.preferences_next_day_starts_at(), s.rollover, 0, 23)
        + _number("learn_ahead_secs", tr.preferences_learn_ahead_limit(), s.learn_ahead_secs)
        + f"<div><label>{html.escape(tr.deck_config_new_review_priority())} "
          f"<select id='new_review_mix'>{mix_opts}</select></label></div>"
        # INVERSE: checked => legacy => new_timezone False
        + _checkbox("legacy_timezone", tr.preferences_legacy_timezone_handling(), not s.new_timezone)
        + _checkbox("day_learn_first", tr.preferences_show_learning_cards_with_larger_steps(), s.day_learn_first)
        + "</fieldset>"
    )

    reviewing = (
        f"<fieldset><legend>{html.escape(tr.preferences_review())}</legend>"
        # INVERSE: checked => show => hide_audio_play_buttons False
        + _checkbox("show_play_buttons", tr.preferences_show_play_buttons_on_cards_with(), not r.hide_audio_play_buttons)
        + _checkbox("interrupt_audio_when_answering", tr.preferences_interrupt_current_audio_when_answering(), r.interrupt_audio_when_answering)
        + _checkbox("show_remaining_due_counts", tr.preferences_show_remaining_card_count(), r.show_remaining_due_counts)
        + _checkbox("show_intervals_on_buttons", tr.preferences_show_next_review_time_above_answer(), r.show_intervals_on_buttons)
        + _number("time_limit_secs", tr.preferences_timebox_time_limit(), r.time_limit_secs)
        + _checkbox("load_balancer_enabled", "Enable load balancer", r.load_balancer_enabled)
        + _checkbox("fsrs_short_term_with_steps_enabled", "Use FSRS for short-term scheduling (with steps)", r.fsrs_short_term_with_steps_enabled)
        + "</fieldset>"
    )

    editing = (
        f"<fieldset><legend>{html.escape(tr.preferences_editing())}</legend>"
        + _checkbox("adding_defaults_to_current_deck", tr.preferences_when_adding_default_to_current_deck(), e.adding_defaults_to_current_deck)
        + _checkbox("paste_images_as_png", tr.preferences_paste_clipboard_images_as_png(), e.paste_images_as_png)
        + _checkbox("paste_strips_formatting", tr.preferences_paste_without_shift_key_strips_formatting(), e.paste_strips_formatting)
        + f"<div><label>{html.escape(tr.preferences_default_search_text())} "
          f"<input type='text' id='default_search_text' value=\"{html.escape(e.default_search_text)}\" size='30'></label></div>"
        + _checkbox("ignore_accents_in_search", tr.preferences_ignore_accents_in_search(), e.ignore_accents_in_search)
        + _checkbox("render_latex", tr.preferences_generate_latex_images_automatically(), e.render_latex)
        + "</fieldset>"
    )

    backups = (
        f"<fieldset><legend>{html.escape(tr.preferences_backups())}</legend>"
        + _number("daily", tr.preferences_daily_backups(), b.daily)
        + _number("weekly", tr.preferences_weekly_backups(), b.weekly)
        + _number("monthly", tr.preferences_monthly_backups(), b.monthly)
        + _number("minimum_interval_mins", tr.preferences_minutes_between_backups(), b.minimum_interval_mins)
        + "</fieldset>"
    )

    buttons = (
        "<div style='margin-top:10px;'>"
        f"<button type='button' id='save' onclick='savePrefs()'>{html.escape(tr.actions_save())}</button> "
        f"<button type='button' onclick=\"pycmd('cancel')\">{html.escape(tr.actions_cancel())}</button>"
        "</div><div id='err' style='color:#c00;margin-top:8px;'></div>"
    )

    script = """
<script>
function chk(id){ return document.getElementById(id).checked; }
function num(id){ return parseInt(document.getElementById(id).value || '0'); }
function val(id){ return document.getElementById(id).value; }
function savePrefs(){
  document.getElementById('err').textContent = '';
  var p = {
    rollover: num('rollover'), learn_ahead_secs: num('learn_ahead_secs'),
    new_review_mix: parseInt(document.getElementById('new_review_mix').value),
    new_timezone: !chk('legacy_timezone'), day_learn_first: chk('day_learn_first'),
    hide_audio_play_buttons: !chk('show_play_buttons'),
    interrupt_audio_when_answering: chk('interrupt_audio_when_answering'),
    show_remaining_due_counts: chk('show_remaining_due_counts'),
    show_intervals_on_buttons: chk('show_intervals_on_buttons'),
    time_limit_secs: num('time_limit_secs'),
    load_balancer_enabled: chk('load_balancer_enabled'),
    fsrs_short_term_with_steps_enabled: chk('fsrs_short_term_with_steps_enabled'),
    adding_defaults_to_current_deck: chk('adding_defaults_to_current_deck'),
    paste_images_as_png: chk('paste_images_as_png'),
    paste_strips_formatting: chk('paste_strips_formatting'),
    default_search_text: val('default_search_text'),
    ignore_accents_in_search: chk('ignore_accents_in_search'),
    render_latex: chk('render_latex'),
    daily: num('daily'), weekly: num('weekly'), monthly: num('monthly'),
    minimum_interval_mins: num('minimum_interval_mins')
  };
  pycmd('savePrefs:' + JSON.stringify(p));
}
window.ankiwebPrefsError = function(m){ document.getElementById('err').textContent = m; };
</script>
"""

    return (f"<div class='preferences'><h3>{html.escape(tr.preferences_preferences())}</h3>"
            f"<form id='pf' onsubmit='return false;'>{scheduling}{reviewing}{editing}{backups}"
            f"{buttons}</form></div>{script}")


def make_preferences_handler(service, hub):
    async def handler(arg: str):
        cmd, _, rest = arg.partition(":")
        if cmd == "cancel":
            await hub.push_call("preferences", "ankiwebNavigate", ["/deckbrowser"])
            return None
        if cmd != "savePrefs":
            return None
        try:
            p = json.loads(rest)
        except Exception:
            return None

        def apply(col):
            # Merge onto a FRESH get_preferences() and resend all 4 sections — set_preferences
            # writes each present section's scalars wholesale.
            prefs = col.get_preferences()
            s = prefs.scheduling
            s.rollover = int(p["rollover"])
            s.learn_ahead_secs = int(p["learn_ahead_secs"])
            s.new_review_mix = int(p["new_review_mix"])
            s.new_timezone = bool(p["new_timezone"])
            s.day_learn_first = bool(p["day_learn_first"])
            r = prefs.reviewing
            r.hide_audio_play_buttons = bool(p["hide_audio_play_buttons"])
            r.interrupt_audio_when_answering = bool(p["interrupt_audio_when_answering"])
            r.show_remaining_due_counts = bool(p["show_remaining_due_counts"])
            r.show_intervals_on_buttons = bool(p["show_intervals_on_buttons"])
            r.time_limit_secs = int(p["time_limit_secs"])
            r.load_balancer_enabled = bool(p["load_balancer_enabled"])
            r.fsrs_short_term_with_steps_enabled = bool(p["fsrs_short_term_with_steps_enabled"])
            ed = prefs.editing
            ed.adding_defaults_to_current_deck = bool(p["adding_defaults_to_current_deck"])
            ed.paste_images_as_png = bool(p["paste_images_as_png"])
            ed.paste_strips_formatting = bool(p["paste_strips_formatting"])
            ed.default_search_text = str(p["default_search_text"])
            ed.ignore_accents_in_search = bool(p["ignore_accents_in_search"])
            ed.render_latex = bool(p["render_latex"])
            bk = prefs.backups
            bk.daily = int(p["daily"])
            bk.weekly = int(p["weekly"])
            bk.monthly = int(p["monthly"])
            bk.minimum_interval_mins = int(p["minimum_interval_mins"])
            return col.set_preferences(prefs)

        try:
            await service.run_op(apply, initiator="preferences")
        except Exception as exc:
            await hub.push_call("preferences", "ankiwebPrefsError", [str(exc)])
            return None
        await hub.push_call("preferences", "ankiwebNavigate", ["/deckbrowser"])
        return None

    return handler
