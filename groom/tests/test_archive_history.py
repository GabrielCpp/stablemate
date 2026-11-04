"""Archives in History: the summary stored at archive time, the older archives read once, and the routes that open them."""
from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from litestar.testing import TestClient
from test_history import seed
from test_run_clock import _DB

from groom import archive, figures, history, medians, overview, pools, state, store
from groom import app as groom_app

DAY = 86400.0


def _archived(run: str, now: float, age_days: float = 60.0, costs: tuple[float | None, ...] = (2.0, 1.0)) -> Path:
    seed(run, now - age_days * DAY, costs=costs)
    found = store.run_bounds()[run]
    destination, _ = archive.archive_run(found, now)
    assert destination is not None
    return destination


def _digest(path: Path) -> str:
    return hashlib.sha256((path / archive.TELEMETRY_FILE).read_bytes()).hexdigest()


def _without_summary(folder: Path) -> None:
    target = folder / archive.TELEMETRY_FILE
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    first = json.loads(lines[0])
    first.pop("summary", None)
    lines[0] = json.dumps(first) + "\n"
    target.write_text("".join(lines), encoding="utf-8")
    _forget(folder.name)


def _forget(run: str) -> None:
    with store.STORE.writing() as conn:
        conn.execute("DELETE FROM run_summary WHERE run_id = ?", (run,))


def _settle_pending() -> None:
    for run_id in history.discover_archives():
        history.compute_archive(run_id)


def test_the_manifest_of_a_new_archive_carries_the_summary_computed_before_its_rows_were_dropped() -> None:
    now = time.time()
    with _DB():
        seed("run-a", now - 60 * DAY, costs=(2.0, 1.0))
        history.compute("run-a", now)
        expected = history.stored("run-a")
        folder = _archived("run-b", now)
        first = archive.manifest(folder)
        assert store.query_spans(run="run-b") == []
    assert expected is not None
    assert first["summary"]["run_id"] == "run-b"
    assert first["summary"]["cost_usd"] == 3.0
    assert first["summary"]["state"] == history.READY


def test_an_archived_run_keeps_a_summary_row_flagged_archived_and_listed_only_with_archives() -> None:
    now = time.time()
    with _DB():
        _archived("run-old", now)
        row = history.stored("run-old")
        plain = history.listing(set(), now)
        wide = history.listing(set(), now, archives=True)
    assert row is not None and row["archived"] == 1
    assert [item["run_id"] for item in plain["runs"]] == []
    assert [item["run_id"] for item in wide["runs"]] == ["run-old"]
    assert wide["runs"][0]["archived"] is True
    assert wide["unlisted"] == 0


def test_an_older_archive_without_a_summary_gets_a_pending_row_from_its_manifest() -> None:
    now = time.time()
    with _DB():
        folder = _archived("run-older", now)
        _without_summary(folder)
        pending = history.discover_archives()
        item = history.listing(set(), now, archives=True)["runs"][0]
    assert pending == ["run-older"]
    assert (item["run_id"], item["ready"], item["unreadable"], item["archived"]) == ("run-older", False, False, True)
    assert item["workflow"] == "coder"
    assert item["ended_ts"] is not None


def test_the_listing_counts_the_archives_no_row_stands_for_yet_and_discovery_clears_it() -> None:
    now = time.time()
    with _DB():
        folder = _archived("run-older", now)
        _without_summary(folder)
        before = history.listing(set(), now, archives=True)["unlisted"]
        history.discover_archives()
        after = history.listing(set(), now, archives=True)["unlisted"]
    assert (before, after) == (1, 0)


def test_one_background_read_fills_the_pending_row_without_rewriting_the_frozen_file() -> None:
    now = time.time()
    with _DB():
        folder = _archived("run-older", now, costs=(2.0, 1.0))
        _without_summary(folder)
        frozen = _digest(folder)
        history.discover_archives()
        assert history.compute_archive("run-older", now) is True
        row = history.stored("run-older")
        after = _digest(folder)
    assert row is not None
    assert (row["state"], row["archived"], row["cost_usd"]) == (history.READY, 1, 3.0)
    assert after == frozen


def test_an_archive_that_cannot_be_read_keeps_its_row_marked_unreadable_and_a_retry_asks_again() -> None:
    now = time.time()
    with _DB():
        folder = _archived("run-older", now)
        _without_summary(folder)
        history.discover_archives()
        with patch.object(archive, "build_index", side_effect=OSError("disk gone")):
            assert history.compute_archive("run-older", now) is False
        item = history.listing(set(), now, archives=True)["runs"][0]
        totals = history.listing(set(), now, archives=True)["totals"]
        asked = history.retry("run-older")
        waiting = history.stored("run-older")
        nothing = history.retry("run-older")
    assert (item["unreadable"], item["ready"]) == (True, False)
    assert (totals["unreadable"], totals["reading"]) == (1, 0)
    assert asked is True and waiting is not None and waiting["state"] == history.PENDING
    assert nothing is False


