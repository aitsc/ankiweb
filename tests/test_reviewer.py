import tempfile, os
import pytest
from anki.collection import Collection
from ankiweb.screens.reviewer import (
    ReviewerSession, load_question, render_answer, answer_current,
)


@pytest.fixture
def col():
    c = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))
    for i in range(2):
        n = c.new_note(c.models.by_name("Basic")); n["Front"] = f"Q{i}"; n["Back"] = f"A{i}"
        c.add_note(n, c.decks.id("Default"))
    yield c
    c.close()


def test_load_question_returns_html_and_sets_session(col):
    s = ReviewerSession()
    info = load_question(col, s)
    assert info is not None
    assert "Q0" in info["q"] or "Q1" in info["q"]   # one of the two cards' fronts
    assert info["bodyclass"].startswith("card card")
    assert s.card is not None and s.states is not None


def test_load_question_returns_none_when_finished(col):
    # bury both cards so the queue is empty → finished
    s = ReviewerSession()
    cids = col.find_cards("")
    col.sched.bury_cards(cids)
    assert load_question(col, s) is None
    assert s.card is None


def test_render_answer_has_answer_and_four_labels(col):
    s = ReviewerSession()
    load_question(col, s)
    info = render_answer(col, s)
    assert info["a"]                       # answer HTML present
    assert len(info["labels"]) == 4        # Again/Hard/Good/Easy interval labels


def test_answer_advances_queue(col):
    s = ReviewerSession()
    load_question(col, s)
    before = col.sched.counts()            # (new, learn, review)
    changes = answer_current(col, s, 3)    # rate Good
    assert changes.study_queues is True
    after = col.sched.counts()
    assert after != before                 # answering moved the card


def test_show_answer_bar():
    from ankiweb.screens.reviewer import show_answer_bar
    html = show_answer_bar()
    assert "Show Answer" in html
    assert "pycmd('ans')" in html


def test_ease_buttons_bar():
    from ankiweb.screens.reviewer import ease_buttons_bar
    html = ease_buttons_bar(["<1m", "<6m", "<10m", "3d"])
    for name in ("Again", "Hard", "Good", "Easy"):
        assert name in html
    for i in (1, 2, 3, 4):
        assert f"pycmd('ease{i}')" in html
    assert "3d" in html  # easy interval label rendered


def test_reviewer_page_body_loads_qa_and_registers():
    from ankiweb.screens.reviewer import reviewer_page_body
    body = reviewer_page_body()
    assert "id='qa'" in body or 'id="qa"' in body
    assert "ankiweb-answer" in body
    assert "registerCalls" in body
    assert "_showQuestion" in body
    assert "pycmd('show')" in body
