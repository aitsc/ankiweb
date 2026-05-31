from __future__ import annotations
from typing import Awaitable, Callable

# camelCaseMethod -> async handler(service, body: bytes) -> bytes
CUSTOM: dict[str, Callable[..., Awaitable[bytes]]] = {}
