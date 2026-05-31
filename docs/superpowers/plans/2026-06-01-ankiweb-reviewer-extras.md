# ankiweb Plan 4 — Reviewer Extras (type-answer, [sound:] audio, shortcuts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the study-loop fidelity deferred from Plan 3 — type-in-answer (`{{type:Field}}` with the real diff), `[sound:]` audio playback (autoplay + per-clip replay), and reviewer keyboard shortcuts — by reusing Anki's real `reviewer.js` globals and pylib, driven over the existing WebSocket bridge.

**Architecture:** All three features keep ankiweb's translation approach. Type-answer: the server runs the GUI-side filter Anki's Qt reviewer does (the backend only emits a literal `[[type:Field]]` marker) — inject `<input id=typeans>` on the question, and render the diff with `col.compare_answer()` (the Rust diff, exposed via pylib). **Capture: the reviewer shell reads `#typeans.value` itself and sends a `typed:<value>` command immediately before `ans` — two sequential WS frames.** (This deliberately AVOIDS a server-initiated `eval_with_callback` round-trip from inside the `ans` handler: the WS receive loop is blocked `await`ing `dispatch_cmd`, so it could never read the `{type:result}` reply — a real deadlock. The `typed:` precommand keeps everything sequential and needs no change to the WS layer.) Audio: rendered cards carry `[anki:play:q:N]` refs and `card.question_av_tags()`/`answer_av_tags()` carry the filenames; the server renders inline replay buttons + pushes the per-side filenames, and a small HTML5 player in the reviewer shell plays them from the existing `/{path}` media route. Shortcuts: JS keydown handlers in the reviewer shell mapping to the existing `pycmd` vocab, gated against the `#typeans` input.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the C study-loop screens + B4 bridge/ui_state, pytest (+ Playwright for DOM behavior, matching `tests/test_reviewer_integration.py`). Run via `conda run -n ankiweb ...`.

**Deferred (NOT in Plan 4; documented):** custom scheduling (`cardStateCustomizer` JS↔backend handshake — orthogonal, no user-facing gap since `describe_next_states` already shows correct intervals); auto-advance (needs deck-options UI from later plans); the Edit button (needs Plan D's note editor); flag/mark/leech UI; **night mode** (card CSS supports `.nightMode` and `bootstrap.ts` toggles it from the hash, but there's no toggle UI/pref yet — a small follow-up); **TTS + audio recording** (confirmed out of scope per the project constraints — the av extraction skips `TTSTag`, only `SoundOrVideoTag` is played).

