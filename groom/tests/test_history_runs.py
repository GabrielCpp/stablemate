from __future__ import annotations

import json
import time

import pytest
from test_history import listed, refresh, seed
from test_run_clock import _DB, span

from groom import activity, archive, cli, history, overview, projection, store
from groom.models import WorkflowContainer


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
