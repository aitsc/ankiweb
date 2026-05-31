from __future__ import annotations
import html as _html
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


_EASE_NAMES = ("Again", "Hard", "Good", "Easy")


def show_answer_bar() -> str:
    return "<button id='ansbut' class='ansbut' onclick=\"pycmd('ans')\">Show Answer</button>"


def ease_buttons_bar(labels) -> str:
    """labels: 4 interval strings in order [Again, Hard, Good, Easy]."""
    cells = []
    for i, name in enumerate(_EASE_NAMES, start=1):
        label = _html.escape(labels[i - 1]) if i - 1 < len(labels) else ""
        cells.append(
            f"<button class='ease' data-ease='{i}' onclick=\"pycmd('ease{i}')\">"
            f"<span class='ease-label'>{name}</span>"
            f"<span class='ease-ivl'>{label}</span></button>"
        )
    return "<div class='ease-row'>" + "".join(cells) + "</div>"


def reviewer_page_body() -> str:
    """The reviewer DOM shell + inline script that registers the JS calls the server
    pushes (_showQuestion/_showAnswer from reviewer.js; ankiwebSetAnswerBar for our bar)
    and asks the server for the first card on load."""
    return (
        "<div id='_mark' hidden>★</div>"
        "<div id='_flag' hidden>⚑</div>"
        "<div id='qa' dir='auto'></div>"
        "<div id='ankiweb-answer'></div>"
        "<script>(function(){"
        "var b=window.__ankiwebBridge;"
        "b.registerCalls({"
        "_showQuestion:function(){return window._showQuestion.apply(window,arguments);},"
        "_showAnswer:function(){return window._showAnswer.apply(window,arguments);},"
        "ankiwebSetAnswerBar:function(h){"
        "document.getElementById('ankiweb-answer').innerHTML=String(h);}"
        "});"
        "window.addEventListener('load',function(){window.pycmd('show');});"
        "})();</script>"
    )


def make_reviewer_handler(service, hub):
    """Bridge handler for the 'reviewer' context. Owns one ReviewerSession."""
    session = ReviewerSession()

    async def _show_next():
        info = await service.run(lambda col: load_question(col, session))
        if info is None:  # finished → overview (which renders Congrats)
            await hub.push_call("reviewer", "ankiwebNavigate", ["/overview"])
            return
        await hub.push_call("reviewer", "_showQuestion",
                            [info["q"], info["a"], info["bodyclass"]])
        await hub.push_call("reviewer", "ankiwebSetAnswerBar", [show_answer_bar()])

    async def handler(arg: str):
        if arg == "show":
            await _show_next()
        elif arg == "ans":
            info = await service.run(lambda col: render_answer(col, session))
            await hub.push_call("reviewer", "_showAnswer", [info["a"]])
            await hub.push_call("reviewer", "ankiwebSetAnswerBar",
                                [ease_buttons_bar(info["labels"])])
        elif arg in ("ease1", "ease2", "ease3", "ease4"):
            ease = int(arg[4:])
            await service.run_op(lambda col: answer_current(col, session, ease),
                                 initiator="reviewer")
            await _show_next()
        elif arg == "decks":
            await hub.push_call("reviewer", "ankiwebNavigate", ["/deckbrowser"])
        # ignore everything else (e.g. reviewer.js emits "updateToolbar" after each render)
        return None

    return handler