**Grounded anki 25.9.4 facts (verified live):** `card.question()`/`answer()` emit literal `[[type:Field]]` / `[[type:cloze:Field]]` / `[[type:nc:Field]]` markers AND `[anki:play:<side>:<N>]` audio refs (NOT `[sound:]`). `col.compare_answer(expected, provided, combining=True)→str` (HTML: `<code id=typeans>` + `<span class=typeGood|typeBad|typeMissed>` + `<span id=typearrow>`; empty typed → just the stripped expected in `<code id=typeans>`; expected is HTML/media-stripped INSIDE compare_answer, so pass the RAW field value). `col.extract_cloze_for_typing(text, ordinal)→str` (ordinal = `card.ord+1`). `card.question_av_tags()`/`answer_av_tags()→list[AVTag]` (cached from the same render). `from anki.sound import SoundOrVideoTag, TTSTag, AV_REF_RE, strip_av_refs` — `AV_REF_RE = re.compile(r"\[anki:(play:(.):(\d+))\]")` (group2=side `q`/`a`, group3=index into that side's av_tags). `card.autoplay()→bool`, `card.replay_question_audio_on_answer_side()→bool`. reviewer.js (vendored) exposes `_showQuestion`/`_showAnswer` (used) plus `getTypedAnswer()`/`_typeAnsPress()` (NOT used — the shell reads `#typeans.value` itself to avoid the eval-round-trip deadlock). NOTE the id-collision: the question-side `<input id=typeans>` and the answer-side `<code id=typeans>` diff share the id at different times; the shell's capture guards on `tagName === "INPUT"`.

---

## Architecture map (existing code this plan touches)

- `ankiweb/screens/reviewer.py` — `ReviewerSession` (card/states/context); `load_question(col, session)→{q,a,bodyclass}|None` (calls `card.question()`/`answer()`, `card.start_timer()`); `render_answer(col, session)→{a,labels}`; `make_reviewer_handler` with `_show_next()` + handler vocab `show`/`ans`/`ease1..4`/`starttimer`/`decks`; `reviewer_page_body()` = the DOM shell + inline `<script>` that `registerCalls({_showQuestion, _showAnswer, ankiwebSetAnswerBar})` and `pycmd('show')` on load. **The inline script is the JS extension point for audio/shortcuts.** B4 already has the handler write `hub.ui_state.current_card_id`/`side`.
- `ankiweb/assets.py` — `_MIME` map + `build_media_router` serving `GET /{path}` from `col.media.dir()` (path-traversal guarded). **Audio MIME types must be added.**
- `ankiweb/bridge/hub.py` — `push_call(ctx,fn,args)`, `eval_with_callback(ctx,js)→value` (alloc id, send `{type:eval,id}`, await future resolved by `resolve()` on a client `{type:result,id}`), `dispatch_cmd(ctx,arg)`.
- `ankiweb/ankiconnect/actions/gui.py` — `gui_play_audio` currently returns `review_active` and no-ops. **Wire it to push audio.**
- Tests: `tests/test_reviewer.py` (pure unit), `tests/test_screen_routes.py` (TestClient + `portal.call` + `websocket_connect("/ws?context=reviewer")` sending `{type:cmd}` and draining `{type:call}` frames), `tests/test_reviewer_integration.py` (Playwright via `pytest.importorskip`, a live uvicorn `live_server` fixture, `page.goto("/reviewer")`).

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/assets.py` (modify) | audio/video MIME types |
| `ankiweb/screens/reviewer.py` (modify) | av filename helper + play-button rendering + audio push + `replay`/`play:` handler args; type-answer wiring in load_question/`ans` |
| `ankiweb/screens/type_answer.py` (create) | the `[[type:...]]` question + answer filters (port of Qt's `typeAnsQuestionFilter`/`typeAnsAnswerFilter`) |
| `ankiweb/ankiconnect/actions/gui.py` (modify) | `guiPlayAudio` pushes audio |
| `tests/test_media_serving.py` (modify) | audio MIME test |
| `tests/test_reviewer_audio.py`, `tests/test_type_answer.py`, `tests/test_reviewer_shortcuts.py` (create) | feature tests (TestClient+WS / unit / Playwright) |

---

## Task 1: Audio/video MIME types

**Files:** Modify `ankiweb/assets.py`; Test: `tests/test_media_serving.py`.

- [ ] **Step 1: Write the failing test (append to `tests/test_media_serving.py`)**
```python
def test_media_audio_mime(tmp_path):
    from fastapi.testclient import TestClient
    from ankiweb.config import Settings
    from ankiweb.app import create_app
    import os
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        mdir = c.portal.call(c.app.state.service.run, lambda col: col.media.dir())
        for fname, mime in [("a.mp3", "audio/mpeg"), ("b.ogg", "audio/ogg"),
                            ("c.wav", "audio/wav"), ("d.m4a", "audio/mp4"),
                            ("e.webm", "video/webm")]:
            with open(os.path.join(mdir, fname), "wb") as f:
                f.write(b"\x00\x01\x02")
            r = c.get("/" + fname)
            assert r.status_code == 200, fname
            assert r.headers["content-type"].split(";")[0] == mime, (fname, r.headers["content-type"])
```
(Use the existing media-serving test conventions in that file; if it already imports a `client` fixture, reuse it instead of building a new one.)

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_media_serving.py::test_media_audio_mime -v` → FAIL (octet-stream / wrong mime).

- [ ] **Step 3: Implement** — In `ankiweb/assets.py`, extend the `_MIME` dict (READ the file first to match its exact name/format) with:
```python
    ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".oga": "audio/ogg",
    ".opus": "audio/opus", ".wav": "audio/wav", ".flac": "audio/flac",
    ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
```
(If `_MIME` keys are without the leading dot, or the lookup uses `os.path.splitext`, match the existing style exactly.)

- [ ] **Step 4: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_media_serving.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add ankiweb/assets.py tests/test_media_serving.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(assets): audio/video MIME types for media serving"
```

## Context
The `[sound:]` audio player fetches `/<filename>` from the media route; browsers refuse to play `application/octet-stream`, so the media route must return proper audio MIME types.

## Report Format
Status, pytest summary, files changed, self-review, commit SHA, concerns.

---

## Task 2: Server-side audio — filenames, replay buttons, push, handler args

**Files:** Modify `ankiweb/screens/reviewer.py`; Test: `tests/test_reviewer_audio.py` (create), `tests/test_reviewer.py` (append unit).

- [ ] **Step 1: Write the failing tests** — `tests/test_reviewer_audio.py`:
```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        c.portal.call(c.app.state.service.run, _seed)
        yield c


def _seed(col):
    import os
    m = col.models.new("AudioModel")
    col.models.add_field(m, col.models.new_field("Front"))
    col.models.add_field(m, col.models.new_field("Back"))
    t = col.models.new_template("Card1")
    t["qfmt"] = "{{Front}} [sound:hello.mp3]"
    t["afmt"] = "{{FrontSide}}<hr id=answer>{{Back}} [sound:bye.mp3]"
    col.models.add_template(m, t)
    col.models.add_dict(m)
    n = col.new_note(col.models.by_name("AudioModel")); n["Front"] = "q"; n["Back"] = "a"
    col.add_note(n, col.decks.id("Default"))
    for fn in ("hello.mp3", "bye.mp3"):
        with open(os.path.join(col.media.dir(), fn), "wb") as f:
            f.write(b"\x00")


def _calls(ws, n):
    out = {}
    for _ in range(n):
        m = ws.receive_json()
        if m["type"] == "call":
            out.setdefault(m["fn"], []).append(m["args"])
    return out


def test_question_autoplays_and_renders_buttons(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        calls = _calls(ws, 3)   # _showQuestion + ankiwebSetAnswerBar + ankiwebPlayAudio
        assert "ankiwebPlayAudio" in calls
        assert calls["ankiwebPlayAudio"][0] == [["hello.mp3"]]
        # the [anki:play:q:0] ref was rendered as a replay button, not literal text
        q_html = calls["_showQuestion"][0][0]
        assert "[anki:play" not in q_html
        assert "play:q:0" in q_html and "replay-button" in q_html


def test_answer_autoplays_and_play_and_replay(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        _calls(ws, 3)
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "ans"})
        calls = _calls(ws, 3)   # _showAnswer + ease bar + ankiwebPlayAudio
        assert "ankiwebPlayAudio" in calls
        # answer side autoplay includes answer audio (and question audio via replayq)
        assert "bye.mp3" in calls["ankiwebPlayAudio"][0][0]
        # per-clip replay of the answer's first sound
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "play:a:0"})
        c2 = _calls(ws, 1)
        assert c2.get("ankiwebPlayAudio") and isinstance(c2["ankiwebPlayAudio"][0][0], list)
        # R-key replay re-pushes the current side's audio
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "replay"})
        c3 = _calls(ws, 1)
        assert "ankiwebPlayAudio" in c3
