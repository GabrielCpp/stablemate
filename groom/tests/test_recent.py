"""Tests for :func:`groom.cli.recent` and :func:`groom.store.recent_runs`.

The CLI fills the dashboard gap :func:`status` leaves: ``status`` answers
"*is this run alive right now?*" from the running server's in-memory
heartbeat cache; ``recent`` answers "*what's the most recent telemetry for
every run the database has rows for, alive or dead, ordered by that
recency?*" from SQLite alone, with no ``groom serve`` in the picture. The
seam here is the focused store helper and the formatting/filtering it
drives — runs ordered by their latest metric or span timestamp, with a
single grouped pass of indexed queries so an interactive ``-n 10`` returns
in well under a second on the 1.4GB production store.

Run: ``uv run pytest tests/test_recent.py``
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

import pytest

from groom import store
from groom.cli import recent
from groom.store import recent_runs


DAY = 86400.0


@contextmanager
def _temp_db():
    """A throwaway ``$GROOM_DB`` so each test owns a fresh schema."""
    tmp = tempfile.TemporaryDirectory()
    prev = os.environ.get("GROOM_DB")
    os.environ["GROOM_DB"] = str(Path(tmp.name) / "groom.db")
    store.reset()
    try:
        yield
    finally:
        store.reset()
        if prev is None:
            os.environ.pop("GROOM_DB", None)
        else:
            os.environ["GROOM_DB"] = prev
        tmp.cleanup()


def _span(run_id: str, *, ts: float, workflow: str = "okf-builder") -> dict:
    """A minimal span the store will accept.

    Span / status fields are the columns ``insert_spans`` writes; this test
    only keys on ``run_id`` and the timestamps, so the rest is collapsed to
    the empty strings the schema accepts."""
    return {
        "span_id": f"sp_{run_id}_{ts}",
        "trace_id": "tr_a",
        "parent_id": "",
        "run_id": run_id,
        "workflow": workflow,
        "repo": "",
        "branch": "",
        "node": "investigate",
        "name": "investigate",
        "run_dir": "",
        "start_ts": ts,
        "end_ts": ts + 0.5,
        "status": "UNSET",
        "attrs": {},
    }


def _metric(run_id: str, *, ts: float) -> dict:
    return {
        "run_id": run_id,
        "name": "workhorse.turn.elapsed_s",
        "ts": ts,
        "value": 1.0,
        "attrs": {},
    }


def _capture_recent(**kwargs) -> str:
    """Run :func:`recent` with stdout captured; return the printed text."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        recent(**kwargs)
    return buf.getvalue()


def test_recent_runs_orders_by_merged_span_and_metric_recency() -> None:
    """Two runs that emitted a span at the same minute but metrics at different
    minutes: the one whose metrics are fresher wins. The ranking is the merge
    of the two streams, not whichever one was queried last."""
    with _temp_db():
        now = 100 * DAY
        store.insert_spans([_span("alpha", ts=now - 100), _span("beta", ts=now - 50)])
        store.insert_metrics(
            [
                _metric(
                    "alpha", ts=now
                ),  # alpha's heartbeats are fresher than its spans
                _metric("beta", ts=now - 200),
            ]
        )
        rows = recent_runs(limit=10)
        assert [row.run_id for row in rows] == ["alpha", "beta"], (
            "alpha has the most recent heartbeats, beta has the most recent spans;"
            " merged ranking must put alpha first because metrics dominate liveness"
        )


def test_recent_runs_limit_is_enforced_post_merge() -> None:
    """``limit`` lands after the metrics merge, not after the spans scan —
    the screening pass widens because a run dead by its last span but live by
    its last heartbeat still belongs in the top N."""
    with _temp_db():
        now = 100 * DAY
        for i in range(20):
            store.insert_spans([_span(f"run_{i:02d}", ts=now - i * 100)])
        # Now overwrite run_5's recency with a fresh metric — its old span
        # says one hour ago, but it just heartbeated. Without the merge it
        # would still rank by old span and miss the ``-n 5`` cut unless the
        # spans query happened to widen enough.
        store.insert_metrics([_metric("run_05", ts=now + 1000)])
        rows = recent_runs(limit=5)
        assert "run_05" in {row.run_id for row in rows}, (
            "the metrics-fresh run must survive the -n 5 cut; "
            "got runs: " + ",".join(row.run_id for row in rows)
        )


