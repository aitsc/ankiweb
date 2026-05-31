import tempfile, os
import pytest
from anki.collection import Collection
from ankiweb.screens.overview import render_overview_html
from ankiweb.screens.congrats import render_congrats_html


@pytest.fixture
def col():
    c = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))
    yield c
    c.close()


def test_overview_shows_counts_and_study_button(col):
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"
    col.add_note(n, col.decks.id("Default"))
    col.decks.set_current(col.decks.id("Default"))
    html = render_overview_html(col)
    assert "Default" in html               # deck name heading
    assert "Study Now" in html
    assert 'pycmd(\'study\')' in html or "study" in html
    assert "new-count" in html             # one new card shown


def test_overview_finished_shows_congrats(col):
    # empty Default deck → counts all zero → congrats
    col.decks.set_current(col.decks.id("Default"))
    html = render_overview_html(col)
    assert "Congratulations" in html or "congrats" in html.lower()


def test_congrats_fragment(col):
    html = render_congrats_html(col)
    assert "Congratulations" in html