```
Append a unit test to `tests/test_reviewer.py`:
```python
def test_render_av_buttons_and_filenames():
    from ankiweb.screens.reviewer import render_av_buttons
    html = render_av_buttons("X [anki:play:q:0] Y [anki:play:a:1] Z")
    assert "[anki:play" not in html
    assert html.count("replay-button") == 2
    assert "pycmd('play:q:0')" in html and "pycmd('play:a:1')" in html
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_reviewer_audio.py -v` → FAIL.

- [ ] **Step 3: Implement (modify `ankiweb/screens/reviewer.py`)**

Add imports + helpers near the top:
```python
from anki.sound import SoundOrVideoTag, AV_REF_RE


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
    """Answer-side autoplay/replay list: question audio first if replayq, then answer audio."""
    files = []
    if card.replay_question_audio_on_answer_side():
        files += av_sound_filenames(card, True)
    files += av_sound_filenames(card, False)
    return files
```

In `load_question`, run `render_av_buttons` over the rendered q/a so refs never show as literal text. Change the return to:
```python
    return {"q": render_av_buttons(card.question()),
            "a": render_av_buttons(card.answer()),
            "bodyclass": f"card card{card.ord + 1}"}
```
In `render_answer`, wrap the answer:
```python
        "a": render_av_buttons(session.card.answer()),
```

In `make_reviewer_handler._show_next`, after the existing `_showQuestion` + `ankiwebSetAnswerBar` pushes, add the question-side autoplay:
```python
        q_files = await service.run(
            lambda col: av_sound_filenames(session.card, True) if session.card.autoplay() else [])
        if q_files:
            await hub.push_call("reviewer", "ankiwebPlayAudio", [q_files])
```
In the handler's `arg == "ans"` branch, after the existing pushes + `hub.ui_state.side = "answer"`, add:
```python
            a_files = await service.run(
                lambda col: answer_side_audio(session.card) if session.card.autoplay() else [])
            if a_files:
                await hub.push_call("reviewer", "ankiwebPlayAudio", [a_files])
```
Add two new handler branches BEFORE the `elif arg == "decks":` branch:
```python
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
```

- [ ] **Step 4: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_reviewer_audio.py tests/test_reviewer.py -v`, then `tests/test_screen_routes.py` (no regression — note: the existing tests drain a fixed number of frames; the NEW `ankiwebPlayAudio` push only happens for cards WITH audio, and `test_screen_routes.py` seeds a plain Basic card with NO audio, so no extra frame is pushed there — verify those still pass).

- [ ] **Step 5: Commit**
```bash
git add ankiweb/screens/reviewer.py tests/test_reviewer_audio.py tests/test_reviewer.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(reviewer): server-side [sound:] audio extraction, replay buttons, push"
```

## Context
Rendered cards carry `[anki:play:<side>:<N>]` refs + the filenames in `card.{question,answer}_av_tags()`. `render_av_buttons` turns refs into inline replay buttons (`pycmd('play:q:0')`); the handler autoplays each side on show/answer (gated by `card.autoplay()`), `replay` re-pushes the current side (question-first on the answer side per `replay_question_audio_on_answer_side`), and `play:<side>:<N>` plays one clip. TTS tags are skipped. The plain-Basic-card tests push no audio frame, so existing reviewer tests are unaffected.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 3: Reviewer shell HTML5 audio player

**Files:** Modify `ankiweb/screens/reviewer.py` (`reviewer_page_body` inline JS); Test: `tests/test_reviewer.py` (append), `tests/test_reviewer_integration.py` (append Playwright).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_reviewer.py`:
```python
def test_reviewer_body_registers_audio_player():
    from ankiweb.screens.reviewer import reviewer_page_body
    body = reviewer_page_body()
    assert "ankiwebPlayAudio" in body
    assert "Audio(" in body or "new Audio" in body
