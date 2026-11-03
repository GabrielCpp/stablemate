from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from litestar.testing import TestClient
from test_run_clock import _DB, SONNET, STATE, span, turn

from groom import activity, alerts, archive, cli, figures, history, overview, pools, projection, state, store
from groom import app as groom_app
from groom.models import RunTelemetry, WorkflowContainer

DAY = 86400.0


def seed(run: str, base: float, terminal: str | None = "terminal", costs: tuple[float | None, ...] = (2.0, 1.0), node: str = "dev", extra: list[dict] | None = None) -> None:
    pre = f"{run}-"
    attrs = {"workhorse.terminal": terminal} if terminal else {}
    rows = [
        span(pre + "r", pre + "t", "", "coder", "run:coder", base, 1000, attrs, 1, run),
        span(pre + "s", pre + "t", pre + "r", "work", "work", base + 5, 900, STATE, 1, run),
        span(pre + "n", pre + "t", pre + "s", node, node, base + 10, 800, {"workhorse.depth": 1}, 1, run),
    ]
    for index, cost in enumerate(costs):
        rows.append(span(f"{pre}a{index}", pre + "t", pre + "n", node, "agent_turn", base + 10 + index * 100, 60, turn(SONNET, 60, cost), 1, run))
    store.insert_spans(rows + (extra or []))


def refresh(now: float | None = None) -> None:
    for run_id in history.discover(now):
        history.compute(run_id, now)


def listed(alive: set[str] | None = None) -> dict[str, dict]:
    return {item["run_id"]: item for item in history.listing(alive or set())["runs"]}


def test_each_recorded_terminal_maps_to_one_ending_and_reload_is_not_an_ending() -> None:
    assert history.ending_of("terminal") == "success"
    assert history.ending_of("ended") == "success"
    assert history.ending_of("terminal", gave_up=True) == "gave-up"
    assert history.ending_of("fail") == "failed"
    assert history.ending_of("interrupted") == "interrupted"
    assert history.ending_of("aborted") == "crashed"
    assert history.ending_of("reload") is None
    assert history.ending_of("") is None
    assert history.ending_of("done") is None


def test_the_ending_is_written_in_words_for_each_recorded_terminal() -> None:
    words = {"terminal": "success", "fail": "failed", "interrupted": "interrupted", "aborted": "crashed"}
    now = time.time()
    with _DB():
        for terminal in words:
            seed(f"run-{terminal}", now - 3600, terminal)
        refresh(now)
        items = listed()
    assert {terminal: items[f"run-{terminal}"]["ending_label"] for terminal in words} == words


def test_a_run_that_reached_a_give_up_node_reads_gave_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOM_GIVEUP_NODES", "qa_give_up")
    now = time.time()
    with _DB():
        seed("run-gave-up", now - 3600, "terminal", node="qa_give_up")
        seed("run-clean", now - 3600, "terminal")
        refresh(now)
        items = listed()
    assert items["run-gave-up"]["ending_label"] == "gave up"
    assert items["run-clean"]["ending_label"] == "success"


def test_a_row_carries_the_figures_the_cost_and_profile_reports_give_for_the_run() -> None:
    now = time.time()
    with _DB():
        seed("run-figures", now - 7200, costs=(2.0, 1.0, None))
        refresh(now)
        row = listed()["run-figures"]
        costs, profile, _ = figures.read("run-figures")
        assert profile is not None
        active = store.active_seconds(profile["time_s"])
    assert row["workflow"] == "coder"
    assert row["repo"] == "acme"
    assert row["branch"] == "story/acme-sign-in"
    assert row["cost_usd"] == costs["usd"] == 3.0
    assert (row["priced_turns"], row["turns"]) == (2, 3)
    assert row["active_s"] == active
    assert row["wall_s"] == profile["time_s"]["wall"]
    assert row["ended_ts"] == pytest.approx(now - 7200 + 1000)


