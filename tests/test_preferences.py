import json
import anki.lang
from pathlib import Path
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.screens.preferences import render_preferences_html, make_preferences_handler


def test_render_default_english(temp_collection):
    html = render_preferences_html(temp_collection)
    assert "Next day starts at" in html       # preferences_next_day_starts_at
    assert "Learn ahead limit" in html
    assert "New/review order" in html          # deck_config_new_review_priority
    assert "Enable load balancer" in html      # english fallback
    assert "id='rollover'" in html
    assert "id='default_search_text'" in html


def test_render_zh(temp_collection):
    anki.lang.set_lang("zh-CN")
    html = render_preferences_html(temp_collection)
    assert "设置" in html                       # preferences_preferences heading


class _Hub:
    def __init__(self):
        self.calls = []

    async def push_call(self, ctx, fn, args):
        self.calls.append((fn, args))


async def _svc(tmp_path):
    svc = CollectionService(Settings(collection_path=tmp_path / "c.anki2"))
    await svc.open()
    return svc


async def test_saveprefs_roundtrip(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_preferences_handler(svc, hub)
    base = await svc.run(lambda col: col.get_preferences())
    payload = {
        "rollover": 6, "learn_ahead_secs": 99, "new_review_mix": 2,
        "new_timezone": base.scheduling.new_timezone, "day_learn_first": True,
        "hide_audio_play_buttons": False, "interrupt_audio_when_answering": True,
        "show_remaining_due_counts": True, "show_intervals_on_buttons": True,
        "time_limit_secs": 0, "load_balancer_enabled": True,
        "fsrs_short_term_with_steps_enabled": False,
        "adding_defaults_to_current_deck": True, "paste_images_as_png": False,
        "paste_strips_formatting": False, "default_search_text": "deck:current",
        "ignore_accents_in_search": False, "render_latex": False,
        "daily": 7, "weekly": 4, "monthly": 3, "minimum_interval_mins": 45,
    }
    await handler("savePrefs:" + json.dumps(payload))
    p = await svc.run(lambda col: col.get_preferences())
    assert p.scheduling.rollover == 6
    assert p.scheduling.learn_ahead_secs == 99
    assert p.scheduling.new_review_mix == 2
    assert p.scheduling.day_learn_first is True
    assert p.editing.default_search_text == "deck:current"
    assert p.backups.minimum_interval_mins == 45
    assert ("ankiwebNavigate", ["/deckbrowser"]) in hub.calls
    await svc.close()


async def test_saveprefs_inverse_checkboxes(tmp_path: Path):
    """legacy_timezone checked => new_timezone False; show_play_buttons unchecked => hide True."""
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_preferences_handler(svc, hub)
    base = await svc.run(lambda col: col.get_preferences())
    payload = {f.name: getattr(base.scheduling, f.name) for f in base.scheduling.DESCRIPTOR.fields}
    payload.update({f.name: getattr(base.reviewing, f.name) for f in base.reviewing.DESCRIPTOR.fields})
    payload.update({f.name: getattr(base.editing, f.name) for f in base.editing.DESCRIPTOR.fields})
    payload.update({f.name: getattr(base.backups, f.name) for f in base.backups.DESCRIPTOR.fields})
    # the JS would send these (inverted) proto values:
    payload["new_timezone"] = False
    payload["hide_audio_play_buttons"] = True
    await handler("savePrefs:" + json.dumps(payload))
    p = await svc.run(lambda col: col.get_preferences())
    assert p.scheduling.new_timezone is False
    assert p.reviewing.hide_audio_play_buttons is True
    await svc.close()


async def test_cancel_navigates(tmp_path: Path):
    svc = await _svc(tmp_path)
    hub = _Hub()
    handler = make_preferences_handler(svc, hub)
    await handler("cancel")
    assert ("ankiwebNavigate", ["/deckbrowser"]) in hub.calls
    await svc.close()
