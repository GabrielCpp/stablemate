"""Ingest and the dashboard's reads each get a pool of their own."""
from __future__ import annotations

import asyncio
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from _settle import until
from litestar.testing import TestClient

from groom import app as groom_app
from groom import discovery, pools, state, store
from tests.test_telemetry import _trace_request

HOLD_S = 30.0


@contextmanager
def _fresh_pools() -> Iterator[None]:
    """Pools built inside the block and disposed after, so no test leaks threads."""
    pools.shutdown_all()
    try:
        yield
    finally:
        pools.shutdown_all()


@contextmanager
def _db() -> Iterator[None]:
    """A throwaway groom.db, mirroring the telemetry suite's env."""
    with tempfile.TemporaryDirectory() as tmp:
        previous = os.environ.get("GROOM_DB")
        os.environ["GROOM_DB"] = str(Path(tmp) / "groom.db")
        store.reset()
        state.RUNS.clear()
        try:
            yield
        finally:
            store.reset()
            state.RUNS.clear()
            if previous is None:
                os.environ.pop("GROOM_DB", None)
            else:
                os.environ["GROOM_DB"] = previous


def _hermetic_client() -> TestClient:
    with patch.object(discovery, "scan", return_value=[]), \
         patch.object(discovery, "present_container_ids", return_value=None):
        client = TestClient(app=groom_app.create_app())
        client.__enter__()
    return client


def test_ingest_and_query_hold_different_executors():
    with _fresh_pools():
        assert pools.INGEST.executor() is not pools.QUERY.executor()


def test_ingest_does_not_run_on_the_shared_default_executor():
    """The whole point: a thread taken here is not a thread docker could have had."""

    async def probe() -> tuple[str, str]:
        mine = await pools.INGEST.run(threading.current_thread)
        default = await asyncio.to_thread(threading.current_thread)
        return mine.name, default.name

    with _fresh_pools():
        ingest_thread, default_thread = asyncio.run(probe())
    assert ingest_thread.startswith("groom-ingest")
    assert not default_thread.startswith("groom-")


def test_a_saturated_ingest_pool_does_not_delay_a_dashboard_read():
    """Ingest wedged on the disk must not be what stops the UI from updating."""
    release = threading.Event()
    arrived: list[int] = []

    def hold(seconds: float) -> bool:
        arrived.append(1)
        return release.wait(seconds)

    async def probe() -> list[bool]:
        blocked = [
            asyncio.ensure_future(pools.INGEST.run(hold, HOLD_S))
            for _ in range(pools.INGEST.workers * 2)
        ]
        await until(lambda: len(arrived) == pools.INGEST.workers, "every ingest worker holding")
        await pools.QUERY.run(lambda: None)
        release.set()
        return await asyncio.gather(*blocked)

    with _fresh_pools():
        released = asyncio.run(probe())
    assert all(released), "the dashboard read queued behind ingest until a worker gave up its wait"


def test_the_trace_receiver_stores_through_the_ingest_pool():
    used: list[str] = []
    original = pools.INGEST.run

    async def recording(fn, /, *args, **kwargs):
        used.append(getattr(fn, "__name__", repr(fn)))
        return await original(fn, *args, **kwargs)

    with _fresh_pools(), _db():
        client = _hermetic_client()
        try:
            with patch.object(pools.INGEST, "run", recording):
                response = client.post(
                    "/v1/traces",
                    content=_trace_request([{"name": "plan", "node": "plan"}]),
                    headers={"content-type": "application/x-protobuf"},
                )
        finally:
            client.__exit__(None, None, None)
    assert response.status_code == 200
    assert used == ["insert_spans"]


def test_worker_count_reads_the_environment_and_refuses_zero():
    with _fresh_pools(), patch.dict(os.environ, {"GROOM_INGEST_WORKERS": "7"}):
        assert pools.INGEST.workers == 7
    with _fresh_pools(), patch.dict(os.environ, {"GROOM_INGEST_WORKERS": "0"}):
        assert pools.INGEST.workers == 1
    with _fresh_pools(), patch.dict(os.environ, {"GROOM_INGEST_WORKERS": "many"}):
        assert pools.INGEST.workers == pools.INGEST_WORKERS_DEFAULT
