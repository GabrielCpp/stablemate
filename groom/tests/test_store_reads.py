"""Dashboard reads must not queue behind the writer's lock."""
from __future__ import annotations

import os
import sqlite3
import tempfile
import threading

import pytest

from _store_lock import HOLD_S, lock_held

from groom import store


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


def test_the_dashboard_queries_answer_while_the_write_lock_is_held():
    """Each panel the shell paints on a live tick, against a busy writer."""
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
            read()

        with lock_held():
            answered = [name for name, read in reads.items() if read() is not None]

    assert answered == list(reads)


def test_a_read_still_answers_after_the_writer_is_recycled_underneath_it():
    """A reopen invalidates every read handle; the next query opens a fresh one."""
    with _DB():
        store.insert_spans([_span("R1", "plan", 100.0)])
        assert len(store.query_spans(run="R1")) == 1
        store.STORE.recycle(sqlite3.OperationalError("wedged"), "test")
        assert len(store.query_spans(run="R1")) == 1


def test_each_thread_gets_its_own_handle_and_it_is_not_the_writers():
    with _DB():
        store.insert_spans([_span("R1", "plan", 100.0)])
        mine = store.read_connection()
        assert mine is store.read_connection()
        assert mine is not store._connection()

        theirs: list[sqlite3.Connection] = []
        thread = threading.Thread(target=lambda: theirs.append(store.read_connection()))
        thread.start()
        thread.join(HOLD_S)
        assert theirs and theirs[0] is not mine


def test_a_write_sent_down_the_read_path_is_refused():
    """`query_only` makes a misrouted write name itself instead of contending."""
    with _DB():
        store.insert_spans([_span("R1", "plan", 100.0)])
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            store.read_connection().execute("DELETE FROM spans")


def test_a_broken_read_handle_is_retired_without_disturbing_the_writer():
    with _DB():
        store.insert_spans([_span("R1", "plan", 100.0)])
        writer = store._connection()
        store.read_connection().close()

        assert len(store.query_spans(run="R1")) == 1
        assert store._connection() is writer


def test_reset_retires_the_calling_threads_handle():
    """Otherwise a test's handle outlives its database file into the next case."""
    with _DB():
        store.insert_spans([_span("R1", "plan", 100.0)])
        stale = store.read_connection()
    with _DB():
        store.insert_spans([_span("R2", "plan", 100.0)])
        assert store.read_connection() is not stale
        assert [s["run_id"] for s in store.query_spans()] == ["R2"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
