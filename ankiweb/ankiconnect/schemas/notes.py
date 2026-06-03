"""Request models for the note actions (ankiweb/ankiconnect/actions/notes.py)."""
from __future__ import annotations
from typing import Optional
from pydantic import Field
from ankiweb.ankiconnect.schemas._base import ACBaseModel


# --- shared nested helpers for the addNote/addNotes note spec ---------------

class AddNoteMedia(ACBaseModel):
    """A single audio/video/picture media item to download and embed in a new note."""
    filename: str = Field(description="Target filename in the media folder.")
    data: Optional[str] = Field(default=None, description="Base64-encoded file contents.")
    path: Optional[str] = Field(default=None, description="Absolute path to read the file from.")
    url: Optional[str] = Field(default=None, description="URL to download the file from.")
    skipHash: Optional[str] = Field(
        default=None, description="Skip the file if its MD5 hash matches this value.")
    fields: list[str] = Field(default_factory=list,
                              description="Field names the media reference is appended to.")


class AddNoteDuplicateScopeOptions(ACBaseModel):
    """Extra settings controlling how duplicates are detected."""
    deckName: Optional[str] = Field(
        default=None, description="Deck used for the duplicate check (defaults to target deck).")
    checkChildren: bool = Field(default=False,
                                description="Also check duplicates in child decks.")
    checkAllModels: bool = Field(default=False,
                                 description="Check duplicates across all note types.")


class AddNoteOptions(ACBaseModel):
    """Per-note add options (duplicate handling)."""
    allowDuplicate: bool = Field(default=False, description="Allow adding a duplicate note.")
    duplicateScope: Optional[str] = Field(
        default=None, description="'deck' to limit duplicate checks to the target deck.")
    duplicateScopeOptions: Optional[AddNoteDuplicateScopeOptions] = Field(
        default=None, description="Additional duplicate-scope settings.")


class AddNoteSpec(ACBaseModel):
    """A note specification: which deck/model, the field values, tags and optional media."""
    deckName: str = Field(default="Default", description="Target deck name.")
    modelName: str = Field(default="", description="Note type (model) name.")
    fields: dict[str, str] = Field(default_factory=dict,
                                   description="Field name -> value map.")
    tags: list[str] = Field(default_factory=list, description="Tags to apply.")
    options: Optional[AddNoteOptions] = Field(default=None, description="Add options.")
    audio: list[AddNoteMedia] = Field(default_factory=list,
                                      description="Audio media to attach.")
    video: list[AddNoteMedia] = Field(default_factory=list,
                                      description="Video media to attach.")
    picture: list[AddNoteMedia] = Field(default_factory=list,
                                        description="Picture media to attach.")


class AddNoteParams(ACBaseModel):
    """Create a single note from a note spec; returns the new note id (or null on failure)."""
    note: AddNoteSpec = Field(description="Note to create.")


class CanAddNoteParams(ACBaseModel):
    """Check whether a single note spec could be added."""
    note: AddNoteSpec = Field(description="Note to test.")


class CanAddNoteWithErrorDetailParams(ACBaseModel):
    """Check whether a single note could be added, returning the failure reason if not."""
    note: AddNoteSpec = Field(description="Note to test.")


class AddNotesParams(ACBaseModel):
    """Create multiple notes from note specs; returns the list of new note ids."""
    notes: list[AddNoteSpec] = Field(default_factory=list, description="Notes to create.")


class CanAddNotesParams(ACBaseModel):
    """Check whether each of several note specs could be added."""
    notes: list[AddNoteSpec] = Field(default_factory=list, description="Notes to test.")


class CanAddNotesWithErrorDetailParams(ACBaseModel):
    """Check whether each note could be added, returning per-note failure reasons."""
    notes: list[AddNoteSpec] = Field(default_factory=list, description="Notes to test.")


class FindNotesParams(ACBaseModel):
    """Find note ids matching an Anki browser search query."""
    query: Optional[str] = Field(default=None,
                                 description="Anki search string, e.g. 'deck:French'.")


class NotesInfoParams(ACBaseModel):
    """Return full info for the given note ids, or for notes matching a query."""
    notes: Optional[list[int]] = Field(default=None, description="Note ids.")
    query: Optional[str] = Field(default=None,
                                 description="Anki search string (used when `notes` is omitted).")


# --- nested helper for updateNoteFields / updateNote / updateNoteModel ------

