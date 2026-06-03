from __future__ import annotations
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.schemas.decks import (
    DeckNamesParams, DeckNamesAndIdsParams, GetDecksParams, CreateDeckParams, ChangeDeckParams,
    DeleteDecksParams, GetDeckConfigParams, SaveDeckConfigParams, SetDeckConfigIdParams,
    CloneDeckConfigIdParams, RemoveDeckConfigIdParams, GetDeckStatsParams, DeckNameFromIdParams,
)


def _config_exists(col, conf_id) -> bool:
    """In anki 25.9.4 col.decks.get_config(missing) returns the DEFAULT config (id=1),
    NOT None — so an `is None` guard is a dead branch. Check existence by matching the
    returned dict's id to the requested id."""
    try:
        c = col.decks.get_config(int(conf_id))
    except Exception:
        return False
    return c is not None and int(c["id"]) == int(conf_id)


@action("deckNames", params=DeckNamesParams, returns=list[str], summary="List all deck names")
async def deck_names(rt):
    return await rt.service.run(lambda col: [d.name for d in col.decks.all_names_and_ids()])


@action("deckNamesAndIds", params=DeckNamesAndIdsParams, summary="Map deck names to ids")
async def deck_names_and_ids(rt):
    return await rt.service.run(
        lambda col: {d.name: d.id for d in col.decks.all_names_and_ids()})


@action("getDecks", params=GetDecksParams, summary="Group cards by deck")
async def get_decks(rt, cards=None):
    cards = cards or []

    def fn(col):
        out: dict[str, list] = {}
        for cid in cards:
            # Match canonical AnkiConnect: look the deck up by SQL (non-raising) instead of
            # col.get_card (raises on a bad id). A missing card -> did None -> decks.get(None)
            # returns the Default deck, so unknown ids bucket under "Default" as upstream does.
            did = col.db.scalar("select did from cards where id = ?", cid)
            name = col.decks.get(did)["name"]
            out.setdefault(name, []).append(cid)
        return out
    return await rt.service.run(fn)


@action("createDeck", params=CreateDeckParams, returns=int, summary="Create a deck")
async def create_deck(rt, deck=None):
    # get-or-create; returns the deck id (AnkiConnect semantics)
    return await rt.service.run(lambda col: col.decks.id(deck))


@action("changeDeck", params=ChangeDeckParams, summary="Move cards to a deck")
async def change_deck(rt, cards=None, deck=None):
    cards = cards or []

    def fn(col):
        did = col.decks.id(deck)  # create target if missing
        return col.set_deck(cards, did)
    await rt.service.run_op(fn, initiator="ankiconnect")
    return None


@action("deleteDecks", params=DeleteDecksParams, summary="Delete decks (and their cards)")
async def delete_decks(rt, decks=None, cardsToo=False):
    if not cardsToo:
        raise Exception("deleteDecks requires cardsToo=true (ankiweb won't keep orphan cards)")
    decks = decks or []

    def fn(col):
        ids = [col.decks.id_for_name(name) for name in decks]  # read-only: don't create
        ids = [i for i in ids if i is not None]
        return col.decks.remove(ids)
    await rt.service.run_op(fn, initiator="ankiconnect")
    return None


@action("getDeckConfig", params=GetDeckConfigParams, summary="Get a deck's config group")
async def get_deck_config(rt, deck=None):
    def fn(col):
        did = col.decks.id_for_name(deck)  # read-only: don't create the deck on a query
        if did is None:
            return False
        return col.decks.config_dict_for_deck_id(did)
    return await rt.service.run(fn)


@action("saveDeckConfig", params=SaveDeckConfigParams, returns=bool,
        summary="Save a deck config group")
async def save_deck_config(rt, config=None):
    def fn(col):
        if not config or not _config_exists(col, config.get("id")):
            return False
        col.decks.update_config(config)
        return True
    return await rt.service.run(fn)


@action("setDeckConfigId", params=SetDeckConfigIdParams, returns=bool,
        summary="Assign a config group to decks")
async def set_deck_config_id(rt, decks=None, configId=None):
    decks = decks or []

    def fn(col):
        if not _config_exists(col, configId):
            return False
        for name in decks:
            did = col.decks.id_for_name(name)  # read-only: skip missing decks
            if did is None:
                continue
            d = col.decks.get(did)
            d["conf"] = int(configId)
            col.decks.save(d)
        return True
    return await rt.service.run(fn)


@action("cloneDeckConfigId", params=CloneDeckConfigIdParams, summary="Clone a config group")
async def clone_deck_config_id(rt, name=None, cloneFrom="1"):
    def fn(col):
        if not _config_exists(col, cloneFrom):
            return False
        clone = col.decks.get_config(int(cloneFrom))
        return col.decks.add_config_returning_id(name, clone)
    return await rt.service.run(fn)


@action("removeDeckConfigId", params=RemoveDeckConfigIdParams, returns=bool,
        summary="Remove a config group")
async def remove_deck_config_id(rt, configId=None):
    def fn(col):
        # refuse the Default config (id 1 → backend raises) and unknown ids
        if int(configId) == 1 or not _config_exists(col, configId):
            return False
        col.decks.remove_config(int(configId))
        return True
    return await rt.service.run(fn)


@action("getDeckStats", params=GetDeckStatsParams, summary="Get card/due stats for decks")
async def get_deck_stats(rt, decks=None):
    names = decks or []

    def fn(col):
        # deck_due_tree() nodes carry LEAF names, so match by id (not name): resolve each
        # requested full name → id (read-only), then find its node in the tree.
        tree = col.sched.deck_due_tree()
        out: dict[str, dict] = {}
        for name in names:
            did = col.decks.id_for_name(name)  # read-only: don't create unknown decks
            if did is None:
                continue
            node = col.decks.find_deck_in_tree(tree, did)
            if node is None:  # exists but pruned from the due-tree (e.g. empty) → zeros
                out[str(did)] = {"deck_id": did, "name": name, "new_count": 0,
                                 "learn_count": 0, "review_count": 0, "total_in_deck": 0}
            else:
                out[str(did)] = {"deck_id": did, "name": name,
                                 "new_count": node.new_count, "learn_count": node.learn_count,
                                 "review_count": node.review_count,
                                 "total_in_deck": node.total_in_deck}
        return out
    return await rt.service.run(fn)


@action("deckNameFromId", params=DeckNameFromIdParams, returns=str, summary="Resolve deck id to name")
async def deck_name_from_id(rt, deckId=None):
    return await rt.service.run(lambda col: col.decks.name(deckId))