def test_the_list_is_newest_end_time_first_and_stops_at_thirty_days() -> None:
    now = time.time()
    with _DB():
        seed("run-old", now - 2 * DAY)
        seed("run-new", now - 3600)
        seed("run-ancient", now - 40 * DAY)
        refresh(now)
        order = [item["run_id"] for item in history.listing(set(), now)["runs"]]
    assert order == ["run-new", "run-old"]
    assert store.RETENTION_DAYS == 30


def test_a_run_still_alive_is_not_listed_and_a_finished_run_in_runs_is_listed() -> None:
    now = time.time()
    with _DB():
        seed("run-finished", now - 3600)
        seed("run-resumed", now - 3600)
        refresh(now)
        state.RUNS.clear()
        state.RUNS["run-finished"] = RunTelemetry(run_id="run-finished", terminal="terminal", last_span_ts=now - 3000)
        state.RUNS["run-resumed"] = RunTelemetry(run_id="run-resumed", last_span_ts=now - 5)
        try:
            alive = alerts.unfinished_run_ids(now)
            items = listed(alive)
        finally:
            state.RUNS.clear()
    assert alive == {"run-resumed"}
    assert "run-finished" in items
    assert "run-resumed" not in items


def test_a_run_that_continues_after_a_resume_leaves_history_and_returns_with_its_new_figures() -> None:
    now = time.time()
    base = now - 6 * 3600
    with _DB():
        seed("run-resume", base, "interrupted", costs=(1.0,))
        refresh(now)
        before = listed()["run-resume"]
        resumed = [span("run-resume-b", "run-resume-t2", "run-resume-r2", "dev", "agent_turn", base + 4000, 60, turn(SONNET, 60, 5.0), 2, "run-resume")]
        store.insert_spans(resumed)
        refresh(now)
        gone = "run-resume" in listed()
        store.insert_spans([span("run-resume-r2", "run-resume-t2", "", "coder", "run:coder", base + 3990, 200, {"workhorse.terminal": "terminal"}, 2, "run-resume")])
        refresh(now)
        after = listed()["run-resume"]
    assert before["ending_label"] == "interrupted"
    assert not gone
    assert after["ending_label"] == "success"
    assert after["cost_usd"] == 6.0
    assert after["turns"] == before["turns"] + 1


def test_a_run_with_no_ending_is_listed_after_forty_eight_hours_of_silence_at_its_last_record() -> None:
    now = time.time()
    base = now - 100 * 3600
    with _DB():
        seed("run-silent", base, None)
        seed("run-recent", now - 3600, None)
        refresh(now)
        items = listed()
        last = max(row["end_ts"] for row in store.run_turn_spans("run-silent"))
    assert "run-recent" not in items
    assert items["run-silent"]["ending_label"] == "no ending recorded"
    assert items["run-silent"]["ended_ts"] == pytest.approx(last)


def test_a_silent_run_with_no_ending_leaves_history_when_it_comes_back_alive() -> None:
    now = time.time()
    base = now - 100 * 3600
    with _DB():
        seed("run-back", base, None)
        refresh(now)
        listed_before = "run-back" in listed()
        store.insert_spans([span("run-back-new", "run-back-t9", "", "dev", "agent_turn", now - 10, 5, turn(SONNET, 5, 1.0), 2, "run-back")])
        refresh(now)
        listed_after = "run-back" in listed()
    assert listed_before
    assert not listed_after


def test_an_unrecognized_terminal_records_no_ending_until_the_run_has_been_silent() -> None:
    now = time.time()
    with _DB():
        seed("run-odd", now - 3600, "done")
        refresh(now)
        early = "run-odd" in listed()
        refresh(now + 100 * 3600)
        late = listed()["run-odd"]["ending_label"]
    assert not early
    assert late == "no ending recorded"


