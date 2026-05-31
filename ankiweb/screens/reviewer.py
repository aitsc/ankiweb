from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ReviewerSession:
    """Holds the in-flight card (timer started) and its scheduling states between
    show-question, show-answer, and answer. Single-user → one session per reviewer."""
    card: object = None      # anki.cards.Card with start_timer() already called
    states: object = None    # SchedulingStates from the queue
    context: object = None   # SchedulingContext


def load_question(col, session: ReviewerSession) -> dict | None:
    """Fetch the top queued card into the session, start its timer, render the question.
    Returns {"q","a","bodyclass"} or None when there are no cards left (finished)."""
    queued = col.sched.get_queued_cards(fetch_limit=1)
    if not queued.cards:
        session.card = session.states = session.context = None
        return None
    top = queued.cards[0]
    card = col.get_card(top.card.id)
    card.start_timer()  # REQUIRED: build_answer() later calls card.time_taken()
    session.card = card
    session.states = top.states
    session.context = top.context
    return {"q": card.question(), "a": card.answer(), "bodyclass": f"card card{card.ord + 1}"}


def render_answer(col, session: ReviewerSession) -> dict:
    """Render the answer side + the 4 ease interval labels [Again, Hard, Good, Easy]."""
    return {
        "a": session.card.answer(),
        "labels": list(col.sched.describe_next_states(session.states)),
    }


def answer_current(col, session: ReviewerSession, ease: int):
    """Answer the in-flight card with ease 1..4. Returns OpChanges."""
    from anki.scheduler.v3 import CardAnswer
    rating_map = {
        1: CardAnswer.Rating.AGAIN, 2: CardAnswer.Rating.HARD,
        3: CardAnswer.Rating.GOOD, 4: CardAnswer.Rating.EASY,
    }
    answer = col.sched.build_answer(
        card=session.card, states=session.states, rating=rating_map[ease]
    )
    return col.sched.answer_card(answer)