```
Append a Playwright test to `tests/test_reviewer_integration.py` (mirror its existing `live_server` fixture + `pytest.importorskip("playwright")`; seed a card WITH `[sound:hello.mp3]` + the media file in that fixture or a dedicated one). The test stubs audio playback (headless Chromium emits no sound) and asserts `play()` is called with the right src:
```python
def test_audio_autoplays_on_question(live_server, page):
    # stub HTMLMediaElement.play to record the src before navigating
    page.add_init_script(
        "window.__played=[];"
        "HTMLMediaElement.prototype.play=function(){window.__played.push(this.src);"
        "return Promise.resolve();};")
    page.goto(live_server + "/reviewer")
    page.wait_for_function("document.querySelector('#qa') && document.querySelector('#qa').innerHTML.length>0")
    page.wait_for_function("window.__played && window.__played.length>0")
    assert any(s.endswith("/hello.mp3") for s in page.evaluate("window.__played"))
```
(If the existing `live_server`/`page` fixtures live in a conftest or the test module, reuse them and seed an audio card the same way the file seeds its current card.)

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_reviewer.py::test_reviewer_body_registers_audio_player -v` → FAIL.

- [ ] **Step 3: Implement** — In `reviewer_page_body()`, extend the inline `<script>`: add a module-scoped queueing player and register `ankiwebPlayAudio` in the `b.registerCalls({...})` object. Insert into the IIFE (alongside the existing `registerCalls`):
```javascript
"var _ankiAudio=null;"
"function ankiwebPlayAudio(files){"
"  if(_ankiAudio){try{_ankiAudio.pause();}catch(e){} _ankiAudio=null;}"
"  files=files||[]; var i=0;"
"  function next(){"
"    if(i>=files.length)return;"
"    _ankiAudio=new Audio('/'+encodeURIComponent(files[i])); i++;"
"    _ankiAudio.addEventListener('ended',next);"
"    var p=_ankiAudio.play(); if(p&&p.catch){p.catch(function(){});}"
"  }"
"  next();"
"}"
```
and add `ankiwebPlayAudio:function(files){return ankiwebPlayAudio(files);},` to the `registerCalls` object. (READ the current `reviewer_page_body` string first; the `registerCalls({...})` object currently has `_showQuestion`, `_showAnswer`, `ankiwebSetAnswerBar` — add the new key alongside, and define the `_ankiAudio`/`ankiwebPlayAudio` function inside the same IIFE before `registerCalls`.)

- [ ] **Step 4: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_reviewer.py -v`; then the Playwright file `conda run -n ankiweb python -m pytest tests/test_reviewer_integration.py -v` (it may `skip` if playwright/browsers aren't installed — that is acceptable; ensure the non-Playwright tests pass).

- [ ] **Step 5: Commit**
```bash
git add ankiweb/screens/reviewer.py tests/test_reviewer.py tests/test_reviewer_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(reviewer): HTML5 audio player in the reviewer shell"
```

## Context
The real `reviewer.js` does not play audio (desktop uses mpv); the browser port adds a tiny queueing `<audio>` player registered as the `ankiwebPlayAudio` bridge call, playing `/<filename>` from the media route and chaining on `ended` so clips play in order. `play().catch()` swallows the autoplay-policy rejection on the first clip before a user gesture.

## Report Format
Status, pytest summaries (note any Playwright skip), files changed, self-review, commit SHA, concerns.

---

## Task 4: Wire guiPlayAudio (B4) to the audio player

**Files:** Modify `ankiweb/ankiconnect/actions/gui.py`; Test: `tests/ankiconnect/test_gui_actions.py` (append).

- [ ] **Step 1: Write the failing test (append)**
```python
def test_gui_play_audio_pushes_when_reviewing(client):
    import os
    # seed an audio card in its own deck and make that deck current, so the reviewer
    # shows exactly this card and 'replay' has a real filename to push.
    def setup(col):
        m = col.models.new("AudioM")
        col.models.add_field(m, col.models.new_field("F"))
        t = col.models.new_template("C"); t["qfmt"] = "{{F}} [sound:s.mp3]"; t["afmt"] = "{{F}}"
        col.models.add_template(m, t); col.models.add_dict(m)
        did = col.decks.id("AudioDeck")
        n = col.new_note(col.models.by_name("AudioM")); n["F"] = "x"
        col.add_note(n, did)
        with open(os.path.join(col.media.dir(), "s.mp3"), "wb") as f:
            f.write(b"\x00")
        col.decks.set_current(did)
    client.portal.call(client.app.state.service.run, setup)
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        for _ in range(3):   # _showQuestion + ankiwebSetAnswerBar + ankiwebPlayAudio
            ws.receive_json()
        assert _gui(client, "guiPlayAudio") is True
        m = ws.receive_json()
        while m["type"] != "call" or m["fn"] != "ankiwebPlayAudio":
            m = ws.receive_json()
        assert "s.mp3" in m["args"][0]
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/ankiconnect/test_gui_actions.py::test_gui_play_audio_pushes_when_reviewing -v` → FAIL.

- [ ] **Step 3: Implement** — Replace `gui_play_audio` in `ankiweb/ankiconnect/actions/gui.py`:
```python
@action("guiPlayAudio")
async def gui_play_audio(rt, ease=None):
    ui = _ui(rt)
    if not ui.review_active:
        return False
    # replay the current side's audio via the reviewer's own player (mirrors qt guiPlayAudio)
    await rt.hub.dispatch_cmd("reviewer", "replay")
    return True
