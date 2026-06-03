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