def test_an_ended_run_with_no_summary_yet_is_listed_unread_and_fills_in_when_it_is_written() -> None:
    now = time.time()
    with _DB():
        seed("run-unread", now - 3600)
        wanted = history.discover(now)
        before = listed()["run-unread"]
        totals_before = history.listing(set())["totals"]
        history.compute("run-unread", now)
        after = listed()["run-unread"]
    assert wanted == ["run-unread"]
    assert before["ready"] is False
    assert before["workflow"] == "coder"
    assert before["ended_ts"] == pytest.approx(now - 3600 + 1000)
    assert (totals_before["runs"], totals_before["reading"], totals_before["spent_usd"], totals_before["ready"]) == (1, 1, 0, 0)
    assert after["ready"] is True


def _item(**fields: object) -> dict:
    base = {"ready": True, "ending": "success", "cost_usd": None, "est_usd": None, "priced_turns": 0, "turns": 0, "active_s": 0.0}
    return {**base, **fields}


def test_the_totals_count_runs_money_active_time_and_successes() -> None:
    items = [
        _item(cost_usd=10.0, priced_turns=4, turns=4, active_s=3600.0),
        _item(cost_usd=5.0, priced_turns=1, turns=2, active_s=1800.0, ending="failed"),
        _item(est_usd=2.5, turns=3, active_s=600.0),
    ]
    totals = history.totals(items)
    assert totals["runs"] == 3
    assert totals["spent_usd"] == 17.5
    assert totals["estimate_usd"] == 2.5
    assert totals["partly_priced"] == 1
    assert totals["active_s"] == 6000.0
    assert (totals["success"], totals["ready"]) == (2, 3)


def test_a_run_still_being_read_counts_in_runs_and_stays_out_of_the_sums_and_the_success_count() -> None:
    items = [_item(cost_usd=10.0, priced_turns=1, turns=1, active_s=60.0), _item(ready=False, ending="", cost_usd=99.0, active_s=9999.0)]
    totals = history.totals(items)
    assert (totals["runs"], totals["reading"]) == (2, 1)
    assert totals["spent_usd"] == 10.0
    assert totals["active_s"] == 60.0
    assert (totals["success"], totals["ready"]) == (1, 1)


def test_an_empty_history_totals_zero() -> None:
    with _DB():
        result = history.listing(set())
    assert result["runs"] == []
    totals = result["totals"]
    assert (totals["runs"], totals["spent_usd"], totals["active_s"], totals["ready"]) == (0, 0, 0, 0)


def test_a_backend_that_reports_no_cost_shows_an_estimate_and_no_cost() -> None:
    now = time.time()
    with _DB():
        seed("run-est", now - 3600, costs=(None, None))
        refresh(now)
        costs, _, _ = figures.read("run-est")
        row = listed()["run-est"]
    assert row["cost_usd"] is None
    assert row["est_usd"] == costs["est_usd"]


def test_the_list_reads_summaries_and_opens_in_under_two_seconds_with_the_store_full() -> None:
    now = time.time()
    rows = [(f"bulk-{index}", "coder", "acme", "main", now - index * 600) for index in range(3000)]
    with _DB():
        history._insert_pending(rows)
        for index in range(0, 3000, 2):
            history._write({"run_id": f"bulk-{index}", "workflow": "coder", "state": "ready", "ending": "success", "ended_ts": now - index * 600, "last_ts": now - index * 600})
        with patch.object(store, "run_turn_spans", side_effect=AssertionError("the list read a run's records")):
            began = time.perf_counter()
            result = history.listing(set(), now)
            took = time.perf_counter() - began
    assert len(result["runs"]) == 3000 - sum(1 for index in range(3000) if now - index * 600 < now - 30 * DAY)
    assert took < 2.0


def test_the_listing_names_every_ending_once_in_the_order_the_ending_filter_offers_them() -> None:
    with _DB():
        result = history.listing(set())
    assert result["endings"] == [["success", "success"], ["gave-up", "gave up"], ["failed", "failed"], ["interrupted", "interrupted"], ["crashed", "crashed"], ["none", "no ending recorded"]]


