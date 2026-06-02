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
        # Auxiliary pool for thread-safe Rust backend calls that must run CONCURRENTLY
        # with the main worker (FSRS compute/simulate + latest_progress polling +
        # set_wants_abort) so progress is observable while a long compute runs.
        self._aux_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="anki-aux")
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
            import anki.lang
            anki.lang.set_lang(self._settings.lang or "en")
            return Collection(str(path), server=False)

        loop = asyncio.get_running_loop()
        self._col = await loop.run_in_executor(self._executor, _open)

    async def reopen(self) -> None:
        """Re-open the collection on the worker WITHOUT shutting it down — for ops
        that close it (export_collection_package). Unlike close(), keeps the executor."""
        path = self._settings.collection_path
        loop = asyncio.get_event_loop()
        async with self._lock:
            self._col = await loop.run_in_executor(
                self._executor, lambda: Collection(str(path), server=False))

    async def close(self) -> None:
        if self._col is None:
            return
        col, self._col = self._col, None
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, lambda: col.close())
        await loop.run_in_executor(None, self._executor.shutdown)
        await loop.run_in_executor(None, self._aux_executor.shutdown)

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

    async def backend_raw_concurrent(self, method: str, data: bytes) -> bytes:
        """Call `col._backend.<method>_raw` OFF the serialized main worker, on the aux
        pool, so it runs CONCURRENTLY with the main worker and with other aux calls.
        ONLY for thread-safe Rust backend calls that don't mutate Python-side collection
        state: FSRS compute/simulate (long, read-only), `latest_progress` (polled while
        they run), and `set_wants_abort` (cancels them). The Rust backend serializes its
        own collection access internally; `latest_progress` uses a separate lock, so it
        returns live progress while a compute holds the collection lock."""
        col = self._col
        if col is None:
            raise RuntimeError("collection not open")
        fn = getattr(col._backend, f"{method}_raw")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._aux_executor, lambda: fn(data))

    def subscribe(self, cb) -> None:
        """cb(changes, initiator) — called after a mutating op broadcasts changes."""
        self._subscribers.append(cb)

    async def emit(self, changes, initiator) -> None:
        for cb in list(self._subscribers):
            res = cb(changes, initiator)
            if asyncio.iscoroutine(res):
                await res
