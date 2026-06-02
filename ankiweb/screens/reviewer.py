from __future__ import annotations
import html as _html
from dataclasses import dataclass
from anki.sound import SoundOrVideoTag, AV_REF_RE
from ankiweb.i18n import tr


def render_av_buttons(text: str) -> str:
    """Replace [anki:play:<side>:<N>] refs with inline replay buttons (pycmd('play:..'))."""
    def repl(m):
        ref = m.group(1)  # e.g. "play:q:0"
        return ("<a class='replay-button soundLink' href=# "
                f"onclick=\"pycmd('{ref}');return false;\"><span>&#9654;</span></a>")
    return AV_REF_RE.sub(repl, text)


def av_sound_filenames(card, question_side: bool) -> list:
    """Ordered playable filenames for one side (SoundOrVideoTag only; TTS skipped)."""
    tags = card.question_av_tags() if question_side else card.answer_av_tags()
    return [t.filename for t in tags if isinstance(t, SoundOrVideoTag)]


def answer_side_audio(card) -> list:
    """Answer-side REPLAY list: question audio first if replayq, then answer audio."""
    files = []
    if card.replay_question_audio_on_answer_side():
        files += av_sound_filenames(card, True)
    files += av_sound_filenames(card, False)
    return files


@dataclass
class ReviewerSession:
    """Holds the in-flight card (timer started) and its scheduling states between
    show-question, show-answer, and answer. Single-user → one session per reviewer."""
    card: object = None      # anki.cards.Card with start_timer() already called
    states: object = None    # SchedulingStates from the queue
    context: object = None   # SchedulingContext
    type_correct: object = None     # expected answer string when the card has {{type:Field}}
    type_combining: bool = True
    type_font: str = "Arial"
    type_size: int = 20
    typed_answer: str = ""          # the user's typed value, set by the "typed:" command


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
    from ankiweb.screens.type_answer import type_answer_question_filter
    q = type_answer_question_filter(col, card, session, card.question())
    return {"q": render_av_buttons(q),
            "a": render_av_buttons(card.answer()),
            "bodyclass": f"card card{card.ord + 1}"}


