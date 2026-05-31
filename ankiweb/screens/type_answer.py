from __future__ import annotations
import html as _html
import re

_TYPE_RE = re.compile(r"\[\[type:(.+?)\]\]")


def _parse_spec(spec: str):
    """'Back' / 'cloze:Text' / 'nc:Back' / 'cloze:nc:Text' -> (field, is_cloze, combining).
    anki emits the prefixes as cloze: then nc:, so strip them in a loop (any order)."""
    is_cloze = False
    combining = True
    changed = True
    while changed:
        changed = False
        if spec.startswith("cloze:"):
            is_cloze = True; spec = spec[len("cloze:"):]; changed = True
        if spec.startswith("nc:"):
            combining = False; spec = spec[len("nc:"):]; changed = True
    return spec.strip(), is_cloze, combining


def _field_font(model, field_name):
    for f in model["flds"]:
        if f["name"] == field_name:
            return f.get("font", "Arial"), f.get("size", 20)
    return "Arial", 20


def type_answer_question_filter(col, card, session, html: str) -> str:
    """Port of Qt typeAnsQuestionFilter: replace the [[type:...]] marker with an input,
    and stash the expected answer + flags on the session. Resets session if no marker."""
    session.type_correct = None
    session.type_combining = True
    session.type_font = "Arial"
    session.type_size = 20
    session.typed_answer = ""        # reset per card; set later by the "typed:" command
    m = _TYPE_RE.search(html)
    if m is None:
        return html
    field, is_cloze, combining = _parse_spec(m.group(1))
    note = card.note()
    model = note.note_type()
    if field not in note:   # unknown field → warn, no input (Qt shows a warning); type_correct stays None
        return _TYPE_RE.sub(
            "<center><b>Type-answer field not found: " + _html.escape(field) + "</b></center>", html)
    if is_cloze:
        expected = col.extract_cloze_for_typing(note[field], card.ord + 1)
    else:
        expected = note[field]
    if not expected:        # empty field → drop the marker, no input (Qt removes it); type_correct None
        return _TYPE_RE.sub("", html)
    session.type_correct = expected
    session.type_combining = combining
    session.type_font, session.type_size = _field_font(model, field)
    box = (f"<center><input type=text id=typeans onkeypress=\"ankiwebTypeAnsPress(event);\" "
           f"style=\"font-family:'{session.type_font}';font-size:{session.type_size}px;\">"
           f"</center>")
    return _TYPE_RE.sub(box, html)   # replace-all (a qfmt could carry the marker more than once)


def type_answer_answer_filter(col, session, html: str) -> str:
    """Port of Qt typeAnsAnswerFilter: replace [[type:...]] with the compare_answer diff."""
    if session.type_correct is None:
        return _TYPE_RE.sub("", html)   # no expected → drop any stray marker
    output = col.compare_answer(session.type_correct, session.typed_answer or "",
                                session.type_combining)
    block = (f"<div style=\"font-family:'{session.type_font}';"
             f"font-size:{session.type_size}px\">{output}</div>")
    # replace-all: {{FrontSide}} in an afmt re-includes the question's [[type:]] marker.
    return _TYPE_RE.sub(block, html)