def test_the_history_route_lists_the_ended_runs_and_leaves_out_a_run_that_is_alive() -> None:
    now = time.time()
    with _DB():
        seed("run-route", now - 3600)
        seed("run-live", now - 3600)
        refresh(now)
        state.RUNS.clear()
        state.RUNS["run-live"] = RunTelemetry(run_id="run-live", last_span_ts=time.time())
        try:
            with TestClient(app=groom_app.create_app()) as client:
                body = client.get("/api/history").json()
        finally:
            state.RUNS.clear()
    assert [item["run_id"] for item in body["runs"]] == ["run-route"]
    assert body["totals"]["runs"] == 1


def test_the_summary_worker_has_a_pool_of_its_own_with_one_thread() -> None:
    assert pools.SUMMARY in pools.ALL
    assert pools.SUMMARY.workers == 1
    assert pools.SUMMARY is not pools.QUERY
    assert pools.SUMMARY is not pools.INGEST


def test_a_summary_pass_writes_the_rows_that_are_missing_one_run_at_a_time() -> None:
    now = time.time()
    with _DB():
        seed("run-pass-1", now - 3600)
        seed("run-pass-2", now - 7200)
        with patch.object(groom_app, "SUMMARY_PAUSE_S", 0.0):
            written = asyncio.run(groom_app._summary_pass())
        items = listed()
        again = asyncio.run(groom_app._summary_pass())
        pools.shutdown_all()
    assert written == 2
    assert all(item["ready"] for item in items.values())
    assert again == 0


def test_the_book_screen_names_history_in_the_rail_and_describes_its_pane() -> None:
    book = (Path(__file__).resolve().parents[2] / "docs/services/groom/gui/screens/groom-dashboard.md").read_text()
    assert "runs, history, attendant, dispatch, and settings mode controls" in book
    assert "### activity-history-mode" in book
    assert "### history-table" in book
    assert 'aria-sort="descending"' in book


def test_the_book_screen_describes_the_history_filters_and_their_rules() -> None:
    root = Path(__file__).resolve().parents[2] / "docs/services/groom"
    book = (root / "gui/screens/groom-dashboard.md").read_text()
    rules = (root / "concepts/run-history-filters.md").read_text()
    for heading in ("### history-filters", "### history-no-match", "### filter-history", "### clear-history-filters"):
        assert heading in book
    assert "No runs match these filters." in book
    assert "- rule: the filters narrow the rows in the browser from the list already loaded, with no request" in rules
    assert "- rule: the range offers the last 7 days and the last 30 days and starts on the last 30 days" in rules


def unnamed(run: str, base: float, terminal: str, workspace: str = "", branch: str = "", late: float | None = None) -> None:
    attrs = {"workhorse.terminal": terminal}
    root = span(f"{run}-r", f"{run}-t", "", "coder", "run:coder", base, 1000, attrs, 1, run)
    child = span(f"{run}-c", f"{run}-t", f"{run}-r", "dev", "dev", base + 10, 100, {"workspace.path.start": workspace, "git.branch.start": branch} if workspace else {}, 1, run)
    rows = [root, child]
    if late is not None:
        rows.append(span(f"{run}-l", f"{run}-t", f"{run}-r", "dev", "dev", base + 1000 + late - 1, 1, {}, 1, run))
    for row in rows:
        row["repo"] = row["branch"] = ""
    store.insert_spans(rows)


def test_a_run_whose_spans_name_a_workspace_and_a_branch_reads_that_repo_and_branch() -> None:
    now = time.time()
    with _DB():
        unnamed("run-ws", now - 3600, "terminal", "/home/dev/work/stablemate", "main")
        wanted = history.discover(now)
        pending = listed()["run-ws"]
        history.compute("run-ws", now)
        ready = listed()["run-ws"]
    assert wanted == ["run-ws"]
    assert (pending["repo"], pending["branch"]) == ("stablemate", "main")
    assert (ready["repo"], ready["branch"]) == ("stablemate", "main")


