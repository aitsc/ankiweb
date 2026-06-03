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