def test_recent_runs_filters_by_workflow() -> None:
    """``workflow=`` lands at SQL level on the spans scan, not in Python
    filtering after the merge — the metrics lookup is bounded to the
    spans-seen runs, so a wide Python-level filter would still pull
    every metric row."""
    with _temp_db():
        now = 100 * DAY
        store.insert_spans(
            [
                _span("a1", ts=now, workflow="okf-builder"),
                _span("a2", ts=now, workflow="okf-builder"),
                _span("b1", ts=now, workflow="coder"),
                _span("b2", ts=now, workflow="coder"),
            ]
        )
        okf = {row.run_id for row in recent_runs(workflow="okf-builder", limit=10)}
        coder = {row.run_id for row in recent_runs(workflow="coder", limit=10)}
        assert okf == {"a1", "a2"}
        assert coder == {"b1", "b2"}


def test_recent_runs_zero_limit_returns_every_run() -> None:
    """``limit=0`` is the operator's \"everything sorted by recency\" — used
    here for archival sweeps where top N is not the question."""
    with _temp_db():
        now = 100 * DAY
        for i in range(10):
            store.insert_spans([_span(f"r{i:02d}", ts=now - i * 100)])
        rows = recent_runs(limit=0)
        assert len(rows) == 10


def test_recent_runs_metadata_round_trips() -> None:
    """Workflow comes from the spans table at the group-by level — the
    helper doesn't reach for ``run_bounds`` to fill it, the SQL does."""
    with _temp_db():
        now = 100 * DAY
        store.insert_spans([_span("c1", ts=now, workflow="groom")])
        rows = recent_runs(limit=10)
        assert len(rows) == 1
        assert rows[0].workflow == "groom"
        assert rows[0].spans == 1


def test_recent_cli_alive_flag_uses_metric_heartbeat_not_span_close() -> None:
    """``alive`` follows the metrics-side timestamp, the same source the
    dashboard liveness chip keys on. A run with no spans closed in 30 min
    but a heartbeating heartbeat 30s ago is alive — the dashboard would
    show it alive, so ``recent`` does too.

    This is the property the merge buys; without it the helper would say
    \"dead\" for every long-running node visit (which closes its span after
    minutes of work) and the operator would lose every live, busy run.
    """
    with _temp_db():
        now = time.time()
        store.insert_spans([_span("busy", ts=now - 1800)])  # span closed 30 min ago
        store.insert_metrics([_metric("busy", ts=now - 30)])  # heartbeat 30 s ago

        out = _capture_recent(limit=5, alive_since_s=180.0)
        assert "busy" in out, "the heartbeating run must render with the alive marker"
        assert " alive " in out, f"expected ' alive ' column marker; got:\n{out}"


def test_recent_cli_dead_flag_for_run_older_than_threshold() -> None:
    """The counterpart: a run whose last telemetry is past the threshold
    is dead, regardless of recency."""
    with _temp_db():
        now = time.time()
        store.insert_spans([_span("yesterday", ts=now - 86400)])
        store.insert_metrics([_metric("yesterday", ts=now - 86400)])

        out = _capture_recent(limit=5, alive_since_s=180.0)
        assert "yesterday" in out
        assert " dead " in out, f"expected ' dead ' marker; got:\n{out}"


def test_recent_cli_workflow_filter_appears_in_empty_message() -> None:
    """When the workflow filter excludes every run, the empty-path print
    surfaces the filter — an empty ``recent --workflow foo`` should be
    diagnosable from the output alone, not by re-running it."""
    with _temp_db():
        store.insert_spans([_span("only", ts=100.0, workflow="okf-builder")])
        out = _capture_recent(limit=5, workflow="coder")
        assert "workflow filter" in out
        assert "'coder'" in out


def test_recent_cli_json_has_alive_ts_and_workflow() -> None:
    """``--json`` is the machine-readable surface; the loads()ed shape is what
    a dashboard or alert tool would key on. Pin the keys here so a
    downstream consumer's parse doesn't silently drift."""
    with _temp_db():
        store.insert_spans([_span("live", ts=1_000_000_000.0, workflow="okf-builder")])
        out = _capture_recent(limit=5, as_json=True)
        rows = json.loads(out)
        assert len(rows) == 1
        row = rows[0]
        assert set(row.keys()) >= {"run", "workflow", "last_seen", "alive", "spans"}
        assert row["run"] == "live"
        assert row["workflow"] == "okf-builder"
        assert isinstance(row["alive"], bool)


def test_recent_cli_empty_db_prints_diagnostic() -> None:
    """An empty DB gets an actionable message rather than a silent no-rows
    silence — the operator wants to know the path is wired, not that the
    answer is ``nothing``.
    """
    with _temp_db():
        out = _capture_recent(limit=5)
        assert "no runs found in" in out
        assert "groom.db" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