def test_a_retry_changes_nothing_for_a_run_that_is_not_an_unreadable_archive() -> None:
    now = time.time()
    with _DB():
        seed("run-live", now - 3600)
        history.compute("run-live", now)
        asked = history.retry("run-live")
        unknown = history.retry("nope")
    assert (asked, unknown) == (False, False)


def test_a_derived_archive_folder_name_does_not_get_a_second_row() -> None:
    now = time.time()
    with _DB():
        folder = _archived("run-older", now)
        extra = folder.with_name("run-older-" + "ab12cd34")
        extra.mkdir()
        (extra / archive.TELEMETRY_FILE).write_text((folder / archive.TELEMETRY_FILE).read_text(encoding="utf-8"), encoding="utf-8")
        history.discover_archives()
        runs = [item["run_id"] for item in history.listing(set(), now, archives=True)["runs"]]
    assert runs == ["run-older"]


def test_the_listing_reads_no_telemetry_file_per_row() -> None:
    now = time.time()
    with _DB():
        for index in range(5):
            _archived(f"run-{index}", now, age_days=40 + index)
        with patch.object(archive, "build_index", side_effect=AssertionError("opened")), patch.object(archive, "manifest", side_effect=AssertionError("opened")):
            body = history.listing(set(), now, archives=True)
    assert len(body["runs"]) == 5


def _summary(run: str, ended: float, cost: float = 4.0) -> dict:
    return {
        "run_id": run, "workflow": "coder", "repo": "acme", "branch": "main", "state": "ready", "ending": "success",
        "ended_ts": ended, "last_ts": ended, "active_s": 60.0, "wall_s": 90.0, "cost_usd": cost, "priced_turns": 2,
        "turns": 2, "items_done": 2, "items_total": 2, "gates": 0, "problems": 0, "archived": 1,
    }


def test_the_median_is_taken_over_the_store_and_the_archives_together() -> None:
    now = time.time()
    with _DB():
        for index in range(5):
            history._write(_summary(f"run-archived-{index}", now - (40 + index) * DAY))
        history._write({**_summary("run-live", now - 3600, cost=8.0), "archived": 0})
        pool = medians.per_item_costs(set())
        judged = history.listing(set(), now, archives=True)["runs"][0]
    assert sorted(pool["coder"]) == sorted([f"run-archived-{index}" for index in range(5)] + ["run-live"])
    assert judged["run_id"] == "run-live"
    assert judged["vs_runs"] == 5
    assert judged["vs_median_usd"] == 2.0
    assert judged["vs_pct"] == pytest.approx(100.0)


def test_an_archived_runs_cost_and_times_per_node_and_flow_equal_the_terminal_reports() -> None:
    now = time.time()
    with _DB():
        seed("run-equal", now - 60 * DAY, costs=(2.0, 1.0, None))
        history.compute("run-equal", now)
        live_costs, live_profile, _ = figures.read("run-equal")
        live = overview.run_overview("run-equal")
        archive.archive_run(store.run_bounds()["run-equal"], now)
        assert store.query_spans(run="run-equal") == []
        found = groom_app._archive_overview("run-equal")
        with archive.run_source("run-equal"):
            costs, profile, _ = figures.read("run-equal")
    assert found is not None and found["archive"] == "ready"
    assert costs == live_costs and profile == live_profile
    assert found["figures"]["cost_usd"] == live_costs["usd"] == 3.0
    assert found["cost"] == live["cost"]
    assert found["flows"] == live["flows"]
    assert found["nodes"] == live["nodes"]
    assert found["time_s"] == live["time_s"]
    assert live_profile is not None
    assert found["clock"] == live["clock"] == live_profile["time_s"]


def test_the_archive_route_reads_an_archive_by_its_exact_id_inside_the_pool_thread() -> None:
    now = time.time()
    with _DB():
        _archived("run-route", now)
        state.RUNS.clear()
        with TestClient(app=groom_app.create_app()) as client:
            body = client.get("/api/archive/run-route/overview")
            prefix = client.get("/api/archive/run-rou/overview")
            missing = client.get("/api/archive/nope/overview")
            traversal = client.get("/api/archive/..%2F/overview")
    assert body.status_code == 200
    assert body.json()["archive"] == "ready"
    assert body.json()["figures"]["cost_usd"] == 3.0
    assert (prefix.status_code, missing.status_code) == (404, 404)
    assert traversal.status_code == 404