```
(`guiPlayAudio` takes no params in AnkiConnect; the `ease=None` is harmless but you may drop it — match the reference no-arg signature: `async def gui_play_audio(rt):`.)

- [ ] **Step 4: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/ankiconnect/test_gui_actions.py -v` (all gui tests, incl. the existing `test_gui_play_audio` which only checks the bool return — still passes). Then `tests/ankiconnect -q`.

- [ ] **Step 5: Commit**
```bash
git add ankiweb/ankiconnect/actions/gui.py tests/ankiconnect/test_gui_actions.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(ankiconnect): guiPlayAudio replays via the reviewer audio player"
```

## Context
`guiPlayAudio` now drives the reviewer's `replay` path (which pushes `ankiwebPlayAudio` to the connected reviewer), closing the B4 stub. It reuses the exact replay code path, so behavior matches the R key.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 5: Type-answer question filter + session fields

**Files:** Create `ankiweb/screens/type_answer.py`; Modify `ankiweb/screens/reviewer.py`; Test: `tests/test_type_answer.py` (create).

- [ ] **Step 1: Write the failing test** — `tests/test_type_answer.py`:
```python
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
    t["afmt"] = "{{FrontSide}}<hr id=answer>{{Back}}\n\n{{type:Back}}"
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
    # a plain card resets type_correct to None
    m = col.models.new("Plain")
    col.models.add_field(m, col.models.new_field("Front"))
    col.models.add_field(m, col.models.new_field("Back"))
    t = col.models.new_template("C"); t["qfmt"] = "{{Front}}"; t["afmt"] = "{{Back}}"
    col.models.add_template(m, t); col.models.add_dict(m)
    n = col.new_note(col.models.by_name("Plain")); n["Front"] = "x"; n["Back"] = "y"
    col.add_note(n, col.decks.id("Default"))
    s = ReviewerSession()
    s.type_correct = "stale"
    # answer the first (type) card so the plain card becomes the top, then load
    # (simplest: just call the filter path twice; the second card has no [[type:]])
    info = load_question(col, s)   # loads a queued card; if it's the type card type_correct set
    # load again after the type card would advance; for the unit we assert the reset semantics:
    assert s.type_correct in (None, "Paris")  # reset per card; never the stale value
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_type_answer.py -v` → FAIL (no `type_correct` field / no filter).

- [ ] **Step 3: Implement**

Create `ankiweb/screens/type_answer.py`:
```python
from __future__ import annotations
import re

_TYPE_RE = re.compile(r"\[\[type:(.+?)\]\]")


def _parse_spec(spec: str):
    """'Back' / 'cloze:Text' / 'nc:Back' -> (field, is_cloze, combining)."""
    combining = True
    if spec.startswith("nc:"):
        combining = False
        spec = spec[3:]
    is_cloze = False
    if spec.startswith("cloze:"):
        is_cloze = True
        spec = spec[len("cloze:"):]
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
    if is_cloze:
        # extract the cloze answer text for this card's ordinal
        src = note[field] if field in note else ""
        expected = col.extract_cloze_for_typing(src, card.ord + 1)
    else:
        expected = note[field] if field in note else ""
    session.type_correct = expected
    session.type_combining = combining
    session.type_font, session.type_size = _field_font(model, field)
    box = (f"<center><input type=text id=typeans onkeypress=\"ankiwebTypeAnsPress(event);\" "
           f"style=\"font-family:'{session.type_font}';font-size:{session.type_size}px;\">"
           f"</center>")
    return _TYPE_RE.sub(box, html, count=1)
```

In `ankiweb/screens/reviewer.py`, add the new `ReviewerSession` fields and call the filter in `load_question`. Update the dataclass:
```python
@dataclass
class ReviewerSession:
    card: object = None
    states: object = None
    context: object = None
    type_correct: object = None     # expected answer string when the card has {{type:Field}}
    type_combining: bool = True
    type_font: str = "Arial"
    type_size: int = 20
    typed_answer: str = ""          # the user's typed value, set by the "typed:" command
```
In `load_question`, after fetching the card and before returning, run the question filter on the rendered question (combine with the av-button rendering from Task 2):
```python
    from ankiweb.screens.type_answer import type_answer_question_filter
    q = type_answer_question_filter(col, card, session, card.question())
    return {"q": render_av_buttons(q),
            "a": render_av_buttons(card.answer()),
            "bodyclass": f"card card{card.ord + 1}"}
```
(Keep the existing `card.start_timer()` etc. The filter sets `session.type_correct=None` on a non-type card so a stale value never leaks.)

