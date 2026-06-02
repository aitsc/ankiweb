# ankiweb Follow-up — AnkiConnect Statistics actions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add AnkiConnect's 8 statistics / review-history actions — `getNumCardsReviewedToday`, `getNumCardsReviewedByDay`, `getCollectionStatsHTML`, `cardReviews`, `getReviewsOfCards`, `getLatestReviewID`, `insertReviews`, `getDeckStats` — replicating each contract faithfully (exact params, SQL, return shapes/column order).

**Architecture:** One new `ankiweb/ankiconnect/actions/stats.py` (registered in `actions/__init__.py`). Reads use `rt.service.run(fn)` over `col.db`/`col.sched`/`col.stats()`; the lone write `insertReviews` uses `rt.service.run` + `col.save()`. Faithful to AnkiConnect's HTTP contract (B1–B4 consistency); deck-name→id via `col.decks.id` (AnkiConnect's create-if-missing behavior).

**Tech Stack:** Python 3.12 (conda env `ankiweb`), `anki==25.9.4`, the AnkiConnect action registry (`@action`, `rt.service.run`), `col.db` (DBProxy), `col.sched.day_cutoff`, `col.stats()`, pytest. Run via `conda run -n ankiweb ...`.

**Grounded facts (live-probed):**
- `col.sched.day_cutoff` (v3; `dayCutoff` is a deprecated alias) = the Unix-seconds end of today's Anki day (probed 1780430400). Use `day_cutoff` (no deprecation warning).
- `col.db.scalar(sql, *args)` / `col.db.all(sql, *args)` / `col.db.execute(sql, *args)` / `col.db.executemany(sql, seq)` all work headless. `revlog` columns: `id, cid, usn, ease, ivl, lastIvl, factor, time, type` (probed via `db.all`). `revlog.id` is epoch-ms.
- `col.stats()` → a `CollectionStats` with `.report()` — **works headless** (probed: a 14528-char HTML string). It has a legacy `.wholeCollection` attribute (set it like AnkiConnect; guard with try/except).
- `col.sched.deck_due_tree()` → a node tree; each node has `deck_id`, `name`, `new_count`, `learn_count`, `review_count`, `total_in_deck` (probed). `col.decks.id(name)` resolves (creates-if-missing).
- The action pattern (`ankiweb/ankiconnect/`): `@action("name")` from `registry`; `async def fn(rt, **params)`; `rt.service.run(fn)` runs `fn(col)` on the executor. Modules register via `actions/__init__.py` imports. Tests: `create_ankiconnect_app(Settings(...))` + `_call(client, action, **params)` → `{"action","version":6,"params"}`, returns `result`. `addNote`/`findCards` exist. **JSON note:** a dict with int keys (e.g. `getReviewsOfCards`/`getDeckStats`) serializes with STRING keys over HTTP — tests must index with `str(id)`.

---

## File Structure

| File | Responsibility |
|---|---|
| `ankiweb/ankiconnect/actions/stats.py` (create) | the 8 statistics actions |
| `ankiweb/ankiconnect/actions/__init__.py` (modify) | import `stats` so its actions register |
| `tests/ankiconnect/test_stats_actions.py` (create) | per-action contract tests (inject a revlog row via `insertReviews`, then exercise the reads) |

---

## Task 1: the 8 statistics actions

**Files:** Create `ankiweb/ankiconnect/actions/stats.py`; modify `ankiweb/ankiconnect/actions/__init__.py`; Test `tests/ankiconnect/test_stats_actions.py`.

