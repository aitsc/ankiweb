"""Request models for the stats actions (ankiweb/ankiconnect/actions/stats.py)."""
from __future__ import annotations
from typing import Optional
from pydantic import Field
from ankiweb.ankiconnect.schemas._base import ACBaseModel


class GetNumCardsReviewedTodayParams(ACBaseModel):
    """Count of cards reviewed in the current day (per the user's day-start time)."""


class GetNumCardsReviewedByDayParams(ACBaseModel):
    """Number of cards reviewed per day, as a list of (dateString, count) pairs."""


class GetCollectionStatsHTMLParams(ACBaseModel):
    """Render the collection statistics report as HTML."""
    wholeCollection: bool = Field(default=True,
                                  description="If True, report over the whole collection.")


class CardReviewsParams(ACBaseModel):
    """All card reviews for a deck made after a given review id."""
    deck: Optional[str] = Field(default=None, description="Deck name.")
    startID: int = Field(default=0,
                         description="Latest unix-ms review id NOT included in the result.")


class GetReviewsOfCardsParams(ACBaseModel):
    """All card reviews for each given card id."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")


class GetLatestReviewIDParams(ACBaseModel):
    """Unix time of the latest review for the given deck (0 if none)."""
    deck: Optional[str] = Field(default=None, description="Deck name.")


class InsertReviewsParams(ACBaseModel):
    """Insert raw revlog rows. Each review is a 9-tuple (reviewTime, cardID, usn,
    buttonPressed, newInterval, previousInterval, newFactor, reviewDuration, reviewType)."""
    reviews: list[list[int]] = Field(default_factory=list,
                                     description="9-element review rows to insert.")


class GetDeckStatsParams(ACBaseModel):
    """Statistics (total/new/learn/review counts) for the given decks."""
    decks: list[str] = Field(default_factory=list, description="Deck names.")
