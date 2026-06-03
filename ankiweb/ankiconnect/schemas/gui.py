"""Request models for the GUI actions (ankiweb/ankiconnect/actions/gui.py)."""
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field
from ankiweb.ankiconnect.schemas._base import ACBaseModel


class GuiReviewActiveParams(ACBaseModel):
    """Whether a reviewer session is currently active."""


class GuiCurrentCardParams(ACBaseModel):
    """Return info about the card currently shown in the reviewer."""


class GuiStartCardTimerParams(ACBaseModel):
    """Start/reset the answer timer for the current reviewer card."""


class GuiShowQuestionParams(ACBaseModel):
    """Show the question side of the current reviewer card."""


class GuiShowAnswerParams(ACBaseModel):
    """Show the answer side of the current reviewer card."""


class GuiAnswerCardParams(ACBaseModel):
    """Answer the current reviewer card with the given ease button."""
    ease: Optional[int] = Field(default=None,
                                description="Answer button: 1=Again, 2=Hard, 3=Good, 4=Easy.")


class GuiDeckBrowserParams(ACBaseModel):
    """Open the Deck Browser screen."""


class GuiDeckOverviewParams(ACBaseModel):
    """Open the Deck Overview screen for a deck by name."""
    name: Optional[str] = Field(default=None, description="Deck name.")


class GuiDeckReviewParams(ACBaseModel):
    """Start reviewing a deck by name."""
    name: Optional[str] = Field(default=None, description="Deck name.")


class GuiUndoParams(ACBaseModel):
    """Undo the last collection operation."""


class GuiCheckDatabaseParams(ACBaseModel):
    """Run the collection database integrity check."""


class GuiBrowseReorder(BaseModel):
    """Optional reorder spec for the Card Browser."""
    columnId: str = Field(description="Browser column identifier to sort by.")
    order: str = Field(description="Sort order: 'ascending' or 'descending'.")


class GuiBrowseParams(ACBaseModel):
    """Open the Card Browser and search for a query."""
    query: Optional[str] = Field(default=None, description="Anki search string.")
    reorderCards: Optional[GuiBrowseReorder] = Field(
        default=None, description="Optional column/order to reorder the matched cards.")


class GuiSelectCardParams(ACBaseModel):
    """Select a card (by card id) in the open Card Browser."""
    card: Optional[int] = Field(default=None, description="Card id to select.")


class GuiSelectNoteParams(ACBaseModel):
    """Deprecated alias of guiSelectCard; selects by card id."""
    note: Optional[int] = Field(default=None, description="Card id to select.")


class GuiSelectedNotesParams(ACBaseModel):
    """Return the note ids selected in the open Card Browser."""


class GuiPlayAudioParams(ACBaseModel):
    """Replay the audio of the current reviewer card's side."""


class GuiAddNoteSetDataNote(BaseModel):
    """Note spec used to prefill the open Add Note dialog."""
    deckName: Optional[str] = Field(default=None, description="Target deck name.")
    modelName: Optional[str] = Field(default=None, description="Note type (model) name.")
    fields: dict[str, str] = Field(default_factory=dict,
                                   description="Field name -> value mapping.")
    tags: list[str] = Field(default_factory=list, description="Tags to set on the note.")


class GuiAddNoteSetDataParams(ACBaseModel):
    """Prefill the open Add Note dialog with deck/model/fields/tags."""
    note: Optional[GuiAddNoteSetDataNote] = Field(default=None, description="Note spec.")
    append: bool = Field(default=False,
                         description="Append to fields/tags instead of replacing.")


class GuiEditNoteParams(ACBaseModel):
    """Open the Edit dialog for a note id."""
    note: Optional[int] = Field(default=None, description="Note id to edit.")


class GuiAddCardsNote(BaseModel):
    """Note spec used to preset the Add Cards dialog."""
    deckName: Optional[str] = Field(default=None, description="Target deck name.")
    modelName: Optional[str] = Field(default=None, description="Note type (model) name.")
    fields: dict[str, str] = Field(default_factory=dict,
                                   description="Field name -> value mapping.")
    tags: list[str] = Field(default_factory=list, description="Tags to set on the note.")
    audio: list[Any] = Field(default_factory=list, description="Optional audio media specs.")
    video: list[Any] = Field(default_factory=list, description="Optional video media specs.")
    picture: list[Any] = Field(default_factory=list, description="Optional picture media specs.")


class GuiAddCardsParams(ACBaseModel):
    """Preset the Add Cards dialog; returns the prospective note id."""
    note: Optional[GuiAddCardsNote] = Field(default=None, description="Note spec to preset.")


class GuiImportFileParams(ACBaseModel):
    """Invoke the Import dialog (unsupported in ankiweb)."""
    path: Optional[str] = Field(default=None, description="Server-side path of the file to import.")


class GuiExitAnkiParams(ACBaseModel):
    """Schedule a graceful Anki shutdown (no-op in ankiweb)."""