class UpdateNoteFieldsSpec(ACBaseModel):
    """An update spec identifying a note by id with new field values and optional media."""
    id: int = Field(description="Note id to update.")
    fields: dict[str, str] = Field(default_factory=dict,
                                   description="Field name -> new value map.")
    audio: list[AddNoteMedia] = Field(default_factory=list,
                                      description="Audio media to attach.")
    video: list[AddNoteMedia] = Field(default_factory=list,
                                      description="Video media to attach.")
    picture: list[AddNoteMedia] = Field(default_factory=list,
                                        description="Picture media to attach.")


class UpdateNoteFieldsParams(ACBaseModel):
    """Modify the fields of an existing note."""
    note: UpdateNoteFieldsSpec = Field(description="Note id and the fields to update.")


class UpdateNoteTagsParams(ACBaseModel):
    """Replace a note's tags by note id."""
    note: int = Field(description="Note id.")
    tags: list[str] = Field(default_factory=list, description="New complete tag list.")


class GetNoteTagsParams(ACBaseModel):
    """Return the tags of a single note."""
    note: int = Field(description="Note id.")


class UpdateNoteSpec(ACBaseModel):
    """A combined fields/tags update spec; either `fields` or `tags` may be omitted."""
    id: int = Field(description="Note id to update.")
    fields: Optional[dict[str, str]] = Field(default=None,
                                             description="Field name -> new value map.")
    tags: Optional[list[str]] = Field(default=None, description="New complete tag list.")
    audio: list[AddNoteMedia] = Field(default_factory=list,
                                      description="Audio media to attach.")
    video: list[AddNoteMedia] = Field(default_factory=list,
                                      description="Video media to attach.")
    picture: list[AddNoteMedia] = Field(default_factory=list,
                                        description="Picture media to attach.")


class UpdateNoteParams(ACBaseModel):
    """Modify the fields and/or tags of an existing note."""
    note: UpdateNoteSpec = Field(description="Note id and the fields/tags to update.")


class UpdateNoteModelSpec(ACBaseModel):
    """An update spec that reassigns a note's model along with new fields and tags."""
    id: int = Field(description="Note id to update.")
    modelName: str = Field(default="", description="New note type (model) name.")
    fields: dict[str, str] = Field(default_factory=dict,
                                   description="Field name -> new value map.")
    tags: Optional[list[str]] = Field(default=None, description="New complete tag list.")


class UpdateNoteModelParams(ACBaseModel):
    """Reassign a note's model, fields and tags."""
    note: UpdateNoteModelSpec = Field(description="Note id, target model and new content.")


class AddTagsParams(ACBaseModel):
    """Add tags to the given notes."""
    notes: list[int] = Field(default_factory=list, description="Note ids.")
    tags: Optional[str] = Field(default=None,
                                description="Space-separated tags to add.")
    add: bool = Field(default=True, description="Reserved flag; tags are always added.")


class RemoveTagsParams(ACBaseModel):
    """Remove tags from the given notes."""
    notes: list[int] = Field(default_factory=list, description="Note ids.")
    tags: Optional[str] = Field(default=None,
                                description="Space-separated tags to remove.")


class GetTagsParams(ACBaseModel):
    """Return every tag in the collection."""


class ClearUnusedTagsParams(ACBaseModel):
    """Remove tags that are not used by any note."""


class ReplaceTagsParams(ACBaseModel):
    """Replace a tag with another tag on the given notes."""
    notes: list[int] = Field(default_factory=list, description="Note ids.")
    tag_to_replace: Optional[str] = Field(default=None, description="Existing tag to replace.")
    replace_with_tag: Optional[str] = Field(default=None, description="Replacement tag.")


class ReplaceTagsInAllNotesParams(ACBaseModel):
    """Replace a tag with another tag across all notes."""
    tag_to_replace: Optional[str] = Field(default=None, description="Existing tag to replace.")
    replace_with_tag: Optional[str] = Field(default=None, description="Replacement tag.")


class NotesModTimeParams(ACBaseModel):
    """Return the modification time of each note id."""
    notes: list[int] = Field(default_factory=list, description="Note ids.")


class DeleteNotesParams(ACBaseModel):
    """Delete the given notes (and their cards)."""
    notes: list[int] = Field(default_factory=list, description="Note ids.")


class RemoveEmptyNotesParams(ACBaseModel):
    """Remove notes whose every card is empty."""


class CardsToNotesParams(ACBaseModel):
    """Map the given card ids to their distinct note ids."""
    cards: list[int] = Field(default_factory=list, description="Card ids.")
