from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar
from anki.collection import Collection
from ankiweb.config import Settings
from google.protobuf.descriptor import FieldDescriptor

T = TypeVar("T")


def op_changes_to_flags(changes) -> dict:
    """Convert an OpChanges proto into a {field_name: bool} dict (only its bool fields)."""
    return {
        f.name: getattr(changes, f.name)
        for f in changes.DESCRIPTOR.fields
        if f.type == FieldDescriptor.TYPE_BOOL
    }


class CollectionService:
    """Owns the single Collection. All access is serialized: pylib objects are
    not thread-safe, and the Rust backend serializes internally anyway."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="anki")
        self._lock = asyncio.Lock()
        self._col: Collection | None = None
        self._subscribers: list = []

    @property
    def settings(self):
        return self._settings

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

    async def run_op(self, fn: Callable[[Collection], T], initiator: str | None = None) -> T:
        """Run a mutating op (fn returns OpChanges or an OpChanges* wrapper), then
        broadcast the change flags on the bus. Returns the op result unchanged."""
        result = await self.run(fn)
        changes = getattr(result, "changes", result)
        flags = op_changes_to_flags(changes)
        if any(flags.values()):  # skip no-op broadcasts (e.g. set_current returns all-False)
            await self.emit(flags, initiator)
        return result

    async def backend_raw(self, method: str, data: bytes) -> bytes:
        def fn(col):
            return getattr(col._backend, f"{method}_raw")(data)
        return await self.run(fn)

    def subscribe(self, cb) -> None:
        """cb(changes, initiator) — called after a mutating op broadcasts changes."""
        self._subscribers.append(cb)

    async def emit(self, changes, initiator) -> None:
        for cb in list(self._subscribers):
            res = cb(changes, initiator)
            if asyncio.iscoroutine(res):
                await res
