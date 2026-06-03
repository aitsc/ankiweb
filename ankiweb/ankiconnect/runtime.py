from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class Runtime:
    """Context passed to every AnkiConnect action handler."""
    service: Any                 # CollectionService
    config: Any                  # AnkiConnectConfig
    hub: Any = None              # BridgeHub (for gui* in B4)
    ui_state: Any = None         # reviewer/browser UI mirror (B4)
    notifier: Any = None         # NotifierState (for /extra_actions push-config get/set)
