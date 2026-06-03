"""Typed REST surface for AnkiConnect actions — one documented `POST /actions/<name>` route
per action, generated from ACTION_SPECS. Purely additive: every route is a thin typed shell
that calls the same dispatch_one as `POST /`, so behavior never diverges from the canonical
JSON-RPC endpoint."""
from __future__ import annotations
import inspect
from typing import Any, Optional

from fastapi import APIRouter, Request, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, create_model

from ankiweb.ankiconnect.registry import (
    ACTION_SPECS, ACTIONS, EXTRA_ACTION_SPECS, EXTRA_ACTIONS, ActionSpec)
from ankiweb.ankiconnect.dispatch import dispatch_one
from ankiweb.ankiconnect.runtime import Runtime
from ankiweb.ankiconnect.schemas._base import LooseParams

# Optional API key; auto_error=False so the request still reaches dispatch_one, which owns the
# gate (and stays open when no key is configured). Renders the "Authorize" lock in Swagger.
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class Envelope(BaseModel):
    """Generic AnkiConnect reply: success -> {result, error: null}; failure -> {result: null,
    error: <message>}. Errors are always returned with HTTP 200, as upstream does."""
    result: Any = None
    error: Optional[str] = None


def _pascal(name: str) -> str:
    return name[:1].upper() + name[1:]


def _response_model(spec: ActionSpec) -> type:
    if spec.result_type is None:
        return Envelope
    return create_model(
        f"{_pascal(spec.name)}Response",
        result=(Optional[spec.result_type], None),
        error=(Optional[str], None),
    )


def _make_endpoint(name: str, model: type, registry: dict, op_name: str):
    async def endpoint(params, request: Request, x_api_key: Optional[str]):
        rt = Runtime(service=request.app.state.service,
                     config=request.app.state.config,
                     hub=request.app.state.hub,
                     notifier=getattr(request.app.state, "notifier", None))
        req = {"action": name, "version": 6,
               "params": params.model_dump(exclude_unset=True, by_alias=True)}
        if x_api_key is not None:
            req["key"] = x_api_key
        return await dispatch_one(rt, req, actions=registry)

    # Build the signature dynamically so FastAPI generates a distinct request-body schema per
    # action (the POC validated this works on fastapi 0.136 / pydantic 2.13).
    endpoint.__signature__ = inspect.Signature([
        inspect.Parameter("params", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=model),
        inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request),
        inspect.Parameter("x_api_key", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                          default=Security(_api_key_header), annotation=Optional[str]),
    ])
    endpoint.__name__ = op_name  # unique operationId across the two namespaces
    return endpoint


def _build_router(prefix: str, tag: str, specs: dict, registry: dict) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])
    for name in sorted(specs):
        spec = specs[name]
        model = spec.params_model or LooseParams
        op_name = name if tag == "actions" else f"{tag}__{name}"
        router.add_api_route(
            f"/{name}",
            _make_endpoint(name, model, registry, op_name),
            methods=["POST"],
            response_model=_response_model(spec),
            name=op_name,
            summary=spec.summary or f"AnkiConnect action: {name}",
            description=spec.description,
        )
    return router


def build_actions_router() -> APIRouter:
    """One POST /actions/<name> per canonical action. Call after actions are imported."""
    return _build_router("/actions", "actions", ACTION_SPECS, ACTIONS)


def build_extra_actions_router() -> APIRouter:
    """One POST /extra_actions/<name> per ankiweb-original action (not on the canonical root)."""
    return _build_router("/extra_actions", "extra_actions", EXTRA_ACTION_SPECS, EXTRA_ACTIONS)