def render_answer(col, session: ReviewerSession) -> dict:
    """Render the answer side + the 4 ease interval labels [Again, Hard, Good, Easy].
    Always runs the type-answer filter: replaces [[type:...]] with the compare_answer diff
    when type_correct is set, or strips any stray marker when None (no-op for Basic cards)."""
    from ankiweb.screens.type_answer import type_answer_answer_filter
    a = type_answer_answer_filter(col, session, session.card.answer())
    return {
        "a": render_av_buttons(a),
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


def _ease_names() -> tuple:
    """Per-request so the labels follow the active language."""
    return (tr.studying_again(), tr.studying_hard(), tr.studying_good(), tr.studying_easy())


def show_answer_bar() -> str:
    return ("<button id='ansbut' class='ansbut' "
            f"onclick=\"ankiwebShowAnswer()\">{tr.studying_show_answer()}</button>")


def ease_buttons_bar(labels) -> str:
    """labels: 4 interval strings in order [Again, Hard, Good, Easy]."""
    cells = []
    for i, name in enumerate(_ease_names(), start=1):
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
        "var _ankiAudio=null;"
        "var _side='question';"
        "function ankiwebPlayAudio(files){"
        "if(_ankiAudio){try{_ankiAudio.pause();}catch(e){} _ankiAudio=null;}"
        "files=files||[]; var i=0;"
        "function next(){"
        "if(i>=files.length)return;"
        "_ankiAudio=new Audio('/'+encodeURIComponent(files[i])); i++;"
        "_ankiAudio.addEventListener('ended',next);"
        "var p=_ankiAudio.play(); if(p&&p.catch){p.catch(function(){});}"
        "}"
        "next();"
        "}"
        "function ankiwebShowAnswer(){"
        "  var ta=document.getElementById('typeans');"
        "  if(ta&&ta.tagName==='INPUT'){window.pycmd('typed:'+ta.value);}"
        "  window.pycmd('ans');"
        "}"
        "window.ankiwebShowAnswer=ankiwebShowAnswer;"
        "function ankiwebTypeAnsPress(e){if(e&&(e.key==='Enter'||e.keyCode===13)){ankiwebShowAnswer();}}"
        "window.ankiwebTypeAnsPress=ankiwebTypeAnsPress;"
        "b.registerCalls({"
        "_showQuestion:function(){_side='question';return window._showQuestion.apply(window,arguments);},"
        "_showAnswer:function(){_side='answer';return window._showAnswer.apply(window,arguments);},"
        "ankiwebSetAnswerBar:function(h){"
        "document.getElementById('ankiweb-answer').innerHTML=String(h);},"
        "ankiwebPlayAudio:function(files){return ankiwebPlayAudio(files);}"
        "});"
        "document.addEventListener('keydown',function(e){"
        "  var t=document.activeElement;"
        "  if(t&&(t.id==='typeans'||t.tagName==='INPUT'||t.tagName==='TEXTAREA'))return;"
        "  var k=e.key;"
        "  if(k===' '||k==='Enter'){e.preventDefault();if(_side==='question'){window.ankiwebShowAnswer();}else{window.pycmd('ease3');}}"
        "  else if(_side==='answer'&&(k==='1'||k==='2'||k==='3'||k==='4')){e.preventDefault();window.pycmd('ease'+k);}"
        "  else if(k==='r'||k==='R'||k==='F5'){e.preventDefault();window.pycmd('replay');}"
        "  else if(k==='e'||k==='E'){e.preventDefault();window.pycmd('edit');}"
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
            hub.ui_state.current_card_id = None
            hub.ui_state.side = None
            await hub.push_call("reviewer", "ankiwebNavigate", ["/overview"])
            return
        hub.ui_state.current_card_id = session.card.id
        hub.ui_state.side = "question"
        await hub.push_call("reviewer", "_showQuestion",
                            [info["q"], info["a"], info["bodyclass"]])
        await hub.push_call("reviewer", "ankiwebSetAnswerBar", [show_answer_bar()])
        q_files = await service.run(
            lambda col: av_sound_filenames(session.card, True) if session.card.autoplay() else [])
        if q_files:
            await hub.push_call("reviewer", "ankiwebPlayAudio", [q_files])

    async def handler(arg: str):
        if arg == "show":
            await _show_next()
        elif arg == "ans":
            if session.card is None:
                return None
            info = await service.run(lambda col: render_answer(col, session))
            await hub.push_call("reviewer", "_showAnswer", [info["a"]])
            await hub.push_call("reviewer", "ankiwebSetAnswerBar",
                                [ease_buttons_bar(info["labels"])])
            hub.ui_state.side = "answer"
            a_files = await service.run(
                lambda col: av_sound_filenames(session.card, False) if session.card.autoplay() else [])
            if a_files:
                await hub.push_call("reviewer", "ankiwebPlayAudio", [a_files])
        elif arg in ("ease1", "ease2", "ease3", "ease4"):
            if session.card is None:
                return None
            ease = int(arg[4:])
            await service.run_op(lambda col: answer_current(col, session, ease),
                                 initiator="reviewer")
            await _show_next()
        elif arg == "edit":
            if session.card is not None:
                nid = await service.run(lambda col: session.card.nid)
                await hub.push_call("reviewer", "ankiwebNavigate", ["/edit?nid=" + str(nid)])
        elif arg == "starttimer":
            if session.card is not None:
                await service.run(lambda col: session.card.start_timer())
        elif arg == "replay":
            if session.card is not None:
                is_answer = hub.ui_state.side == "answer"
                files = await service.run(
                    lambda col: answer_side_audio(session.card) if is_answer
                    else av_sound_filenames(session.card, True))
                if files:
                    await hub.push_call("reviewer", "ankiwebPlayAudio", [files])
        elif arg.startswith("play:"):
            parts = arg.split(":")
            if len(parts) == 3 and session.card is not None:
                side, idx = parts[1], int(parts[2])

                def one(col):
                    tags = (session.card.question_av_tags() if side == "q"
                            else session.card.answer_av_tags())
                    if 0 <= idx < len(tags) and isinstance(tags[idx], SoundOrVideoTag):
                        return [tags[idx].filename]
                    return []
                files = await service.run(one)
                if files:
                    await hub.push_call("reviewer", "ankiwebPlayAudio", [files])
        elif arg.startswith("typed:"):
            session.typed_answer = arg[len("typed:"):]
        elif arg == "decks":
            await hub.push_call("reviewer", "ankiwebNavigate", ["/deckbrowser"])
        # ignore everything else (e.g. reviewer.js emits "updateToolbar" after each render)
        return None

    return handler
