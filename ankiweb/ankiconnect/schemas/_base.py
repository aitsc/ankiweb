"""Base models for AnkiConnect action request schemas."""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict


class ACBaseModel(BaseModel):
    """Base for every `<Action>Params` model. `extra="forbid"` makes the docs honest — the
    schema lists exactly the params the action accepts — and is kept safe by the registry
    cross-check test (model fields == handler signature params)."""
    model_config = ConfigDict(extra="forbid")


class LooseParams(BaseModel):
    """Fallback body for an action that has no params_model yet: accepts any JSON object and
    passes it through. Lets the typed surface roll out incrementally without breaking calls."""
    model_config = ConfigDict(extra="allow")
