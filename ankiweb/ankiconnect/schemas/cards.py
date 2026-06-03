"""Request models for the card actions (ankiweb/ankiconnect/actions/cards.py)."""
from __future__ import annotations
from typing import Any, Optional
from pydantic import Field
from ankiweb.ankiconnect.schemas._base import ACBaseModel


class FindCardsParams(ACBaseModel):
    """Find card ids matching an Anki browser search query."""
    query: str = Field(default="", description="Anki search string, e.g. 'deck:French is:due'.")


class CardsInfoParams(ACBaseModel):
    """Return full info (fields, deck, scheduling, …) for each card id."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")


class CardsModTimeParams(ACBaseModel):
    """Return the modification time of each card id."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")


class SuspendParams(ACBaseModel):
    """Suspend (or unsuspend) the given cards."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")
    suspend: bool = Field(default=True, description="True to suspend, False to unsuspend.")


class UnsuspendParams(ACBaseModel):
    """Unsuspend the given cards."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")


class SuspendedParams(ACBaseModel):
    """Whether a single card is currently suspended."""
    card: int = Field(description="Card id.")


class AreSuspendedParams(ACBaseModel):
    """Per-card suspended state (None for an unknown card id)."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")


class AreDueParams(ACBaseModel):
    """Per-card 'is it due' flag."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")


class GetEaseFactorsParams(ACBaseModel):
    """Per-card ease factor (None for an unknown card id)."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")


class SetEaseFactorsParams(ACBaseModel):
    """Set each card's ease factor; returns per-card success."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")
    easeFactors: list[int] = Field(default_factory=list,
                                   description="New ease factors, parallel to `cards`.")


class SetSpecificValueOfCardParams(ACBaseModel):
    """Set arbitrary card column(s). Risky keys require warning_check=True."""
    card: int = Field(description="Card id.")
    keys: list[str] = Field(default_factory=list, description="Card attribute names to set.")
    newValues: list[Any] = Field(default_factory=list,
                                 description="New values, parallel to `keys`.")
    warning_check: bool = Field(default=False,
                                description="Must be True to set protected attributes.")


class GetIntervalsParams(ACBaseModel):
    """Per-card review interval(s)."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")
    complete: bool = Field(default=False,
                           description="If True, return the full interval history per card.")


class ForgetCardsParams(ACBaseModel):
    """Reset the given cards to new (forget review history)."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")


class RelearnCardsParams(ACBaseModel):
    """Move the given cards into the relearning queue."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")


class AnswerItem(ACBaseModel):
    """A single card answer."""
    cardId: int = Field(description="Card id.")
    ease: int = Field(description="Answer button 1=Again, 2=Hard, 3=Good, 4=Easy.")


class AnswerCardsParams(ACBaseModel):
    """Answer cards as if reviewed; returns per-answer success."""
    answers: list[AnswerItem] = Field(default_factory=list, description="Cards to answer.")


class SetDueDateParams(ACBaseModel):
    """Reschedule cards to a due date/range (Anki 'Set Due Date' syntax)."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")
    days: str = Field(default="0",
                      description="Days from today: '3', a range '1-7', or '1!' to also reset.")
