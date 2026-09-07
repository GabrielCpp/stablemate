"""Ingest that has nothing to store must not queue behind the store lock.

Diagnosed from a live wedge: groom stopped ingesting for minutes at a time while
plain GETs kept answering in milliseconds. One thread sat in a page-cache read
holding the process-wide store lock, and :func:`store._resilient` takes that lock
*before* the writer it wraps can decide the batch is empty — so every other
ingest thread piled up behind it, including the no-op exports that are most of
what a fleet of mostly-idle exporters sends. Those waits exhausted the shared
thread pool, the dashboard's own live tick could no longer reach the store, and
the browser read the resulting silence as a dead connection.

The invariant these tests pin: a batch with no rows in it is answered without
ever touching the lock, and a batch that does carry rows still lands.

Run: uv run pytest tests/test_store_contention.py
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

from groom import store
from groom.models import LIVENESS_METRICS

# Long enough that a call which waits for the lock cannot be mistaken for a slow
# one, short enough that a regression costs a couple of seconds rather than a
# hung suite.
HOLD_S = 2.0
# A call that never takes the lock does no I/O at all; anything near HOLD_S means
# it queued.
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


# --------------------------------------------------------------------------- #
# an empty batch never reaches the lock
# --------------------------------------------------------------------------- #
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
    """The heartbeats are dropped rather than stored, so the batch has no rows.

    They were ~80% of everything this table ever saw, which makes the all-ticks
    batch the single most common thing arriving at the metrics receiver.
    """
    ticks = [{"run_id": "R1", "name": name, "ts": 1.0, "value": 1.0} for name in LIVENESS_METRICS]
    with _lock_held():
        waited, _ = _elapsed(lambda: store.insert_metrics(ticks))
    assert waited < BUDGET_S, f"a liveness-only batch queued for the lock ({waited:.3f}s)"


# --------------------------------------------------------------------------- #
# a batch with rows in it still lands
# --------------------------------------------------------------------------- #
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
