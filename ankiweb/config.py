from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    collection_path: Path
    host: str = "127.0.0.1"
    port: int = 8000
    assets_dir: Path = Path(__file__).parent / "web_assets"
    shell_dir: Path = Path(__file__).parent / "shell"
    import_tmp_dir: Path = Path(__file__).parent / "_import_tmp"

    @classmethod
    def from_env(cls) -> "Settings":
        default = Path.home() / ".local/share/ankiweb/collection.anki2"
        return cls(
            collection_path=Path(os.environ.get("ANKIWEB_COLLECTION", str(default))),
            host=os.environ.get("ANKIWEB_HOST", "127.0.0.1"),
            port=int(os.environ.get("ANKIWEB_PORT", "8000")),
            import_tmp_dir=Path(os.environ["ANKIWEB_IMPORT_TMP_DIR"]) if os.environ.get("ANKIWEB_IMPORT_TMP_DIR") else (Path(os.environ.get("ANKIWEB_COLLECTION", str(default))).parent / "import-tmp"),
        )
