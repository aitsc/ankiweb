# ankiweb Follow-up — Security/Cleanup: remove /spike/* + WS malformed-frame hardening

> **For agentic workers:** small follow-up; executed inline with TDD. Steps use checkbox (`- [ ]`) syntax.

**Goal:** (1) Remove the development-only `/spike/*` debug routes (and the file + test they reference) before public exposure; (2) harden the `/ws` receive loop so a malformed frame (bad JSON, non-object, missing fields) cannot drop the connection.

**Why:** `/spike/reviewer` + `/spike/push_question` were spike scaffolding to prove reviewer.js renders — now superseded by the real study-loop Playwright test (`tests/test_reviewer_integration.py`). They expose an unauthenticated "render arbitrary first card / push to any reviewer" surface; remove them. The WS loop currently lets `receive_json()` on bad JSON, `msg.get()` on a non-dict, or `msg["id"]` on a result frame propagate → the socket drops; harden it to skip malformed frames and keep the session alive.

**Tech Stack:** Python 3.12 (conda env `ankiweb`), FastAPI, the existing `ankiweb/app.py` + `ankiweb/bridge/ws.py`. Run via `conda run -n ankiweb ...`.

---

## Task 1: remove the /spike/* routes

**Files:** Modify `ankiweb/app.py`; delete `ankiweb/shell/reviewer_spike.html`, `tests/test_bridge_spike.py`; Test `tests/test_no_spike_routes.py`.

- [ ] **Step 1 — failing test** `tests/test_no_spike_routes.py`:
```python
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_spike_reviewer_route_gone(client):
    # GET /spike/reviewer must no longer serve the spike page (it 404s via the media catch-all)
    r = client.get("/spike/reviewer")
    assert r.status_code == 404


def test_spike_push_question_route_gone(client):
    r = client.post("/spike/push_question")
    assert r.status_code in (404, 405)
```

- [ ] **Step 2** — run → FAIL (the spike page currently 200s).
- [ ] **Step 3** — in `ankiweb/app.py`, delete the `@app.get("/spike/reviewer")` block and the `@app.post("/spike/push_question")` block (the two functions `spike_page`/`spike_push`). Leave the `/shell/static` mount + `/healthz` intact.
- [ ] **Step 4** — `git rm ankiweb/shell/reviewer_spike.html tests/test_bridge_spike.py` (its coverage is superseded by `tests/test_reviewer_integration.py`).
- [ ] **Step 5** — run `conda run -n ankiweb python -m pytest tests/test_no_spike_routes.py -v` → PASS; regression `conda run -n ankiweb python -m pytest tests/test_screen_routes.py tests/test_media_serving.py -q`.
- [ ] **Step 6** — commit.

## Task 2: WS malformed-frame hardening

**Files:** Modify `ankiweb/bridge/ws.py`; Test `tests/test_ws_hardening.py`.

- [ ] **Step 1 — failing test** `tests/test_ws_hardening.py`:
```python
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_bad_json_then_valid_cmd_survives(client):
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_text("this is not json{{{")          # malformed → must be skipped, not fatal
        # the socket is still alive: a valid cmd with an id still gets a result
        ws.send_json({"type": "cmd", "id": 1, "ctx": "deckbrowser", "arg": "noop:"})
        m = ws.receive_json()
        while m.get("type") != "result":
            m = ws.receive_json()
        assert m["id"] == 1


def test_non_object_frame_skipped(client):
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json([1, 2, 3])                        # JSON array, not an object
        ws.send_json({"type": "cmd", "id": 2, "ctx": "deckbrowser", "arg": "noop:"})
        m = ws.receive_json()
        while m.get("type") != "result":
            m = ws.receive_json()
        assert m["id"] == 2


def test_result_frame_missing_id_skipped(client):
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "result", "value": "x"})  # no 'id' → must not KeyError/drop
        ws.send_json({"type": "cmd", "id": 3, "ctx": "deckbrowser", "arg": "noop:"})
        m = ws.receive_json()
        while m.get("type") != "result":
            m = ws.receive_json()
        assert m["id"] == 3
```
(NOTE: `noop:` is an unknown deckbrowser cmd — the handler ignores it and returns None; the `id` still yields a `result` frame, proving the socket survived the malformed frame. If the deckbrowser handler errors on an unknown cmd, use a known no-effect cmd instead; the load-bearing assertion is that a valid cmd after a malformed frame still returns its result.)

- [ ] **Step 2** — run → FAIL (bad JSON drops the connection → `receive_json` raises).
- [ ] **Step 3** — in `ankiweb/bridge/ws.py`, harden the loop:
```python
        from fastapi import WebSocketDisconnect
        try:
            while True:
                try:
                    msg = await websocket.receive_json()
                except WebSocketDisconnect:
                    raise
                except Exception:
                    continue  # malformed JSON frame — skip, keep the socket alive
                if not isinstance(msg, dict):
                    continue
                mtype = msg.get("type")
                if mtype == "cmd":
                    try:
                        result = await hub.dispatch_cmd(context, msg.get("arg", ""))
                    except Exception:
                        result = None  # a handler error must not drop the session
                    if msg.get("id") is not None:
                        await websocket.send_json(
                            {"type": "result", "id": msg["id"], "value": result})
                elif mtype == "result":
                    mid = msg.get("id")
                    if mid is not None:
                        hub.resolve(mid, msg.get("value"))
                elif mtype == "ready":
                    pass
        except WebSocketDisconnect:
            pass
        finally:
            hub.unregister(context, websocket)
```
(Keep the existing host-guard + accept + register prologue. The key changes: wrap `receive_json` to skip bad-JSON frames; guard non-dict; guard `dispatch_cmd` so a handler error doesn't drop the socket; `result` frame missing `id` is skipped.)

- [ ] **Step 4** — run `conda run -n ankiweb python -m pytest tests/test_ws_hardening.py -v` → PASS; regression `conda run -n ankiweb python -m pytest tests/ -q -k "ws or bridge or reviewer or deckbrowser or browser"`.
- [ ] **Step 5** — full suite + commit.
