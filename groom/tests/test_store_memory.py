"""Memory-bounding of the telemetry hot cache and the durable store.

Two growth vectors are covered:
- ``state.RUNS`` (and the native rows it backs) is evicted for finished/dead runs
  by :func:`alerts.stale_run_ids` + :func:`state.evict_runs`, so it stops growing
  one entry per distinct run for the life of the process;
- the fleet/telemetry scans (``run_summaries``/``live_status``) bound themselves to
  a recent window rather than the whole retained table, and the span/log searches
  accept a keyset cursor so a broad query pages instead of loading everything.

Run: uv run pytest tests/test_store_memory.py
"""
from __future__ import annotations

import os
import tempfile

from groom import alerts, state, store
from groom.models import RunTelemetry, WorkflowContainer


def _reset() -> None:
    state.WORKFLOWS.clear()
    state.RUNS.clear()
    state._gate_locks.clear()


class _DB:
    """A throwaway groom.db for the store tests, mirroring the telemetry suite."""

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
# RUNS eviction
# --------------------------------------------------------------------------- #
def test_terminated_run_evicted_after_grace():
    _reset()
    now = 10_000.0
    run = RunTelemetry(run_id="R1", first_seen_ts=now - 10_000, last_span_ts=now - 10_000)
    run.terminal = "terminal"
    state.RUNS["R1"] = run
    stale = alerts.stale_run_ids(now)
    assert "R1" in stale
    state.evict_runs(stale)
    assert "R1" not in state.RUNS


def test_live_run_is_not_evicted():
    _reset()
    now = 10_000.0
    run = RunTelemetry(run_id="R2", first_seen_ts=now - 60, last_heartbeat_ts=now - 5)
    state.RUNS["R2"] = run
    assert "R2" not in alerts.stale_run_ids(now)


def test_silent_run_evicted_past_dead_window():
    _reset()
    now = 1_000_000.0
    # No terminal, but silent for well over the 48h dead window → presumed gone.
    run = RunTelemetry(run_id="R3", first_seen_ts=0.0, last_heartbeat_ts=0.0)
    state.RUNS["R3"] = run
    assert "R3" in alerts.stale_run_ids(now)


def test_eviction_drops_the_native_row_but_not_docker_rows():
    _reset()
    state.RUNS["R4"] = RunTelemetry(run_id="R4", terminal="terminal")
    state.WORKFLOWS["R4"] = WorkflowContainer(container_id="R4", name="n", native=True)
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="d")
    state.evict_runs(["R4"])
    assert "R4" not in state.WORKFLOWS  # native row retired with its run
    assert "abc123" in state.WORKFLOWS  # docker row untouched (prune owns those)


# --------------------------------------------------------------------------- #
# Windowed scans + keyset pagination
# --------------------------------------------------------------------------- #
def _span(run_id, name, start, end, **extra):
    return {
        "span_id": f"{run_id}-{name}-{start}", "trace_id": "t", "parent_id": "",
        "run_id": run_id, "workflow": "coder", "repo": "", "branch": "", "node": name,
        "name": name, "run_dir": "", "start_ts": float(start), "end_ts": float(end),
        "status": "UNSET", "attrs": {}, **extra,
    }


def test_run_summaries_windows_out_old_runs():
    with _DB():
        now = 1_000_000.0
        store.insert_spans([_span("recent", "plan", now - 100, now - 90)])
        store.insert_spans([_span("ancient", "plan", 10, 20)])  # far outside the window
        ids = {s["run_id"] for s in store.run_summaries(now=now)}
        assert ids == {"recent"}


def test_query_spans_keyset_cursor_pages():
    with _DB():
        store.insert_spans([_span("R", "a", 100, 101)])
        store.insert_spans([_span("R", "b", 200, 201)])
        store.insert_spans([_span("R", "c", 300, 301)])
        first = store.query_spans(run="R", limit=2)
        assert [s["node"] for s in first] == ["c", "b"]  # newest first
        nxt = store.query_spans(run="R", limit=2, before_ts=first[-1]["start_ts"])
        assert [s["node"] for s in nxt] == ["a"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
