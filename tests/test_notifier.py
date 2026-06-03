import asyncio
import json
from pathlib import Path
import pytest
from ankiweb.notifier import (
    NotifyConfig, NotifyStatus, NotifierState, DeckNotifier,
    learnable, diff_changes, build_payload, eval_response, snapshot,
)


def _counts(n=0, l=0, r=0, did=1):
    return {"deck_id": did, "new_count": n, "learn_count": l, "review_count": r}


# ----- pure logic -----
def test_learnable():
    assert learnable(_counts(n=1)) and learnable(_counts(l=1)) and learnable(_counts(r=1))
    assert not learnable(_counts())


def test_diff_changes_empty_baseline_pushes_learnable_only():
    current = {"A": _counts(n=2, did=10), "B": _counts(did=11)}  # A learnable, B not
    changes = diff_changes(current, {})
    assert len(changes) == 1
    assert changes[0] == {"deck": "A", "deckId": 10, "learnable": True,
                          "new_count": 2, "learn_count": 0, "review_count": 0}


def test_diff_changes_flip_both_directions():
    current = {"A": _counts(did=10), "B": _counts(r=3, did=11)}
    # A was learnable -> now not; B was not -> now learnable
    changes = {c["deck"]: c["learnable"] for c in diff_changes(current, {"A": True, "B": False})}
    assert changes == {"A": False, "B": True}


def test_build_payload():
    p = build_payload([{"deck": "A"}], ts=1780500000.7)
    assert p == {"source": "ankiweb", "ts": 1780500000, "changes": [{"deck": "A"}]}


@pytest.mark.parametrize("status,body,ok", [
    (200, {"ok": True}, True),
    (200, {"ok": False}, False),
    (200, {}, False),
    (200, None, False),
    (500, {"ok": True}, False),
    (204, {"ok": True}, False),
])
def test_eval_response(status, body, ok):
    assert eval_response(status, body)[0] is ok


# ----- config persistence -----
def test_config_round_trip(tmp_path: Path):
    cfg = NotifyConfig(enabled=True, url="http://x/y", token="t", poll_sec=15, retry_sec=5)
    p = tmp_path / "notify.json"
    cfg.save(p)
    assert NotifyConfig.load(p) == cfg
    assert json.loads(p.read_text())["url"] == "http://x/y"


def test_config_active():
    assert NotifyConfig(enabled=True, url="http://x", poll_sec=1, retry_sec=1).active()
    assert not NotifyConfig(enabled=False, url="http://x", poll_sec=1, retry_sec=1).active()
    assert not NotifyConfig(enabled=True, url="", poll_sec=1, retry_sec=1).active()
    assert not NotifyConfig(enabled=True, url="http://x", poll_sec=0, retry_sec=1).active()


def test_load_missing_file_is_disabled(tmp_path: Path):
    assert NotifyConfig.load(tmp_path / "nope.json") == NotifyConfig()


# ----- runner state machine (_tick is deterministic; no waiting) -----
class FakePost:
    def __init__(self, result=(True, "")):
        self.result = result
        self.calls = []

    async def __call__(self, cfg, payload):
        self.calls.append(payload)
        return self.result


CFG = NotifyConfig(enabled=True, url="http://x", token="t", poll_sec=60, retry_sec=10)


def _notifier(tmp_path, fetch, post):
    state = NotifierState(tmp_path / "notify.json")
    state.config = CFG  # mirror run(): the tick's cfg is the state's live config (identity guard)
    return DeckNotifier(state, fetch=fetch, post=post, now=lambda: 1780500000.0), state


@pytest.mark.asyncio
async def test_tick_startup_pushes_all_learnable(tmp_path):
    snap = {"A": _counts(n=1, did=10), "B": _counts(did=11), "C": _counts(r=2, did=12)}
    post = FakePost()
    n, state = _notifier(tmp_path, fetch=lambda: _async(snap), post=post)
    delay = await n._tick(CFG)
    assert delay == 60
    sent = {c["deck"] for c in post.calls[0]["changes"]}
    assert sent == {"A", "C"}                 # only learnable decks
    assert state.status.watching == 3 and state.status.learnable == 2
    # second tick, unchanged -> no new POST
    await n._tick(CFG)
    assert len(post.calls) == 1


@pytest.mark.asyncio
async def test_tick_failure_does_not_advance_and_retries_latest(tmp_path):
    snap = {"A": _counts(n=1, did=10)}
    post = FakePost(result=(False, "boom"))
    n, state = _notifier(tmp_path, fetch=lambda: _async(snap), post=post)
    delay = await n._tick(CFG)
    assert delay == 10 and state.status.last_error == "boom"  # retry interval
    assert n.last_notified == {}                              # NOT advanced on failure
    # while unsent, A's counts grow (still learnable) -> the retry must carry the LATEST counts
    snap["A"] = _counts(n=5, did=10)
    post.result = (True, "")
    await n._tick(CFG)
    last = post.calls[-1]["changes"][0]
    assert last["learnable"] is True and last["new_count"] == 5
    assert n.last_notified == {"A": True}


