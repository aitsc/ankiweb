import time
from pathlib import Path
import anyio
import pytest
from fastapi.testclient import TestClient
from ankiweb.config import Settings
from ankiweb.collection_service import CollectionService
from ankiweb.app import create_app


def test_concurrent_path_not_blocked_by_busy_main_worker(tmp_path: Path):
    """latest_progress (CONCURRENT) must return promptly even while the single main
    worker is busy with a long op — that's what makes FSRS progress observable."""
    async def _run():
        import asyncio
        svc = CollectionService(Settings(collection_path=tmp_path / "c.anki2"))
        await svc.open()
        try:
            busy = asyncio.create_task(svc.run(lambda col: time.sleep(0.6)))  # occupy main worker
            await asyncio.sleep(0.05)                                          # let it start
            t0 = asyncio.get_running_loop().time()
            out = await svc.backend_raw_concurrent("latest_progress", b"")     # aux pool
            dt = asyncio.get_running_loop().time() - t0
            await busy
            assert out is not None
            assert dt < 0.3, f"concurrent call blocked by the busy worker (took {dt:.2f}s)"
        finally:
            await svc.close()
    anyio.run(_run)


def test_concurrent_methods_are_segregated():
    from ankiweb.anki_rpc.passthrough import PASSTHROUGH, CONCURRENT
    for m in ("latest_progress", "set_wants_abort", "compute_fsrs_params",
              "evaluate_params_legacy", "compute_optimal_retention",
              "simulate_fsrs_review", "simulate_fsrs_workload", "get_retention_workload"):
        assert m in CONCURRENT and m not in PASSTHROUGH, m


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(collection_path=tmp_path / "c.anki2"))) as c:
        yield c


def test_latest_progress_rpc_served(client):
    r = client.post("/_anki/latestProgress", content=b"",
                    headers={"content-type": "application/binary"})
    assert r.status_code == 200      # served via the concurrent path (idle → Progress.none)
