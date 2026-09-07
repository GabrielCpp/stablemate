"""Dashboard reads must not queue behind the writer's lock.

The second half of the wedge diagnosed in :mod:`tests.test_store_contention`:
even once an empty export stops taking the store lock, every *query* still took
it, because one process-wide connection behind one ``RLock`` was the whole store.
A single slow write therefore stalled the run list, the span search and the live
tick alike — the panels a person is watching go quiet for exactly as long as the
disk is busy, which is what "groom is unresponsive" looked like from the browser.

The invariant these tests pin: a read runs on this thread's own ``query_only``
connection, so it answers while the writer holds its lock and for as long as it
holds it, and a read handle that breaks is retired without touching the writer's.

Run: uv run pytest tests/test_store_reads.py
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from groom import store

# Mirrors the contention suite: long enough that queueing is unmistakable, short
# enough that a regression costs seconds rather than hanging the run.
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


def _span(run_id: str, node: str, start: float) -> dict[str, object]:
    return {
        "span_id": f"{run_id}-{node}-{start}", "trace_id": "t", "parent_id": "",
        "run_id": run_id, "workflow": "coder", "repo": "", "branch": "", "node": node,
        "name": node, "run_dir": "", "start_ts": start, "end_ts": start + 1,
        "status": "UNSET", "attrs": {},
    }


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
# reads answer while the writer holds the lock
# --------------------------------------------------------------------------- #
def test_the_dashboard_queries_answer_while_the_write_lock_is_held():
    """Each panel the shell paints on a live tick, against a busy writer.

    The reads are warmed first on purpose: opening a thread's handle *does* take
    the lock once, to create the file and run the migrations, and the guarantee
    being pinned here is about every query after that one.
    """
    with _DB():
        store.insert_spans([_span("R1", "plan", 100.0)])
        reads = {
            "query_spans": lambda: store.query_spans(run="R1"),
            "run_summaries": lambda: store.run_summaries(now=200.0),
            "query_logs": lambda: store.query_logs(run="R1"),
            "query_turns": lambda: store.query_turns(run="R1"),
            "run_profile": lambda: store.run_profile("R1"),
        }
        for read in reads.values():
            read()  # warm this thread's handle outside the measurement

        with _lock_held():
            waited = {name: _elapsed(read)[0] for name, read in reads.items()}

    slow = {name: round(s, 3) for name, s in waited.items() if s >= BUDGET_S}
    assert not slow, f"these reads queued for the write lock: {slow}"


def test_a_read_still_answers_after_the_writer_is_recycled_underneath_it():
    """A reopen invalidates every read handle; the next query opens a fresh one."""
    with _DB():
        store.insert_spans([_span("R1", "plan", 100.0)])
        assert len(store.query_spans(run="R1")) == 1
        store._STORE.recycle(sqlite3.OperationalError("wedged"), "test")
        assert len(store.query_spans(run="R1")) == 1


# --------------------------------------------------------------------------- #
# the handle itself
# --------------------------------------------------------------------------- #
def test_each_thread_gets_its_own_handle_and_it_is_not_the_writers():
    with _DB():
        store.insert_spans([_span("R1", "plan", 100.0)])
        mine = store._read_connection()
        assert mine is store._read_connection()  # cached for this thread
        assert mine is not store._connection()  # never the writer's

        theirs: list[sqlite3.Connection] = []
        thread = threading.Thread(target=lambda: theirs.append(store._read_connection()))
        thread.start()
        thread.join(HOLD_S)
        assert theirs and theirs[0] is not mine


def test_a_write_sent_down_the_read_path_is_refused():
    """`query_only` makes a misrouted write name itself instead of contending."""
    with _DB():
        store.insert_spans([_span("R1", "plan", 100.0)])
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            store._read_connection().execute("DELETE FROM spans")


def test_a_broken_read_handle_is_retired_without_disturbing_the_writer():
    with _DB():
        store.insert_spans([_span("R1", "plan", 100.0)])
        writer = store._connection()
        store._read_connection().close()  # what a recycled handle looks like

        assert len(store.query_spans(run="R1")) == 1  # healed on the one retry
        assert store._connection() is writer  # the writer was left alone


def test_reset_retires_the_calling_threads_handle():
    """Otherwise a test's handle outlives its database file into the next case."""
    with _DB():
        store.insert_spans([_span("R1", "plan", 100.0)])
        stale = store._read_connection()
    with _DB():
        store.insert_spans([_span("R2", "plan", 100.0)])
        assert store._read_connection() is not stale
        assert [s["run_id"] for s in store.query_spans()] == ["R2"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