def test_the_archive_route_does_not_open_a_run_the_live_store_still_holds() -> None:
    now = time.time()
    with _DB():
        seed("run-live", now - 3600)
        history.compute("run-live", now)
        with TestClient(app=groom_app.create_app()) as client:
            answer = client.get("/api/archive/run-live/overview")
    assert answer.status_code == 404


def test_an_archive_whose_telemetry_file_is_gone_answers_from_the_stored_summary() -> None:
    now = time.time()
    with _DB():
        folder = _archived("run-gone", now, costs=(2.0, 1.0))
        with TestClient(app=groom_app.create_app()) as client:
            ready = client.get("/api/archive/run-gone/overview").json()
        (folder / archive.TELEMETRY_FILE).unlink()
        with TestClient(app=groom_app.create_app()) as client:
            body = client.get("/api/archive/run-gone/overview").json()
            rows = client.get("/api/history?archives=1").json()["runs"]
    assert body["archive"] == "gone"
    assert body["figures"]["cost_usd"] == 3.0
    assert body["figures"]["turns"] == 2
    assert body["standing"]["retries"] == ready["standing"]["retries"]
    assert body["facts"]["started_ts"] is None
    assert body["facts"]["branch"]
    assert [row["run_id"] for row in rows] == ["run-gone"]


def test_the_retry_route_puts_an_unreadable_summary_back_in_the_queue() -> None:
    now = time.time()
    with _DB():
        folder = _archived("run-older", now)
        _without_summary(folder)
        history.discover_archives()
        with patch.object(archive, "build_index", side_effect=OSError("x")):
            history.compute_archive("run-older", now)
        with patch.object(groom_app, "_summary_pass", AsyncMock(return_value=0)), TestClient(app=groom_app.create_app()) as client:
            answer = client.post("/api/history/run-older/retry")
        row = history.stored("run-older")
    assert answer.status_code in (200, 201)
    assert row is not None and row["state"] == history.PENDING


def test_a_summary_pass_reads_the_older_archives_on_the_archive_pool() -> None:
    now = time.time()
    with _DB():
        folder = _archived("run-older", now)
        _without_summary(folder)
        with patch.object(groom_app, "SUMMARY_PAUSE_S", 0.0), patch.object(groom_app, "_summary_wake", None):
            asyncio.run(groom_app._summary_pass())
        row = history.stored("run-older")
    assert row is not None and row["state"] == history.READY


def test_archive_reads_have_a_pool_of_their_own_so_the_dashboard_queries_never_wait_on_them() -> None:
    assert pools.ARCHIVE in pools.ALL
    assert pools.ARCHIVE is not pools.QUERY
    assert pools.ARCHIVE is not pools.SUMMARY
    assert pools.ARCHIVE.workers >= 1


def test_history_answers_while_every_archive_read_worker_is_busy() -> None:
    now = time.time()
    release = threading.Event()
    started = threading.Barrier(pools.ARCHIVE.workers + 1)

    def hold() -> None:
        started.wait(timeout=10)
        release.wait(timeout=30)

    with _DB():
        _archived("run-old", now)
        holders = [pools.ARCHIVE.executor().submit(hold) for _ in range(pools.ARCHIVE.workers)]
        try:
            started.wait(timeout=10)
            began = time.perf_counter()
            with TestClient(app=groom_app.create_app()) as client:
                body = client.get("/api/history?archives=1").json()
            took = time.perf_counter() - began
        finally:
            release.set()
            for holder in holders:
                holder.result(timeout=30)
    assert [item["run_id"] for item in body["runs"]] == ["run-old"]
    assert took < 5


def test_a_sweep_leaves_an_existing_archive_file_untouched() -> None:
    now = time.time()
    with _DB():
        folder = _archived("run-kept", now)
        before = _digest(folder)
        archive.sweep(retention_days=30, now=now)
        after = _digest(folder)
        row = history.stored("run-kept")
    assert after == before
    assert row is not None and row["archived"] == 1


def test_a_writer_failure_while_summarizing_still_archives_the_run_without_a_summary() -> None:
    now = time.time()
    with _DB():
        seed("run-x", now - 60 * DAY)
        with patch.object(history, "summarize", side_effect=RuntimeError("boom")):
            destination, _ = archive.archive_run(store.run_bounds()["run-x"], now)
        assert destination is not None
        first = archive.manifest(destination)
    assert "summary" not in first