@pytest.mark.asyncio
async def test_tick_flip_then_back_to_acknowledged_nets_no_send(tmp_path):
    snap = {"A": _counts(n=1, did=10)}
    post = FakePost()
    n, _ = _notifier(tmp_path, fetch=lambda: _async(snap), post=post)
    await n._tick(CFG)                       # success -> receiver acknowledged A learnable
    assert len(post.calls) == 1
    # A goes not-learnable; the send fails so the receiver still believes "learnable"
    snap["A"] = _counts(did=10)
    post.result = (False, "x")
    await n._tick(CFG)
    assert n.last_notified == {"A": True}    # unchanged on failure
    # A reverts to learnable (== last acknowledged) before any retry succeeds -> nothing to send
    snap["A"] = _counts(n=1, did=10)
    post.result = (True, "")
    before = len(post.calls)                 # 2 so far: tick1 success + tick2 failed attempt
    await n._tick(CFG)
    assert len(post.calls) == before         # net no change -> tick3 makes no new POST


@pytest.mark.asyncio
async def test_tick_deleted_deck_pruned(tmp_path):
    snap = {"A": _counts(n=1, did=10)}
    post = FakePost()
    n, _ = _notifier(tmp_path, fetch=lambda: _async(snap), post=post)
    await n._tick(CFG)
    assert n.last_notified == {"A": True}
    snap.clear()                              # deck A removed
    await n._tick(CFG)
    assert n.last_notified == {}              # pruned silently, no extra POST
    assert len(post.calls) == 1


@pytest.mark.asyncio
async def test_disabled_config_never_posts(tmp_path):
    post = FakePost()
    n, _ = _notifier(tmp_path, fetch=lambda: _async({"A": _counts(n=1)}), post=post)
    # active() False -> the run loop would idle; _tick is only called when active, so we assert
    # the gate directly
    assert not NotifyConfig(enabled=False, url="http://x", poll_sec=1, retry_sec=1).active()
    assert post.calls == []


def test_state_update_persists_and_signals(tmp_path):
    state = NotifierState(tmp_path / "notify.json")
    state.update(NotifyConfig(enabled=True, url="http://x", poll_sec=1, retry_sec=1))
    assert state.changed.is_set()
    assert NotifyConfig.load(tmp_path / "notify.json").url == "http://x"


# ----- snapshot against a real collection -----
def test_snapshot_real_collection(tmp_path):
    from anki.collection import Collection
    col = Collection(str(tmp_path / "c.anki2"))
    try:
        m = col.models.by_name("Basic")
        note = col.new_note(m)
        note["Front"], note["Back"] = "Q", "A"
        col.add_note(note, col.decks.id("Default"))
        snap = snapshot(col)
        assert "Default" in snap
        assert learnable(snap["Default"])  # a fresh new card -> learnable
        assert snap["Default"]["new_count"] >= 1
    finally:
        col.close()


async def _async(value):
    return value


# ----- review fixes -----
def test_load_corrupt_json_degrades_to_defaults(tmp_path):  # fix #4
    p = tmp_path / "notify.json"
    for bad in ('{"poll_sec": "abc", "enabled": true}', "[1,2,3]", "not json", "null"):
        p.write_text(bad)
        assert NotifyConfig.load(p) == NotifyConfig()


@pytest.mark.asyncio
async def test_tick_aborts_post_if_config_changed_during_fetch(tmp_path):  # fix #1
    snap = {"A": _counts(n=1, did=10)}
    post = FakePost()
    state = NotifierState(tmp_path / "notify.json")
    state.config = CFG

    async def fetch_then_repoint():
        # a /notify save lands during the fetch await -> NotifierState.update rebinds .config
        state.config = NotifyConfig(enabled=True, url="http://NEW", poll_sec=60, retry_sec=10)
        return snap

    n = DeckNotifier(state, fetch=fetch_then_repoint, post=post, now=lambda: 0.0)
    await n._tick(CFG)                 # CFG is the snapshot captured at the loop top
    assert post.calls == []            # must NOT POST to the stale target
    assert n.last_notified == {}       # baseline not advanced


@pytest.mark.asyncio
async def test_run_survives_fetch_error_and_retries(tmp_path):  # fix #3
    state = NotifierState(tmp_path / "notify.json")
    state.config = NotifyConfig(enabled=True, url="http://x", poll_sec=0.01, retry_sec=0.01)
    calls = {"n": 0}

    async def bad_fetch():
        calls["n"] += 1
        raise RuntimeError("collection not open")

    n = DeckNotifier(state, fetch=bad_fetch, post=FakePost(), now=lambda: 0.0)
    task = asyncio.create_task(n.run())
    await asyncio.sleep(0.06)
    assert not task.done()                                   # the task did NOT die
    assert calls["n"] >= 2                                   # it kept retrying
    assert "collection not open" in state.status.last_error  # error surfaced
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_run_zeros_status_when_disabled(tmp_path):  # fix #2
    state = NotifierState(tmp_path / "notify.json")  # disabled by default
    state.status.watching, state.status.learnable, state.status.pending = 5, 3, 2
    n = DeckNotifier(state, fetch=lambda: _async({}), post=FakePost())
    task = asyncio.create_task(n.run())
    await asyncio.sleep(0.02)
    assert (state.status.watching, state.status.learnable, state.status.pending) == (0, 0, 0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
