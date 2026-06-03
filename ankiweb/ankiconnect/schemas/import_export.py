"""Request models for the import/export actions (ankiweb/ankiconnect/actions/import_export.py)."""
from __future__ import annotations
from typing import Optional
from pydantic import Field
from ankiweb.ankiconnect.schemas._base import ACBaseModel


class ExportPackageParams(ACBaseModel):
    """Export a deck to a server-side .apkg file."""
    deck: Optional[str] = Field(default=None, description="Name of the deck to export.")
    path: Optional[str] = Field(default=None,
                                description="Server-side output path for the .apkg file.")
    includeSched: bool = Field(default=False,
                               description="Include the cards' scheduling data in the export.")


class ImportPackageParams(ACBaseModel):
    """Import a server-side .apkg file into the collection."""
    path: Optional[str] = Field(default=None,
                                description="Server-side path of the .apkg file to import.")