- [ ] **Step 1: Write the failing tests** — `tests/ankiconnect/test_stats_actions.py`:
```python
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.ankiconnect.app import create_ankiconnect_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_ankiconnect_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def _call(client, action, **params):
    r = client.post("/", json={"action": action, "version": 6, "params": params})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None, body["error"]
    return body["result"]


def _seed_card(client):
    nid = _call(client, "addNote", note={"deckName": "Default", "modelName": "Basic",
                "fields": {"Front": "q", "Back": "a"}})
    return _call(client, "findCards", query=f"nid:{nid}")[0]


def _revlog_row(cid):
    # id, cid, usn, ease, ivl, lastIvl, factor, time, type
    return [int(time.time() * 1000), cid, -1, 3, 10, 5, 2500, 18000, 1]


def test_insert_reviews_and_latest_and_today(client):
    cid = _seed_card(client)
    assert _call(client, "getLatestReviewID", deck="Default") == 0   # no reviews yet
    row = _revlog_row(cid)
    _call(client, "insertReviews", reviews=[row])
    assert _call(client, "getLatestReviewID", deck="Default") == row[0]
    assert _call(client, "getNumCardsReviewedToday") >= 1


def test_card_reviews(client):
    cid = _seed_card(client)
    row = _revlog_row(cid)
    _call(client, "insertReviews", reviews=[row])
    rows = _call(client, "cardReviews", deck="Default", startID=0)
    assert any(r[0] == row[0] and r[1] == cid for r in rows)   # id, cid, … (9 cols)
    assert len(rows[0]) == 9


def test_get_reviews_of_cards(client):
    cid = _seed_card(client)
    row = _revlog_row(cid)
    _call(client, "insertReviews", reviews=[row])
    res = _call(client, "getReviewsOfCards", cards=[cid])
    revs = res[str(cid)]                                       # JSON int key → str
    assert revs and revs[0]["id"] == row[0] and revs[0]["ease"] == 3
    assert set(revs[0].keys()) == {"id", "usn", "ease", "ivl", "lastIvl", "factor", "time", "type"}


def test_reviewed_by_day(client):
    cid = _seed_card(client)
    _call(client, "insertReviews", reviews=[_revlog_row(cid)])
    by_day = _call(client, "getNumCardsReviewedByDay")
    assert isinstance(by_day, list) and by_day and len(by_day[0]) == 2   # [day_str, count]
    assert isinstance(by_day[0][0], str) and by_day[0][1] >= 1


def test_collection_stats_html(client):
    html = _call(client, "getCollectionStatsHTML")
    assert isinstance(html, str) and len(html) > 0


def test_deck_stats(client):
    _seed_card(client)
    res = _call(client, "getDeckStats", decks=["Default"])
    # outer keys are deck ids (str over JSON); find the Default one
    entry = next(v for v in res.values() if v["name"] == "Default")
    assert {"deck_id", "name", "new_count", "learn_count", "review_count"} <= set(entry)
```

- [ ] **Step 2: Run to verify failure** — `conda run -n ankiweb python -m pytest tests/ankiconnect/test_stats_actions.py -v` → FAIL (actions unregistered).

