import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_deck_options_serves_spa_shell(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    r = client.get(f"/deck-options/{did}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "_app/immutable/entry" in r.text


def test_frontend_service_methods_are_custom_noops(client):
    for m in ("deckOptionsReady", "deckOptionsRequireClose"):
        r = client.post(f"/_anki/{m}", content=b"", headers={"content-type": "application/binary"})
        assert r.status_code == 204, m


def test_get_deck_configs_for_update_passthrough(client):
    r = client.post("/_anki/get_deck_configs_for_update", content=b"",
                    headers={"content-type": "application/binary"})
    assert r.status_code != 404


def test_passthrough_and_custom_registered():
    from ankiweb.anki_rpc.passthrough import PASSTHROUGH
    from ankiweb.anki_rpc.handlers import CUSTOM
    for m in ("get_ignored_before_count", "compute_fsrs_params", "evaluate_params_legacy",
              "compute_optimal_retention", "simulate_fsrs_review", "simulate_fsrs_workload",
              "get_retention_workload", "set_wants_abort"):
        assert m in PASSTHROUGH, m
    for m in ("updateDeckConfigs", "deckOptionsReady", "deckOptionsRequireClose"):
        assert m in CUSTOM, m


def test_update_deck_configs_persists_and_broadcasts(client):
    import anki.deck_config_pb2 as dc
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    state = client.portal.call(client.app.state.service.run,
                               lambda col: col.decks.get_deck_configs_for_update(did))
    # state.all_config[0] is DeckConfigsForUpdate.ConfigWithExtra
    # .config is DeckConfig (has id, name, mtime_secs, usn, config)
    # .config.config is DeckConfig.Config (has new_per_day, etc.)
    deck_config = state.all_config[0].config
    inner_config = deck_config.config
    new_limit = inner_config.new_per_day + 7
    inner_config.new_per_day = new_limit
    req = dc.UpdateDeckConfigsRequest(
        target_deck_id=did, configs=[deck_config], removed_config_ids=[],
        mode=dc.UpdateDeckConfigsMode.UPDATE_DECK_CONFIGS_MODE_NORMAL,
        card_state_customizer=state.card_state_customizer,
        limits=state.current_deck.limits,
        new_cards_ignore_review_limit=state.new_cards_ignore_review_limit,
        apply_all_parent_limits=state.apply_all_parent_limits,
        fsrs=state.fsrs, fsrs_reschedule=False)
    r = client.post("/_anki/updateDeckConfigs", content=req.SerializeToString(),
                    headers={"content-type": "application/binary"})
    assert r.status_code == 200
    persisted = client.portal.call(
        client.app.state.service.run,
        lambda col: col.decks.get_deck_configs_for_update(did).all_config[0].config.config.new_per_day)
    assert persisted == new_limit


def test_gear_menu_navigates_to_deck_options(client):
    did = client.portal.call(client.app.state.service.run, lambda col: col.decks.id("Default"))
    with client.websocket_connect("/ws?context=deckbrowser") as ws:
        ws.send_json({"type": "cmd", "id": None, "ctx": "deckbrowser", "arg": f"opts:{did}"})
        m = ws.receive_json()
        while m["type"] != "call" or m["fn"] != "ankiwebNavigate":
            m = ws.receive_json()
        assert m["args"] == [f"/deck-options/{did}"]
