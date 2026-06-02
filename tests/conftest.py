from __future__ import annotations
import pytest
from pathlib import Path
from anki.collection import Collection


@pytest.fixture(autouse=True)
def _default_english_lang():
    """Reset the process-global UI language to English before each test so default-English
    assertions are order-independent (set_lang is process-global and sticky, and it keeps
    anki.lang.current_i18n in sync with tr_legacyglobal's backend). Tests that need another
    locale call anki.lang.set_lang(...) in their own body."""
    import anki.lang
    anki.lang.set_lang("en")
    yield


@pytest.fixture
def temp_collection(tmp_path: Path):
    col = Collection(str(tmp_path / "collection.anki2"))
    yield col
    col.close()
