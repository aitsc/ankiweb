from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class UiState:
    """Server-side mirror of the live web UI, shared on the BridgeHub. Single-user local.

    Written by: the web client/screens (current_screen via dispatch_cmd + WS connect;
    current_card_id/side by the reviewer handler) and the gui* actions (browse/selection)."""
    current_screen: str | None = None        # 'deckbrowser'|'overview'|'reviewer'|'congrats'
    current_card_id: int | None = None        # reviewer's in-flight card
    side: str | None = None                   # 'question'|'answer'|None
    browser_open: bool = False                # set True by guiBrowse (degraded "Browser window")
    last_browse_query: str | None = None      # the last guiBrowse query (may be None)
    matched_card_ids: list = field(default_factory=list)
    selected_card_ids: list = field(default_factory=list)
    selected_note_ids: list = field(default_factory=list)

    @property
    def review_active(self) -> bool:
        return self.current_screen == "reviewer" and self.current_card_id is not None
