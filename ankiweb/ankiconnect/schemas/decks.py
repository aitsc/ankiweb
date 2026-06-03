"""Request models for the deck actions (ankiweb/ankiconnect/actions/decks.py)."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from ankiweb.ankiconnect.schemas._base import ACBaseModel


class DeckNamesParams(ACBaseModel):
    """List every deck name for the current profile (no params)."""


class DeckNamesAndIdsParams(ACBaseModel):
    """Map every deck name to its deck id (no params)."""


class GetDecksParams(ACBaseModel):
    """Group the given card ids by the deck each card belongs to."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")


class CreateDeckParams(ACBaseModel):
    """Create a deck by name (get-or-create); returns the deck id."""
    deck: Optional[str] = Field(default=None,
                                description="Deck name, '::' separated for subdecks.")


class ChangeDeckParams(ACBaseModel):
    """Move the given cards into a deck, creating it if needed."""
    cards: list[int] = Field(default_factory=list, description="Card ids to move.")
    deck: Optional[str] = Field(default=None, description="Target deck name.")


class DeleteDecksParams(ACBaseModel):
    """Delete decks by name; `cardsToo` must be True."""
    decks: list[str] = Field(default_factory=list, description="Deck names to delete.")
    cardsToo: bool = Field(default=False,
                           description="Must be True; also deletes the cards in those decks.")


class GetDeckConfigParams(ACBaseModel):
    """Get the options-group config for a deck (False if the deck is unknown)."""
    deck: Optional[str] = Field(default=None, description="Deck name.")


class SaveDeckConfigConfig(BaseModel):
    """A deck options-group config object (as returned by getDeckConfig).

    Accepts the full Anki config dict; only `id` is read explicitly to locate the group.
    """
    model_config = ConfigDict(extra="allow")
    id: Optional[int] = Field(default=None, description="Id of the config group to update.")


class SaveDeckConfigParams(ACBaseModel):
    """Save an options-group config object; True on success, False if its id is unknown."""
    config: Optional[SaveDeckConfigConfig] = Field(
        default=None, description="Config group object to save (must contain a valid `id`).")


class SetDeckConfigIdParams(ACBaseModel):
    """Assign an existing config group to the given decks; False if any is unknown."""
    decks: list[str] = Field(default_factory=list, description="Deck names to update.")
    configId: Optional[int] = Field(default=None, description="Existing config-group id.")


class CloneDeckConfigIdParams(ACBaseModel):
    """Clone a config group under a new name; returns the new id or False."""
    name: Optional[str] = Field(default=None, description="Name for the new config group.")
    cloneFrom: str = Field(default="1",
                           description="Source config-group id to clone (default '1').")


class RemoveDeckConfigIdParams(ACBaseModel):
    """Remove a config group by id; False for id 1 (Default) or an unknown id."""
    configId: Optional[int] = Field(default=None, description="Config-group id to remove.")


class GetDeckStatsParams(ACBaseModel):
    """Get card-count/due stats for the given decks, keyed by deck id."""
    decks: list[str] = Field(default_factory=list, description="Deck names.")


class DeckNameFromIdParams(ACBaseModel):
    """Resolve a deck id to its full deck name."""
    deckId: Optional[int] = Field(default=None, description="Deck id.")
