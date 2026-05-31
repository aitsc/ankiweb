import tempfile, os
import pytest
from anki.collection import Collection
from anki.decks import DeckCollapseScope
from ankiweb.screens.deckbrowser import render_deckbrowser_html


@pytest.fixture
def col():
    c = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))
    yield c
    c.close()


def test_renders_default_deck_with_counts(col):
    # add one new card to the Default deck
    n = col.new_note(col.models.by_name("Basic")); n["Front"] = "q"
    col.add_note(n, col.decks.id("Default"))
    html = render_deckbrowser_html(col)
    assert "Default" in html
    # the Default deck row carries its deck id and the deck CSS class
    did = col.decks.id("Default")
    assert f"id='{did}'" in html or f'id="{did}"' in html
    assert "class='deck" in html or 'class="deck' in html
    # a new-count span exists (one new card)
    assert "new-count" in html
    assert "studiedToday" in html
    # open command wired
    assert f'pycmd(\'open:{did}\')' in html or f'open:{did}' in html


def test_subdeck_indented_and_nested(col):
    pid = col.decks.id("Parent")
    col.decks.id("Parent::Child")
    # newly-created parent decks default to collapsed=True (children hidden), like Anki;
    # expand it so the child row is rendered.
    col.decks.set_collapsed(pid, False, DeckCollapseScope.REVIEWER)
    html = render_deckbrowser_html(col)
    assert "Parent" in html and "Child" in html
    # child name is leaf-only
    assert ">Child<" in html
