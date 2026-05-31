from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AnkiConnectConfig:
    api_key: str | None = None
    cors_origin_list: list = field(default_factory=lambda: ["http://localhost"])
    bind_address: str = "127.0.0.1"
    bind_port: int = 8765
    ignore_origin_list: list = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "AnkiConnectConfig":
        data = {}
        if Path(path).exists():
            data = json.loads(Path(path).read_text() or "{}")
        return cls(
            api_key=data.get("apiKey"),
            cors_origin_list=data.get("webCorsOriginList", ["http://localhost"]),
            bind_address=data.get("webBindAddress", "127.0.0.1"),
            bind_port=int(data.get("webBindPort", 8765)),
            ignore_origin_list=data.get("ignoreOriginList", []),
        )
