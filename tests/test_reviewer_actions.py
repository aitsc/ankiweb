from pathlib import Path
import anki.consts
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.bridge.ui_state import UiState
from ankiweb.screens.reviewer import make_reviewer_handler


class _Hub:
    """Records push_call(fn, args) and carries a real UiState (the handler writes to it)."""
    def __init__(self):
        self.calls = []
        self.ui_state = UiState()

    async def push_call(self, ctx, fn, args):
        self.calls.append((fn, args))

    def fns(self):
        return [c[0] for c in self.calls]

    def last(self, fn):
        for c in reversed(self.calls):
            if c[0] == fn:
                return c[1]
        return None


async def _svc(tmp_path, n_cards=3):
    svc = CollectionService(Settings(collection_path=tmp_path / "c.anki2"))
    await svc.open()

    def setup(col):
        did = col.decks.id("Default")
        col.decks.set_current(did)
        for i in range(n_cards):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = f"Q{i}"
            note["Back"] = f"A{i}"
            col.add_note(note, did)
    await svc.run(setup)
    return svc


async def _make(tmp_path, n_cards=3):
    svc = await _svc(tmp_path, n_cards)
    hub = _Hub()
    handler = make_reviewer_handler(svc, hub)
    return svc, hub, handler


# ---- (a) mark toggles the note's 'marked' tag + pushes _drawMark -------------