def test_a_run_whose_spans_record_no_workspace_keeps_no_repo() -> None:
    now = time.time()
    with _DB():
        unnamed("run-bare", now - 3600, "terminal")
        refresh(now)
        row = listed()["run-bare"]
    assert (row["repo"], row["branch"]) == ("", "")


def test_a_live_row_and_history_label_one_run_with_the_same_repo_and_branch() -> None:
    now = time.time()
    with _DB():
        unnamed("run-same", now - 3600, "terminal", "/home/dev/work/stablemate", "main")
        refresh(now)
        row = listed()["run-same"]
    live = WorkflowContainer(container_id="run-same", name="coder", native=True, repo_branch="main", workspace_volume="/home/dev/work/stablemate")
    assert projection.repo_text(row["repo"], row["branch"]) == projection.repo_label(live) == "stablemate@main"


def test_a_span_ending_within_sixty_seconds_after_the_root_still_counts_as_the_root_closing_the_run() -> None:
    now = time.time()
    with _DB():
        unnamed("run-near", now - 3600, "interrupted", late=5.2)
        wanted = history.discover(now)
        history.compute("run-near", now)
        row = listed()["run-near"]
    assert history.ENDING_TOLERANCE_S == 60
    assert wanted == ["run-near"]
    assert row["ending_label"] == "interrupted"


def test_a_span_ending_past_sixty_seconds_after_the_root_means_the_run_went_on() -> None:
    now = time.time()
    with _DB():
        unnamed("run-far", now - 3600, "interrupted", late=61)
        early = history.discover(now)
        refresh(now + 100 * 3600)
        row = listed()["run-far"]
    assert early == []
    assert row["ending_label"] == "no ending recorded"


def _cli_json(capsys: pytest.CaptureFixture[str], command, run: str):
    capsys.readouterr()
    command(run, as_json=True)
    return json.loads(capsys.readouterr().out)


def test_one_ended_runs_cost_and_times_per_node_and_per_flow_equal_groom_cost_and_groom_profile(capsys: pytest.CaptureFixture[str]) -> None:
    now = time.time()
    with _DB():
        seed("run-parity", now - 3600, costs=(4.0, 1.5, None))
        refresh(now)
        costs = _cli_json(capsys, cli.cost, "run-parity")
        profiled = _cli_json(capsys, cli.profile, "run-parity")
        found = overview.run_overview("run-parity")
    assert found["figures"]["cost_usd"] == sum(row["cost_usd"] for row in costs if row["cost_usd"] is not None)
    assert {row["node"]: row["time_s"] for row in found["nodes"]} == {
        child["node"]: child["time_s"] for flow in profiled["flows"] for child in flow["children"] if child["kind"] == "state"
    }
    assert found["flows"] == profiled["flows"]


def test_a_run_recorded_before_the_flow_attributes_still_shows_its_flow_times() -> None:
    now = time.time()
    with _DB():
        seed("run-before", now - 3600, costs=(4.0, 1.0))
        refresh(now)
        found = overview.run_overview("run-before")
    assert [flow["name"] for flow in found["flows"]] == ["coder"]
    assert found["flows"][0]["time_s"] == 120.0
    assert found["nodes"][0]["time_s"] == 120.0


def test_the_summary_the_overview_and_the_activity_count_report_one_problem_number() -> None:
    now = time.time()
    with _DB():
        seed("run-one", now - 3600, costs=(4.0, 1.0))
        refresh(now)
        listed_problems = listed()["run-one"]["problems"]
        standing = overview.run_overview("run-one")["standing"]["problems"]
        with archive.run_source("run-one"):
            counted = activity.timeline("run-one")["problems"]
    assert listed_problems == standing == counted
    assert counted >= 1
