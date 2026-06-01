from __future__ import annotations
import secrets
import time
from pathlib import Path


def dir(settings) -> Path:
    d = Path(settings.import_tmp_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def allocate(settings, ext: str) -> Path:
    return dir(settings) / (secrets.token_hex(8) + ext)


def is_within(settings, candidate: str) -> bool:
    base = dir(settings).resolve()
    try:
        Path(candidate).resolve().relative_to(base)
        return True
    except (ValueError, OSError):
        return False


def gc(settings, ttl_seconds: int = 3600) -> None:
    base = dir(settings)
    now = time.time()
    for f in base.iterdir():
        try:
            if f.is_file() and now - f.stat().st_mtime > ttl_seconds:
                f.unlink()
        except OSError:
            pass
