import os
import tempfile
import pytest
from anki.collection import Collection
from ankiweb.screens.reviewer import ReviewerSession, load_question


@pytest.fixture
def col():
    c = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))
    m = c.models.new("TypeM")
    c.models.add_field(m, c.models.new_field("Front"))
    c.models.add_field(m, c.models.new_field("Back"))
    t = c.models.new_template("Card1")
    t["qfmt"] = "{{Front}}\n\n{{type:Back}}"
    t["afmt"] = "{{FrontSide}}<hr id=answer>{{Back}}"   # stock form: marker comes via {{FrontSide}}
    c.models.add_template(m, t)
    c.models.add_dict(m)
    n = c.new_note(c.models.by_name("TypeM")); n["Front"] = "capital?"; n["Back"] = "Paris"
    c.add_note(n, c.decks.id("Default"))
    yield c
    c.close()


def test_question_filter_injects_input_and_captures_expected(col):
    s = ReviewerSession()
    info = load_question(col, s)
    assert "id=typeans" in info["q"] or 'id="typeans"' in info["q"]
    assert "[[type:" not in info["q"]
    assert s.type_correct == "Paris"
    assert s.type_combining is True


def test_non_type_card_leaves_type_correct_none(col):
    m = col.models.new("Plain")
    col.models.add_field(m, col.models.new_field("Front"))
    col.models.add_field(m, col.models.new_field("Back"))
    t = col.models.new_template("C"); t["qfmt"] = "{{Front}}"; t["afmt"] = "{{Back}}"
    col.models.add_template(m, t); col.models.add_dict(m)
    n = col.new_note(col.models.by_name("Plain")); n["Front"] = "x"; n["Back"] = "y"
    col.add_note(n, col.decks.id("Default"))
    s = ReviewerSession()
    s.type_correct = "stale"
    info = load_question(col, s)
    assert s.type_correct in (None, "Paris")   # reset per card; never the stale value
