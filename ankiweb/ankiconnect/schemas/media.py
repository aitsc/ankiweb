"""Request models for the media actions (ankiweb/ankiconnect/actions/media.py)."""
from __future__ import annotations
from typing import Optional
from pydantic import Field
from ankiweb.ankiconnect.schemas._base import ACBaseModel


class StoreMediaFileParams(ACBaseModel):
    """Store a file in the media folder from base64 data, an absolute path, or a url."""
    filename: Optional[str] = Field(default=None,
                                    description="Target media filename; prefix with '_' to keep it unused-safe.")
    data: Optional[str] = Field(default=None, description="Base64-encoded file contents.")
    path: Optional[str] = Field(default=None, description="Absolute path to a local file to read.")
    url: Optional[str] = Field(default=None, description="URL to download the file from.")
    skipHash: Optional[str] = Field(default=None,
                                    description="MD5 hex; skip storing if the source matches this hash.")
    deleteExisting: bool = Field(default=True,
                                 description="If False, let Anki rename instead of overwriting an existing file.")


class RetrieveMediaFileParams(ACBaseModel):
    """Retrieve the base64-encoded contents of a media file (False if it does not exist)."""
    filename: Optional[str] = Field(default=None, description="Media filename to read.")


class GetMediaFilesNamesParams(ACBaseModel):
    """List media filenames matching a glob pattern."""
    pattern: str = Field(default="*", description="Glob pattern, e.g. '_hell*.txt'. Defaults to all files.")


class GetMediaDirPathParams(ACBaseModel):
    """Get the full path to the collection.media folder of the current profile."""


class DeleteMediaFileParams(ACBaseModel):
    """Delete a media file from the media folder."""
    filename: Optional[str] = Field(default=None, description="Media filename to delete.")
