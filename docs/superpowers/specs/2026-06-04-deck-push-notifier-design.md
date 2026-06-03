# Deck Push Notifier — Design

**Goal:** Proactively notify an external HTTP endpoint whenever a deck's study counts change —
its `(new_count, learn_count, review_count)` tuple moves (any of the three, including bucket
shifts that preserve the total) — so a downstream system (a study agent, a bot) learns about it
without polling AnkiConnect.

> **Trigger update (2026-06-04):** originally this fired only when the *learnable* boolean
> flipped (total `> 0` ⟷ `= 0`). It now fires on **any change to the counts tuple**. The payload
> still carries a `learnable` field (`total > 0`) for convenience. Configured live from a new **Extras** menu in the
web UI — this is an ankiweb-original feature, distinct from the Anki/AnkiConnect port.

## Definitions

- **Learnable deck:** `new_count + learn_count + review_count > 0`, where the counts come from
  `col.sched.deck_due_tree()` — the same source/semantics as `getDeckStats` (respects daily
  limits, includes subdeck rollup). One backend call returns the whole tree, so this scales to
  thousands of decks (the efficiency requirement).
- Decks are keyed by **full name** (`col.decks.name(deck_id)`, e.g. `A::B::C`) to avoid
  collisions between same-named subdecks. The synthetic root (id 0) is skipped.

## Configuration — web-managed, no env vars

Persisted to a sidecar `notify.json` next to the collection (like `ankiconnect.json`), edited
live from `GET/POST /notify` under the **Extras** toolbar menu. Fields:

| field | meaning |
|---|---|
| `enabled` | master on/off |
| `url` | POST endpoint |
| `token` | bearer token (optional; omitted from the request if empty) |
| `poll_sec` | `deck_due_tree()` refresh cadence (seconds) |
| `retry_sec` | resend cadence after a failed POST (seconds) |

The notifier is **active** only when `enabled && url && poll_sec>0 && retry_sec>0`. Saving the
form persists the file and wakes the running task immediately (an `asyncio.Event`), so changes
take effect without a restart.

## The POST contract (documented in README)

```
POST <url>
Authorization: Bearer <token>        # omitted when token is empty
Content-Type: application/json

{ "source": "ankiweb",
  "ts": 1780500000,                  # epoch seconds
  "changes": [
    { "deck": "英语词汇::单词", "deckId": 1780005159378, "learnable": true,
      "new_count": 12, "learn_count": 3, "review_count": 40 } ] }
```

**Success = HTTP 200 AND a JSON body with `ok === true`.** Anything else (non-200, missing/false
`ok`, non-JSON, timeout, connection error) is a failure → retry. This lets the receiver NACK
(return `{"ok": false}`) to force a resend.

## State machine (in-memory)

Two facts per deck: `current` (latest observed counts) and `last_notified` (the `(new, learn,
review)` tuple the receiver last acknowledged). `last_notified` starts **empty**, and an unseen
deck's baseline is `(0, 0, 0)`, so the first poll treats every deck with nonzero counts as a
change → the startup push (always-empty decks stay silent)s. It also resets to empty whenever the feature is disabled or the `url` changes, so
re-enabling / re-pointing re-syncs the receiver.

Each loop iteration (when active):
1. `current = fetch()` (deck_due_tree snapshot, via `service.run`).
2. Prune `last_notified` keys no longer in `current` (deleted/renamed decks dropped silently).
3. `changes = {d : counts_sig(current[d]) != last_notified.get(d, (0, 0, 0))}`.
4. If `changes`: POST a payload built from the **current** state of the changed decks.
   - success → `last_notified[d] = counts_sig` for each changed deck; wait `poll_sec`.
   - failure → leave `last_notified` untouched; wait `retry_sec`, then re-fetch and re-send.
     Because the payload is always rebuilt from fresh `current`, a deck that changed again while
     a send was failing is sent with its **latest** value, and a flip-then-flip-back nets to no
     notification (coalescing — "notify the last change result").
5. No changes → wait `poll_sec`.

Disabled/invalid → reset baseline and wait on the config-changed event (no fetch, no POST).

## Components / files

- `ankiweb/notifier.py` — `NotifyConfig` (+ `notify.json` load/save), `NotifyStatus`,
  `NotifierState` (shared holder + `asyncio.Event`), pure functions (`learnable`,
  `diff_changes`, `build_payload`, `eval_response`), `snapshot(col)`, and `DeckNotifier`
  (async runner + httpx POST). Pure functions are unit-tested; the runner is tested with a fake
  fetch/post; HTTP I/O is a thin shell over `eval_response`.
- `ankiweb/screens/notify.py` — `render_notify_html(state)` (form prefilled from config + a live
  status panel) and `config_from_form(...)`.
- `ankiweb/screens/page.py` — add an **Extras ▾** CSS dropdown to the toolbar with a
  *Push notifications* item → `/notify`.
- `ankiweb/screens/routes.py` — `GET/POST /notify`; `build_screen_router` gains `get_notifier`.
- `ankiweb/app.py` — `create_app(..., notifier=None)`; set `app.state.notifier` in lifespan
  (defaulting to a fresh `NotifierState` from the collection dir when not injected).
- `ankiweb/__main__.py` — build the `NotifierState`, inject into `create_app`, run
  `DeckNotifier.run()` as a task alongside the two servers, cancel it on shutdown.
- `README.md` — "Deck push notifications" section (Extras menu, POST schema, success contract).

## Scope / decisions

Track **all** decks (receiver filters by name); status panel shows watching/learnable/pending +
last attempt/success/error. No subset filter, no per-deck config (could be added later). Status
is best-effort in-memory (resets on restart). The notifier task runs only under `python -m
ankiweb`; in tests the holder exists for the form, and the engine is tested directly.
