import anki.lang


def test_ensure_lang_initializes_when_none(monkeypatch):
    # Simulate a fresh process: no language set yet. Set current_i18n=None DIRECTLY (not via
    # monkeypatch.setattr, whose teardown-restore would desync it from tr_legacyglobal's
    # backend weakref); _ensure_lang -> set_lang resyncs both, and the autouse fixture resets
    # the next test.
    monkeypatch.delenv("ANKIWEB_LANG", raising=False)
    anki.lang.current_i18n = None
    from ankiweb.i18n import _ensure_lang
    _ensure_lang()
    assert anki.lang.current_i18n is not None
    # English default works without opening a Collection.
    assert anki.lang.tr_legacyglobal.actions_add() == "Add"


def test_tr_is_callable_without_collection():
    # Importing the module must have self-initialized; tr works with no Collection open.
    from ankiweb.i18n import tr
    assert tr.actions_add() == "Add"


def test_ensure_lang_honors_env(monkeypatch):
    monkeypatch.setenv("ANKIWEB_LANG", "zh-CN")
    anki.lang.current_i18n = None
    from ankiweb.i18n import _ensure_lang
    _ensure_lang()
    assert anki.lang.tr_legacyglobal.actions_add() == "添加"


def test_ensure_lang_is_idempotent_when_already_set(monkeypatch):
    # If a language is already active, _ensure_lang must NOT override it.
    anki.lang.set_lang("zh-CN")
    monkeypatch.setenv("ANKIWEB_LANG", "ja")  # would change it if guard were absent
    from ankiweb.i18n import _ensure_lang
    _ensure_lang()
    assert anki.lang.tr_legacyglobal.actions_add() == "添加"  # still zh-CN, not ja
