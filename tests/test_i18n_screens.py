"""I2: hand-written screens follow the active UI language.

The autouse `_default_english_lang` fixture (conftest) resets to English before each test,
so the default-English tests need no setup; the zh-CN tests call set_lang in-body. Screens
use the process-global `tr` (ankiweb.i18n), so set_lang controls their language regardless
of how the test collection was opened.
"""
from __future__ import annotations
import anki.lang
from ankiweb.screens.page import render_page
from ankiweb.screens.deckbrowser import render_deckbrowser_html
from ankiweb.screens.custom_study import render_custom_study_html


def test_toolbar_default_english():
    html = render_page("deckbrowser", "<div>x</div>")
    assert ">Decks</a>" in html and ">Add</a>" in html
    assert ">Browse</a>" in html and ">Stats</a>" in html
    assert ">Source</a>" in html  # keyless, stays English


def test_toolbar_zh():
    anki.lang.set_lang("zh-CN")
    html = render_page("deckbrowser", "<div>x</div>")
    assert "牌组" in html and "浏览" in html and "统计" in html
    assert ">Source</a>" in html  # keyless stays English even in zh


def test_deckbrowser_default_english(temp_collection):
    html = render_deckbrowser_html(temp_collection)
    assert "Create Deck" in html and "Import" in html


def test_deckbrowser_zh(temp_collection):
    anki.lang.set_lang("zh-CN")
    html = render_deckbrowser_html(temp_collection)
    assert "创建牌组" in html and "导入" in html


def test_custom_study_default_english(temp_collection):
    html = render_custom_study_html(temp_collection)
    assert "Custom Study" in html
    assert "Increase today's new card limit" in html


def test_custom_study_zh(temp_collection):
    anki.lang.set_lang("zh-CN")
    html = render_custom_study_html(temp_collection)
    assert "自定义学习" in html
    assert "提升今日新卡片上限" in html