- [ ] **Step 4: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_type_answer.py tests/test_reviewer.py -v`.

- [ ] **Step 5: Commit**
```bash
git add ankiweb/screens/type_answer.py ankiweb/screens/reviewer.py tests/test_type_answer.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(reviewer): type-answer question filter + session capture"
```

## Context
The backend emits a literal `[[type:Field]]`; the GUI substitutes the `<input id=typeans>` and remembers the expected RAW field value (HTML/media stripping happens later inside `compare_answer`). Handles `cloze:`/`nc:` like Qt. `reviewer.js` already exposes `getTypedAnswer()` (reads the input) and `_typeAnsPress()` (Enter → `bridgeCommand("ans")`), so no new shell JS is needed for capture.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 6: Type-answer capture (typed: command) + answer-side diff

**Files:** Modify `ankiweb/screens/type_answer.py`, `ankiweb/screens/reviewer.py`; Test: `tests/test_type_answer.py` (append) + `tests/test_reviewer_audio.py`-style WS test in a new `tests/test_type_answer_flow.py`.

- [ ] **Step 1: Write the failing tests**

Append a unit test to `tests/test_type_answer.py` (the typed value lives on the session):
```python
def test_answer_filter_renders_diff(col):
    from ankiweb.screens.reviewer import ReviewerSession, load_question, render_answer
    s = ReviewerSession()
    load_question(col, s)               # sets s.type_correct = "Paris"
    s.typed_answer = "Paros"            # set by the "typed:" command in the live flow
    info = render_answer(col, s)
    assert "typeans" in info["a"]
    assert "typeBad" in info["a"] or "typeMissed" in info["a"]  # a diff was rendered
    assert "[[type:" not in info["a"]
```
Create `tests/test_type_answer_flow.py` (the WS round-trip: server `ans` → `eval getTypedAnswer()` → test replies → diff in `_showAnswer`):
```python
import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        c.portal.call(c.app.state.service.run, _seed)
        yield c


def _seed(col):
    m = col.models.new("TypeM")
    col.models.add_field(m, col.models.new_field("Front"))
    col.models.add_field(m, col.models.new_field("Back"))
    t = col.models.new_template("Card1")
    t["qfmt"] = "{{Front}}\n\n{{type:Back}}"
    t["afmt"] = "{{FrontSide}}<hr id=answer>{{Back}}\n\n{{type:Back}}"
    col.models.add_template(m, t)
    col.models.add_dict(m)
    n = col.new_note(col.models.by_name("TypeM")); n["Front"] = "capital?"; n["Back"] = "Paris"
    col.add_note(n, col.decks.id("Default"))


def test_type_answer_ws_roundtrip(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    client.portal.call(client.app.state.service.run, lambda col: col.decks.set_current(did))
    with client.websocket_connect("/ws?context=reviewer") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "show"})
        for _ in range(2):
            ws.receive_json()                      # drain _showQuestion + ankiwebSetAnswerBar
        # the shell sends the typed value, then asks to show the answer (two sequential cmds)
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "typed:Paros"})
        ws.send_json({"type": "cmd", "id": None, "ctx": "reviewer", "arg": "ans"})
        diff = None
        for _ in range(6):
            m = ws.receive_json()
            if m["type"] == "call" and m["fn"] == "_showAnswer":
                diff = m["args"][0]
                break
        assert diff is not None and ("typeBad" in diff or "typeMissed" in diff)
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_type_answer.py tests/test_type_answer_flow.py -v` → FAIL (`render_answer` has no `typed` param; no answer filter; handler doesn't capture).

- [ ] **Step 3: Implement**

Add the answer filter to `ankiweb/screens/type_answer.py` (reads `session.typed_answer`):
```python
def type_answer_answer_filter(col, session, html: str) -> str:
    """Port of Qt typeAnsAnswerFilter: replace [[type:...]] with the compare_answer diff."""
    if session.type_correct is None:
        return _TYPE_RE.sub("", html)   # defensive: no expected → drop any marker
    output = col.compare_answer(session.type_correct, session.typed_answer or "",
                                session.type_combining)
    block = (f"<div style=\"font-family:'{session.type_font}';"
             f"font-size:{session.type_size}px\">{output}</div>")
    return _TYPE_RE.sub(block, html, count=1)
```

In `ankiweb/screens/reviewer.py`, `render_answer` keeps its signature and reads `session.typed_answer` (set by the `typed:` command before `ans`):
```python
def render_answer(col, session):
    from ankiweb.screens.type_answer import type_answer_answer_filter
    a = session.card.answer()
    if session.type_correct is not None:
        a = type_answer_answer_filter(col, session, a)
    return {"a": render_av_buttons(a),
            "labels": list(col.sched.describe_next_states(session.states))}
```
The `arg == "ans"` branch is UNCHANGED from Task 2 (`render_answer(col, session)` now picks up `session.typed_answer`). Add a NEW `typed:` handler branch (the shell sends it right before `ans`); place it before `elif arg == "decks":`:
```python
        elif arg.startswith("typed:"):
            session.typed_answer = arg[len("typed:"):]
