from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

_BASE_HOST_PREFIXES = ("127.0.0.1:", "localhost:", "[::1]:")
_BASE_HOSTS = ("127.0.0.1", "localhost", "testserver", "[::1]")


def host_allowed(host: str, extra=()) -> bool:
    """DNS-rebinding guard. Always allows localhost; allows any host explicitly listed in
    `extra` (matched with OR without a :port); `'*'` in `extra` disables the check entirely
    (open to any Host header — only do this on a trusted network)."""
    if "*" in extra:
        return True
    if host.startswith(_BASE_HOST_PREFIXES) or host in _BASE_HOSTS:
        return True
    if host in extra:
        return True
    bare = host.rsplit(":", 1)[0] if host.count(":") == 1 else host  # strip :port (not IPv6)
    return bare in extra


@dataclass(frozen=True)
class Settings:
    collection_path: Path
    host: str = "127.0.0.1"
    port: int = 8000
    assets_dir: Path = Path(__file__).parent / "web_assets"
    shell_dir: Path = Path(__file__).parent / "shell"
    import_tmp_dir: Path = Path(__file__).parent / "_import_tmp"
    # Extra Host-header values accepted by the DNS-rebinding guard (beyond localhost),
    # e.g. ("192.168.1.50:8000",) or ("myhost.local",). "*" disables the check.
    allowed_hosts: tuple = ()

    @classmethod
    def from_env(cls) -> "Settings":
        default = Path.home() / ".local/share/ankiweb/collection.anki2"
        return cls(
            collection_path=Path(os.environ.get("ANKIWEB_COLLECTION", str(default))),
            host=os.environ.get("ANKIWEB_HOST", "127.0.0.1"),
            port=int(os.environ.get("ANKIWEB_PORT", "8000")),
            import_tmp_dir=Path(os.environ["ANKIWEB_IMPORT_TMP_DIR"]) if os.environ.get("ANKIWEB_IMPORT_TMP_DIR") else (Path(os.environ.get("ANKIWEB_COLLECTION", str(default))).parent / "import-tmp"),
            allowed_hosts=tuple(
                h.strip() for h in os.environ.get("ANKIWEB_ALLOWED_HOSTS", "").split(",") if h.strip()),
        )