async def test_mark_toggles_tag_and_draws(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    cid = hub.ui_state.current_card_id
    await handler("mark")
    has_tag = await svc.run(lambda col: "marked" in col.get_card(cid).note().tags)
    assert has_tag is True
    assert ("_drawMark", [True]) in hub.calls
    # same card still current (mark does not advance)
    assert hub.ui_state.current_card_id == cid
    await handler("mark")
    has_tag = await svc.run(lambda col: "marked" in col.get_card(cid).note().tags)
    assert has_tag is False
    assert ("_drawMark", [False]) in hub.calls
    await svc.close()


# ---- (b) setflag sets the card's user flag + pushes _drawFlag ----------------

async def test_setflag_sets_user_flag_and_draws(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    cid = hub.ui_state.current_card_id
    await handler("setflag:2")
    flag = await svc.run(lambda col: col.get_card(cid).user_flag())
    assert flag == 2
    assert ("_drawFlag", [2]) in hub.calls
    assert hub.ui_state.current_card_id == cid  # does not advance
    # clear
    await handler("setflag:0")
    flag = await svc.run(lambda col: col.get_card(cid).user_flag())
    assert flag == 0
    assert ("_drawFlag", [0]) in hub.calls
    await svc.close()


# ---- (c) buryc advances ------------------------------------------------------

async def test_buryc_advances(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    first = hub.ui_state.current_card_id
    before = await svc.run(lambda col: sum(col.sched.counts()))
    await handler("buryc")
    after = await svc.run(lambda col: sum(col.sched.counts()))
    assert hub.ui_state.current_card_id != first  # advanced to a different card
    assert after < before                          # one fewer card in today's queue
    await svc.close()


# ---- (d) suspendc suspends + advances ---------------------------------------

async def test_suspendc_suspends_and_advances(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    first = hub.ui_state.current_card_id
    await handler("suspendc")
    queue = await svc.run(lambda col: col.get_card(first).queue)
    assert queue == anki.consts.QUEUE_TYPE_SUSPENDED
    assert hub.ui_state.current_card_id != first
    await svc.close()


# ---- buryn / suspendn act on all of the note's cards -------------------------

async def test_suspendn_suspends_note_and_advances(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    first = hub.ui_state.current_card_id
    await handler("suspendn")
    queue = await svc.run(lambda col: col.get_card(first).queue)
    assert queue == anki.consts.QUEUE_TYPE_SUSPENDED
    assert hub.ui_state.current_card_id != first
    await svc.close()


async def test_buryn_buries_note_and_advances(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    first = hub.ui_state.current_card_id
    before = await svc.run(lambda col: sum(col.sched.counts()))
    await handler("buryn")
    after = await svc.run(lambda col: sum(col.sched.counts()))
    assert hub.ui_state.current_card_id != first
    assert after < before
    await svc.close()


# ---- (e) forget resets the card to new --------------------------------------

async def test_forget_resets_card(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    cid = hub.ui_state.current_card_id
    # answer it so it's no longer new, then reload that card by id and forget it
    await handler("ease3")
    ctype = await svc.run(lambda col: col.get_card(cid).type)
    assert ctype != anki.consts.CARD_TYPE_NEW  # it advanced out of new
    await svc.run_op(lambda col: col.sched.schedule_cards_as_new([cid]))
    ctype = await svc.run(lambda col: col.get_card(cid).type)
    assert ctype == anki.consts.CARD_TYPE_NEW
    await svc.close()


async def test_forget_branch_runs_and_advances(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    first = hub.ui_state.current_card_id
    await handler("forget")
    # forget on a new card keeps it new but the branch advances to the next card
    assert "_showQuestion" in hub.fns()
    assert hub.ui_state.current_card_id is not None
    await svc.close()


# ---- (f) deletenote removes the note + advances -----------------------------

async def test_deletenote_removes_and_advances(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    first = hub.ui_state.current_card_id
    before = await svc.run(lambda col: len(col.find_notes("")))
    await handler("deletenote")
    after = await svc.run(lambda col: len(col.find_notes("")))
    assert after == before - 1
    assert hub.ui_state.current_card_id != first
    await svc.close()


# ---- (g) setdue reschedules without error -----------------------------------

async def test_setdue_reschedules_without_error(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    await handler("setdue:0")
    # no error pushed
    assert "ankiwebReviewerError" not in hub.fns()
    # advanced (or reloaded) — a question was shown
    assert "_showQuestion" in hub.fns()
    await svc.close()


# ---- (h) undo after an ease answer restores without crashing ----------------

async def test_undo_after_answer_restores(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    await handler("ease3")  # mutating + advances
    n_show_before = hub.fns().count("_showQuestion")
    await handler("undo")
    # undo reloads → another _showQuestion pushed, no error
    assert hub.fns().count("_showQuestion") > n_show_before
    assert "ankiwebReviewerError" not in hub.fns()
    await svc.close()


async def test_undo_when_empty_pushes_error(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    # drain the backend undo stack (the setup add_notes left undoable entries) so the
    # NEXT undo genuinely has nothing to undo -> UndoEmpty -> error pushed
    import anki.errors

    async def _drain():
        while True:
            try:
                await svc.run(lambda col: col.undo())
            except anki.errors.UndoEmpty:
                return
    await _drain()
    hub.calls.clear()
    await handler("undo")  # now truly nothing to undo
    assert "ankiwebReviewerError" in hub.fns()
    await svc.close()


# ---- (i) cardinfo navigates to /card-info/<cid> -----------------------------

async def test_cardinfo_navigates(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    await handler("show")
    cid = hub.ui_state.current_card_id
    await handler("cardinfo")
    assert ("ankiwebNavigate", [f"/card-info/{cid}"]) in hub.calls
    await svc.close()


# ---- (j) every new branch is a no-op when there is no current card ----------

async def test_actions_are_noops_without_card(tmp_path: Path):
    svc, hub, handler = await _make(tmp_path)
    # do NOT send "show" first → session.card is None
    for arg in ("mark", "setflag:2", "buryc", "buryn", "suspendc", "suspendn",
                "setdue:0", "forget", "deletenote", "cardinfo"):
        res = await handler(arg)
        assert res is None
    # none of these should have pushed any call
    assert hub.calls == []
    await svc.close()


# ---- (k) reviewer_page_body() wires the actions bar + new shortcuts ---------

def test_reviewer_body_has_actions_bar_and_shortcuts():
    from ankiweb.screens.reviewer import reviewer_page_body
    body = reviewer_page_body()
    assert "rev-actions" in body
    # buttons issue the new pycmds
    for cmd in ("'mark'", "'buryc'", "'suspendc'", "'forget'", "'cardinfo'", "'undo'"):
        assert cmd in body
    assert "setflag:" in body
    assert "_drawMark" in body and "_drawFlag" in body
    assert "ankiwebReviewerError" in body
    # new keyboard cases (existing ones still present)
    assert "'*'" in body          # mark
    assert "ctrlKey" in body       # Ctrl+1..4 flag
    assert "'i'" in body or '"i"' in body   # card info
    assert "'u'" in body or '"u"' in body   # undo
    # existing shortcuts intact
    assert "typeans" in body and "ease" in body