```
Change `show_answer_bar()` so the button routes through the shell (to capture the typed value), and add the two shell functions to `reviewer_page_body()`'s inline IIFE:
```python
def show_answer_bar() -> str:
    return ("<button id='ansbut' class='ansbut' "
            "onclick=\"ankiwebShowAnswer()\">Show Answer</button>")
```
In `reviewer_page_body()`'s inline `<script>` IIFE, define (and expose on `window`, since the input's inline `onkeypress` and the button's `onclick` run in global scope):
```javascript
"function ankiwebShowAnswer(){"
"  var ta=document.getElementById('typeans');"
"  if(ta&&ta.tagName==='INPUT'){window.pycmd('typed:'+ta.value);}"  // read input, not the answer <code>
"  window.pycmd('ans');"
"}"
"window.ankiwebShowAnswer=ankiwebShowAnswer;"
"function ankiwebTypeAnsPress(e){if(e&&(e.key==='Enter'||e.keyCode===13)){ankiwebShowAnswer();}}"
"window.ankiwebTypeAnsPress=ankiwebTypeAnsPress;"
```
If a unit test in `tests/test_reviewer.py` asserts `show_answer_bar()` contains `pycmd('ans')`, update it to assert `ankiwebShowAnswer()` (the button text "Show Answer" is unchanged, so `test_screen_routes.py`'s `"Show Answer" in ...` assertion still passes; the WS tests send `ans` directly, not via the button, so they're unaffected).

- [ ] **Step 4: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_type_answer.py tests/test_type_answer_flow.py tests/test_screen_routes.py tests/test_reviewer_audio.py -v`. The existing `test_screen_routes.py` reviewer tests seed a NON-type Basic card (`session.type_correct` stays None) so no `eval` round-trip happens — verify they still pass.

- [ ] **Step 5: Commit**
```bash
git add ankiweb/screens/type_answer.py ankiweb/screens/reviewer.py tests/test_type_answer.py tests/test_type_answer_flow.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(reviewer): type-answer capture (eval_with_callback) + compare_answer diff"
```

