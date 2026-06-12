"""Request models for the ankiweb-original /extra_actions/<name> routes."""
from __future__ import annotations
from typing import Optional
from pydantic import Field
from ankiweb.ankiconnect.schemas._base import ACBaseModel


class DeleteModelParams(ACBaseModel):
    """Delete an entire note type (the reverse of createModel). Identify it by name or id."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    modelId: Optional[int] = Field(default=None,
                                   description="Note type id (alternative to modelName).")


class ExtendCardLimitsParams(ACBaseModel):
    """Add to (or subtract from) today's new/review card limits for a deck — the API form of
    Custom Study's 'Increase today's … card limit'. Identify the deck by name or id."""
    deck: Optional[str] = Field(default=None, description="Deck name.")
    deckId: Optional[int] = Field(default=None, description="Deck id (alternative to `deck`).")
    new: int = Field(default=0, description="Delta for today's NEW card limit (negative reduces).")
    review: int = Field(default=0,
                        description="Delta for today's REVIEW card limit (negative reduces).")


class GetNotifyConfigParams(ACBaseModel):
    """Read the Push-notifications configuration and live status."""
    # no parameters


class SetNotifyConfigParams(ACBaseModel):
    """Modify the Push-notifications configuration. Only the fields you send are changed;
    omitted fields keep their current value. Returns the resulting config + status."""
    enabled: Optional[bool] = Field(default=None, description="Master on/off.")
    url: Optional[str] = Field(default=None, description="POST endpoint URL ('' to clear).")
    token: Optional[str] = Field(default=None, description="Bearer token ('' to clear).")
    poll_sec: Optional[float] = Field(default=None, description="Poll interval, seconds (>0).")
    retry_sec: Optional[float] = Field(default=None, description="Retry interval, seconds (>0).")
    scope: Optional[str] = Field(default=None, description="'leaf' (last-level decks) or 'all'.")
    resync: Optional[bool] = Field(default=None,
                                   description="If true, re-push every nonzero deck after saving.")


class RemoveDuplicateNotesParams(ACBaseModel):
    """Find notes in a deck (and its subdecks) that are duplicates across ALL fields within the
    same note type, and remove the newer copies (keeping the oldest). Identify the deck by name
    or id. Set dryRun to preview the statistics without deleting anything."""
    deck: Optional[str] = Field(default=None, description="Deck name.")
    deckId: Optional[int] = Field(default=None, description="Deck id (alternative to `deck`).")
    dryRun: bool = Field(default=False,
                         description="If true, report duplicates but delete nothing.")
