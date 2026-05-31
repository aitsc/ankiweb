from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar
from anki.collection import Collection
from ankiweb.config import Settings

T = TypeVar("T")


class CollectionService:
    """Owns the single Collection. All access is serialized: pylib objects are
    not thread-safe, and the Rust backend serializes internally anyway."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="anki")
        self._lock = asyncio.Lock()
        self._col: Collection | None = None

    async def open(self) -> None:
        path = self._settings.collection_path
        path.parent.mkdir(parents=True, exist_ok=True)

        def _open() -> Collection:
            return Collection(str(path), server=False)

        loop = asyncio.get_running_loop()
        self._col = await loop.run_in_executor(self._executor, _open)

    async def close(self) -> None:
        if self._col is None:
            return
        col, self._col = self._col, None
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, lambda: col.close())
        await loop.run_in_executor(None, self._executor.shutdown)

    async def run(self, fn: Callable[[Collection], T]) -> T:
        async with self._lock:
            col = self._col
            if col is None:
                raise RuntimeError("collection not open")
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, lambda: fn(col))
