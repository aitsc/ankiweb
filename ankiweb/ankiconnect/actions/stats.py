from __future__ import annotations
import time
from ankiweb.ankiconnect.registry import action
from ankiweb.ankiconnect.schemas.stats import (
    GetNumCardsReviewedTodayParams, GetNumCardsReviewedByDayParams, GetCollectionStatsHTMLParams,
    CardReviewsParams, GetReviewsOfCardsParams, GetLatestReviewIDParams, InsertReviewsParams,
    GetDeckStatsParams,
)

_REVLOG_COLS = "id, cid, usn, ease, ivl, lastIvl, factor, time, type"


@action("getNumCardsReviewedToday", params=GetNumCardsReviewedTodayParams, returns=int,
        summary="Count cards reviewed today")
async def get_num_cards_reviewed_today(rt):
    def fn(col):
        return col.db.scalar("select count() from revlog where id > ?",
                             (col.sched.day_cutoff - 86400) * 1000)
    return await rt.service.run(fn)


@action("getNumCardsReviewedByDay", params=GetNumCardsReviewedByDayParams,
        summary="Count cards reviewed per day")
async def get_num_cards_reviewed_by_day(rt):
    def fn(col):
        offset = int(time.strftime("%H", time.localtime(col.sched.day_cutoff))) * 3600
        return col.db.all(
            'select date(id/1000 - ?, "unixepoch", "localtime") as day, count() '
            "from revlog group by day order by day desc", offset)
    return await rt.service.run(fn)


@action("getCollectionStatsHTML", params=GetCollectionStatsHTMLParams, returns=str,
        summary="Render collection stats as HTML")
async def get_collection_stats_html(rt, wholeCollection=True):
    def fn(col):
        stats = col.stats()
        try:
            stats.wholeCollection = wholeCollection
        except Exception:
            pass
        return stats.report()
    return await rt.service.run(fn)


@action("cardReviews", params=CardReviewsParams, summary="Card reviews for a deck after an id")
async def card_reviews(rt, deck=None, startID=0):
    def fn(col):
        return col.db.all(
            f"select {_REVLOG_COLS} from revlog "
            "where id > ? and cid in (select id from cards where did = ?)",
            startID, col.decks.id(deck))
    return await rt.service.run(fn)


@action("getReviewsOfCards", params=GetReviewsOfCardsParams, summary="Reviews for each card id")
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


@action("getLatestReviewID", params=GetLatestReviewIDParams, returns=int,
        summary="Latest review id for a deck")
async def get_latest_review_id(rt, deck=None):
    def fn(col):
        return col.db.scalar(
            "select max(id) from revlog where cid in (select id from cards where did = ?)",
            col.decks.id(deck)) or 0
    return await rt.service.run(fn)


@action("insertReviews", params=InsertReviewsParams, summary="Insert raw revlog rows")
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


@action("getDeckStats", params=GetDeckStatsParams, summary="Statistics for the given decks")
async def get_deck_stats(rt, decks=None):
    names = list(decks or [])

    def fn(col):
        deck_ids = [col.decks.id(d) for d in names]
        nodes = {}
        _collect_deck_tree(col.sched.deck_due_tree(), nodes)
        return {did: _deck_stats_json(node) for did, node in nodes.items() if did in deck_ids}
    return await rt.service.run(fn)
