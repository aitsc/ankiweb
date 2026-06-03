"""Request models for the meta actions (ankiweb/ankiconnect/actions/meta.py)."""
from __future__ import annotations
from typing import Optional
from pydantic import Field
from ankiweb.ankiconnect.schemas._base import ACBaseModel


class VersionParams(ACBaseModel):
    """Return the AnkiConnect API version."""


class ApiReflectParams(ACBaseModel):
    """List the available AnkiConnect actions for the requested scopes."""
    scopes: list[str] = Field(default_factory=list,
                              description="Scopes to reflect on; only 'actions' is supported.")
    actions: Optional[list[str]] = Field(
        default=None,
        description="If null, list all actions; otherwise restrict to these action names.")


class RequestPermissionParams(ACBaseModel):
    """Request permission to use the API (origin/allowed are injected from CORS state)."""
    allowed: bool = Field(default=False,
                          description="Whether the requesting origin is trusted/allowed.")
    origin: Optional[str] = Field(default=None, description="The requesting origin.")


class ReloadCollectionParams(ACBaseModel):
    """Reload the collection (no-op on ankiweb)."""


class GetProfilesParams(ACBaseModel):
    """List the available profile names."""


class GetActiveProfileParams(ACBaseModel):
    """Return the name of the currently active profile."""


class LoadProfileParams(ACBaseModel):
    """Select the profile with the given name."""
    name: Optional[str] = Field(default=None, description="Profile name to load.")


class SyncParams(ACBaseModel):
    """Synchronize the local collection (not supported by ankiweb)."""
