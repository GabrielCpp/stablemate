"""Ingest that has nothing to store must not queue behind the store lock."""
from __future__ import annotations

import os
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

from groom import store
from groom.models import LIVENESS_METRICS

HOLD_S = 2.0
BUDGET_S = 0.25


@contextmanager
def _lock_held() -> Iterator[None]:
    """Hold the process-wide store lock from another thread for the block."""
    holding = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with store._STORE.lock:
            holding.set()
            release.wait(HOLD_S)

    thread = threading.Thread(target=hold, daemon=True)
    thread.start()
    assert holding.wait(HOLD_S), "the holder thread never acquired the store lock"
    try:
        yield
    finally:
        release.set()
        thread.join(HOLD_S)


def _elapsed(call) -> tuple[float, object]:
    start = time.monotonic()
    result = call()
    return time.monotonic() - start, result


class _DB:
    """A throwaway groom.db, mirroring the memory-bounding suite."""

    def __enter__(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._prev = os.environ.get("GROOM_DB")
        os.environ["GROOM_DB"] = self._tmp.name
        store.reset()
        return self

    def __exit__(self, *exc):
        store.reset()
        if self._prev is None:
            os.environ.pop("GROOM_DB", None)
        else:
            os.environ["GROOM_DB"] = self._prev
        os.unlink(self._tmp.name)


def test_empty_span_batch_does_not_wait_for_the_store_lock():
    with _lock_held():
        waited, _ = _elapsed(lambda: store.insert_spans([]))
    assert waited < BUDGET_S, f"insert_spans([]) queued for the lock ({waited:.3f}s)"


def test_empty_log_batch_does_not_wait_for_the_store_lock():
    with _lock_held():
        waited, _ = _elapsed(lambda: store.insert_logs([]))
    assert waited < BUDGET_S, f"insert_logs([]) queued for the lock ({waited:.3f}s)"


def test_empty_turn_batch_does_not_wait_for_the_store_lock():
    with _lock_held():
        waited, indexed = _elapsed(lambda: store.insert_turns([]))
    assert waited < BUDGET_S, f"insert_turns([]) queued for the lock ({waited:.3f}s)"
    assert indexed == 0


def test_liveness_only_metric_batch_does_not_wait_for_the_store_lock():
    """The heartbeats are dropped rather than stored, so the batch has no rows."""
    ticks = [{"run_id": "R1", "name": name, "ts": 1.0, "value": 1.0} for name in LIVENESS_METRICS]
    with _lock_held():
        waited, _ = _elapsed(lambda: store.insert_metrics(ticks))
    assert waited < BUDGET_S, f"a liveness-only batch queued for the lock ({waited:.3f}s)"


def test_non_empty_batches_still_write():
    with _DB():
        assert store.insert_turns([{
            "run_id": "R1", "workflow": "wf", "node": "n", "session_id": "s",
            "generation": 0, "seq": 1, "ts": 1.0, "path": "p", "bytes": 1,
        }]) == 1
        assert len(store.query_turns(run="R1")) == 1

        store.insert_metrics([
            {"run_id": "R1", "name": LIVENESS_METRICS[0], "ts": 1.0, "value": 1.0},
            {"run_id": "R1", "name": "workhorse.turn.tokens", "ts": 1.0, "value": 7.0},
        ])
        stored = store._connection().execute("SELECT name FROM metrics").fetchall()
        assert [row["name"] for row in stored] == ["workhorse.turn.tokens"]