- [ ] **Step 3: Create `ankiweb/ankiconnect/actions/stats.py`**:
```python
from __future__ import annotations
import time
from ankiweb.ankiconnect.registry import action

_REVLOG_COLS = "id, cid, usn, ease, ivl, lastIvl, factor, time, type"


@action("getNumCardsReviewedToday")
async def get_num_cards_reviewed_today(rt):
    def fn(col):
        return col.db.scalar("select count() from revlog where id > ?",
                             (col.sched.day_cutoff - 86400) * 1000)
    return await rt.service.run(fn)


@action("getNumCardsReviewedByDay")
async def get_num_cards_reviewed_by_day(rt):
    def fn(col):
        offset = int(time.strftime("%H", time.localtime(col.sched.day_cutoff))) * 3600
        return col.db.all(
            'select date(id/1000 - ?, "unixepoch", "localtime") as day, count() '
            "from revlog group by day order by day desc", offset)
    return await rt.service.run(fn)


@action("getCollectionStatsHTML")
async def get_collection_stats_html(rt, wholeCollection=True):
    def fn(col):
        stats = col.stats()
        try:
            stats.wholeCollection = wholeCollection
        except Exception:
            pass
        return stats.report()
    return await rt.service.run(fn)


@action("cardReviews")
async def card_reviews(rt, deck=None, startID=0):
    def fn(col):
        return col.db.all(
            f"select {_REVLOG_COLS} from revlog "
            "where id > ? and cid in (select id from cards where did = ?)",
            startID, col.decks.id(deck))
    return await rt.service.run(fn)


@action("getReviewsOfCards")
async def get_reviews_of_cards(rt, cards=None):
    cards = [int(c) for c in (cards or [])]
    cols = ["cid", "id", "usn", "ease", "ivl", "lastIvl", "factor", "time", "type"]

    def fn(col):
        cid_to_reviews = {}
        for i in range(0, len(cards), 999):   # sqlite var limit
            batch = cards[i:i + 999]
            ph = ",".join("?" * len(batch))
            for rev in col.db.all(
                    "select {} from revlog where cid in ({})".format(", ".join(cols), ph), *batch):
                cid_to_reviews.setdefault(rev[0], []).append(rev[1:])
        return {c: [dict(zip(cols[1:], rev)) for rev in cid_to_reviews.get(c, [])] for c in cards}
    return await rt.service.run(fn)


@action("getLatestReviewID")
async def get_latest_review_id(rt, deck=None):
    def fn(col):
        return col.db.scalar(
            "select max(id) from revlog where cid in (select id from cards where did = ?)",
            col.decks.id(deck)) or 0
    return await rt.service.run(fn)


@action("insertReviews")
async def insert_reviews(rt, reviews=None):
    rows = [tuple(r) for r in (reviews or [])]

    def fn(col):
        if rows:
            col.db.executemany(
                f"insert into revlog({_REVLOG_COLS}) values (?,?,?,?,?,?,?,?,?)", rows)
            col.save()
        return None
    return await rt.service.run(fn)


def _collect_deck_tree(node, out):
    out[node.deck_id] = node
    for child in node.children:
        _collect_deck_tree(child, out)


def _deck_stats_json(node):
    d = {"deck_id": node.deck_id, "name": node.name, "new_count": node.new_count,
         "learn_count": node.learn_count, "review_count": node.review_count}
    if hasattr(node, "total_in_deck"):
        d["total_in_deck"] = node.total_in_deck
    return d


@action("getDeckStats")
async def get_deck_stats(rt, decks=None):
    names = list(decks or [])

    def fn(col):
        deck_ids = [col.decks.id(d) for d in names]
        nodes = {}
        _collect_deck_tree(col.sched.deck_due_tree(), nodes)
        return {did: _deck_stats_json(node) for did, node in nodes.items() if did in deck_ids}
    return await rt.service.run(fn)
```
(NOTE: `cardReviews`/`getReviewsOfCards` use an f-string only for the FIXED column-name constant `_REVLOG_COLS`/`cols` (no user input) + parameterized `?` placeholders for all values — no SQL injection. `insertReviews` uses parameterized `executemany` (safer than AnkiConnect's string-concat, identical effect) + `col.save()` to persist the raw revlog write. `col.db.all` returns lists; `cardReviews` returns 9-col rows; `getReviewsOfCards` returns `{cid: [dict,…]}`.)

- [ ] **Step 4: Register the module** — in `ankiweb/ankiconnect/actions/__init__.py`, add `stats` to the import line:
```python
from ankiweb.ankiconnect.actions import meta, decks, notes, cards, models, media, gui, import_export, stats  # noqa: F401
```

- [ ] **Step 5: Run to verify pass** — `conda run -n ankiweb python -m pytest tests/ankiconnect/test_stats_actions.py -v`, then regression: `conda run -n ankiweb python -m pytest tests/ankiconnect/ -q`.

- [ ] **Step 6: Commit**
```bash
git add ankiweb/ankiconnect/actions/stats.py ankiweb/ankiconnect/actions/__init__.py tests/ankiconnect/test_stats_actions.py
git -c user.name="tsc" -c user.email="xxj.tan@gmail.com" commit -m "feat(ankiconnect): statistics actions (cardReviews/getReviewsOfCards/getNumCardsReviewed*/getCollectionStatsHTML/insertReviews/getLatestReviewID/getDeckStats)"
```

## Context
The 8 statistics actions complete the AnkiConnect surface's review-history/stats gap. Reads query `col.db`/`col.sched`/`col.stats()` on the executor; `insertReviews` writes raw revlog rows (parameterized) + `col.save()`. Faithful contracts: `cardReviews` → 9-col rows (`id,cid,usn,ease,ivl,lastIvl,factor,time,type`); `getReviewsOfCards` → `{cid: [{id,usn,ease,ivl,lastIvl,factor,time,type}]}`; `getNumCardsReviewedToday`/`ByDay` use `col.sched.day_cutoff`; `getCollectionStatsHTML` → `col.stats().report()` HTML (works headless); `getDeckStats` → `{deck_id: {name,new_count,…}}` from `deck_due_tree`.

## Report Format
Status, pytest summaries, files changed, self-review, commit SHA, concerns (incl. whether `col.stats().report()` + `day_cutoff` + the JSON int-key serialization behaved as expected).

---

## Self-Review
**1. Coverage:** all 8 actions implemented + tested (insert/latest/today, cardReviews 9-col, getReviewsOfCards dict, byDay, statsHTML, deckStats). **2. Placeholders:** none — every action is complete; the occlusions-style SQL is parameterized. **3. Consistency:** `@action` names match AnkiConnect exactly; `rt.service.run` pattern; `_REVLOG_COLS` column order is the faithful `id,cid,usn,ease,ivl,lastIvl,factor,time,type`; `getReviewsOfCards` strips `cid` and keys by `id,usn,…` (cid-first SELECT). **4. Risks:** `insertReviews` is a raw write (parameterized + `col.save()`; no OpChanges/broadcast — faithful to AnkiConnect, stats don't refresh the study UI); JSON serializes int dict-keys as strings (tests use `str(id)`); `col.decks.id` creates-if-missing (faithful); `getCollectionStatsHTML` sets `.wholeCollection` under try/except (legacy attr); f-strings inject only fixed column constants, never user values.