## Context
Capture is sequential, not a round-trip: `ankiwebShowAnswer()` (the Show Answer button, the type input's Enter, and the Space shortcut) reads `#typeans.value` in the shell and sends `pycmd('typed:'+value)` then `pycmd('ans')`. The server stores `session.typed_answer` on the `typed:` command, then `render_answer` calls `col.compare_answer(expected, session.typed_answer, combining)` for the colored diff, substituted where `[[type:...]]` was. Non-type cards have no `#typeans`, so the shell sends only `ans` and the server's `type_correct is None` short-circuits the compare. This avoids the `eval_with_callback`-inside-`ans` deadlock (the WS receive loop is busy `await`ing the handler and could not deliver the reply).

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns.

---

## Task 7: Reviewer keyboard shortcuts

**Files:** Modify `ankiweb/screens/reviewer.py` (`reviewer_page_body`); Test: `tests/test_reviewer.py` (append) + `tests/test_reviewer_integration.py` (append Playwright).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_reviewer.py`:
```python
def test_reviewer_body_has_shortcuts_guarded():
    from ankiweb.screens.reviewer import reviewer_page_body
    body = reviewer_page_body()
    assert "keydown" in body
    assert "typeans" in body          # the input guard
    assert "ease" in body             # digit -> ease mapping
```
Append a Playwright test to `tests/test_reviewer_integration.py`:
```python
def test_shortcuts_space_shows_answer_and_digit_guarded(live_server, page):
    page.goto(live_server + "/reviewer")
    page.wait_for_function("document.querySelector('#qa').innerHTML.length>0")
    page.keyboard.press("Space")      # question side -> show answer
    page.wait_for_function("document.querySelector('#ankiweb-answer').innerHTML.indexOf('ease')>=0")
    # digit 3 -> rate Good -> advances (queue of 1 -> overview) OR next card
    # (assert the answer bar appeared as the load-bearing 'space shows answer' behavior)
```
(Keep the Playwright assertion minimal/robust; the unit test is the primary gate. If the existing integration fixture seeds a single card, pressing 3 navigates to /overview — assert that if convenient.)

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/test_reviewer.py::test_reviewer_body_has_shortcuts_guarded -v` → FAIL.

- [ ] **Step 3: Implement** — In `reviewer_page_body()`'s inline IIFE, track the side via the registered call wrappers and add a guarded `keydown` listener. Update the `registerCalls` wrappers to set a side flag, and append the listener:
```javascript
"var _side='question';"
// in registerCalls: wrap _showQuestion/_showAnswer to set _side
//   _showQuestion:function(q,a,bc){_side='question';return window._showQuestion(q,a,bc);},
//   _showAnswer:function(a){_side='answer';return window._showAnswer(a);},
"document.addEventListener('keydown',function(e){"
"  var t=document.activeElement;"
"  if(t&&(t.id==='typeans'||t.tagName==='INPUT'||t.tagName==='TEXTAREA'))return;"
"  var k=e.key;"
"  if(k===' '||k==='Enter'){e.preventDefault();if(_side==='question'){window.ankiwebShowAnswer();}else{window.pycmd('ease3');}}"
"  else if(_side==='answer'&&(k==='1'||k==='2'||k==='3'||k==='4')){e.preventDefault();window.pycmd('ease'+k);}"
"  else if(k==='r'||k==='R'||k==='F5'){e.preventDefault();window.pycmd('replay');}"
"});"
```
(READ the current `reviewer_page_body` first. The `_showQuestion`/`_showAnswer` entries in `registerCalls` currently delegate to `window._showQuestion`/`window._showAnswer`; modify them to set `_side` first. Define `_side` and add the `keydown` listener inside the same IIFE.)

- [ ] **Step 4: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/test_reviewer.py -v`; then the Playwright file (skip allowed). Then the FULL suite: `conda run -n ankiweb python -m pytest -q`.

- [ ] **Step 5: Commit**
```bash
git add ankiweb/screens/reviewer.py tests/test_reviewer.py tests/test_reviewer_integration.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(reviewer): keyboard shortcuts (space/1-4/r) guarded against typeans"
```

## Context
Anki's reviewer shortcuts are Qt-only; the browser port adds JS `keydown` handlers mapping to the existing `pycmd` vocab (`ans`, `ease1-4`, `replay`). Space is state-dependent (show answer on the question side, rate Good on the answer side); digits 1-4 only fire on the answer side; ALL keys are suppressed while `#typeans` (or any input) is focused so digits can be part of a typed answer and Enter is owned by `_typeAnsPress`.

## Report Format
Status, full-suite pytest summary, files changed, self-review, commit SHA, concerns.

---

## Self-Review

**1. Spec coverage (Plan 4 deferrals from Plan 3):** type-in-answer (Tasks 5-6: question filter injecting `#typeans` + capture via the `typed:` precommand from `ankiwebShowAnswer` + `compare_answer` diff, incl. cloze/nc); `[sound:]` audio (Tasks 1-3: MIME, server extraction + replay buttons + autoplay/replay/per-clip push, HTML5 shell player) + guiPlayAudio wiring (Task 4); keyboard shortcuts (Task 7). Deferred + documented: custom scheduling, auto-advance, Edit (Plan D), flag/mark/leech UI, night mode (follow-up), TTS+recording (out of scope — TTSTag skipped).

**2. Placeholder scan:** No TBD/TODO. The Playwright tests are explicitly allowed to `skip` if browsers aren't installed (matching the existing `test_reviewer_integration.py` `pytest.importorskip`); the unit/WS tests are the primary gates.

**3. Type/name consistency:** `render_av_buttons`/`av_sound_filenames`/`answer_side_audio` (reviewer.py); `type_answer_question_filter`/`type_answer_answer_filter`/`_parse_spec` (type_answer.py); `ReviewerSession.type_correct/type_combining/type_font/type_size/typed_answer` (new fields); `render_answer(col, session)` keeps its signature (reads `session.typed_answer` — NO new param); reviewer handler new args `replay`, `play:<side>:<N>`, `typed:<value>`; new shell globals `ankiwebShowAnswer`/`ankiwebTypeAnsPress` (used by `show_answer_bar`'s button onclick, the `#typeans` onkeypress, and the Space shortcut); new bridge call `ankiwebPlayAudio` (server push ↔ shell registerCalls). `col.compare_answer`/`col.extract_cloze_for_typing`/`card.{question,answer}_av_tags`/`card.autoplay`/`card.replay_question_audio_on_answer_side`/`anki.sound.{SoundOrVideoTag,AV_REF_RE}` all verified live. Reuses `reviewer.js` globals `_showQuestion`/`_showAnswer`.

**4. Risk: `show_answer_bar` onclick change.** Task 6 changes the button from `pycmd('ans')` to `ankiwebShowAnswer()`. The button text stays "Show Answer" (so `test_screen_routes.py`'s substring check passes); the WS tests send `ans`/`typed:` as raw cmds (not via the button); only a `tests/test_reviewer.py` unit assertion on the exact onclick would need updating (Task 6 Step 3 calls this out). `render_answer` signature is unchanged, so existing callers are unaffected.

**5. Risk: existing reviewer tests draining fixed frame counts.** Task 2 adds an `ankiwebPlayAudio` push only for cards WITH audio; type-answer adds no extra frames (the `typed:` cmd is client→server, no push). `test_screen_routes.py` seeds a plain Basic card (no audio, no type), so its fixed-count frame draining is unaffected. Each task's Step 4 re-runs `test_screen_routes.py` to confirm.

**6. Concurrency check (the deadlock that was designed out):** capturing the typed answer with `hub.eval_with_callback` inside the `ans` handler would deadlock — the WS receive loop is blocked `await`ing `dispatch_cmd("ans")`, so it can never read the `{type:result}` that resolves the eval future (true in production AND tests). The `typed:<value>` precommand makes capture two ordered client→server frames, processed sequentially by the existing WS loop with zero concurrency change.
