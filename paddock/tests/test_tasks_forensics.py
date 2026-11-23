"""Tests for `paddock.tasks.forensics`, the reader of what a round left on disk."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from paddock.tasks import forensics as fx

ROOT = Path(__file__).parents[2]


def write_events(base: Path, node: str, enter: str, done: str, *, flow: bool = False) -> Path:
    directory = base / node / "_flow" if flow else base
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "events.jsonl").write_text(
        json.dumps({"ts": enter, "phase": "enter", "node": node}) + "\n"
        + json.dumps({"ts": done, "phase": "done", "node": node}) + "\n",
        encoding="utf-8")
    return base


def write_entered(directory: Path, *nodes: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "events.jsonl").write_text("\n".join(
        json.dumps({"ts": "2026-07-21T00:00:00+00:00", "phase": "enter", "node": node})
        for node in nodes), encoding="utf-8")
    return directory


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A directory shaped like a stablemate checkout, dated by this test rather than the tree."""
    source = tmp_path / "checkout" / "workflows" / "src" / "workhorse_workflows"
    source.mkdir(parents=True)
    (source / "flow.py").write_text("# a workflow\n", encoding="utf-8")
    return tmp_path / "checkout"




def test_cap_wait_is_never_flagged_as_a_hang(tmp_path: Path) -> None:
    """3h35m of wall-clock that was 3h35m of cap-wait is a healthy node, not a hang."""
    runs, artifacts = tmp_path / "runs", tmp_path / "artifacts"
    write_events(runs / "run1", "review_story_documentation",
                 "2026-07-21T00:00:00+00:00", "2026-07-21T03:35:00+00:00")
    artifacts.mkdir(parents=True)
    (artifacts / "coder.log").write_text(
        "[review_story_documentation] ⏸ spending/usage cap reached — pausing ~12900s (resuming …)\n",
        encoding="utf-8")

    node = next(n for n in fx.hang_candidates(runs, artifacts)
                if n["node"] == "review_story_documentation")
    assert not node["hang"]
    assert node["active_per_run"] < 600, "cap-wait must be subtracted from active time"


def test_genuine_active_work_is_flagged(tmp_path: Path) -> None:
    """The same wall-clock with no cap-wait behind it is a real hang / retry-churn."""
    runs, artifacts = tmp_path / "runs", tmp_path / "artifacts"
    write_events(runs / "run1", "stuck_agent",
                 "2026-07-21T00:00:00+00:00", "2026-07-21T02:00:00+00:00")
    artifacts.mkdir(parents=True)
    (artifacts / "coder.log").write_text("no cap here\n", encoding="utf-8")

    node = next(n for n in fx.hang_candidates(runs, artifacts) if n["node"] == "stuck_agent")
    assert node["hang"], "2h of ACTIVE work must exceed the 30-min threshold"


def test_flow_containers_are_excluded(tmp_path: Path) -> None:
    """A container's time is its children's — flagging it points at the wrong node."""
    runs, artifacts = tmp_path / "runs", tmp_path / "artifacts"
    write_events(runs / "run1", "qa_phase",
                 "2026-07-21T00:00:00+00:00", "2026-07-21T04:00:00+00:00", flow=True)
    artifacts.mkdir(parents=True)
    assert "qa_phase" in fx.flow_containers(runs)
    assert "qa_phase" not in {n["node"] for n in fx.hang_candidates(runs, artifacts)}




def test_escalation_outranks_repair(tmp_path: Path, checkout: Path) -> None:
    """An operator-gate escalation is a would-have-halted run, not an ordinary rework."""
    runs = tmp_path / "runs"
    write_entered(runs / "run1", "plan_story", "fix_story", "await_operator")

    row = fx.read_runs(runs, checkout)[0]
    assert row["repairs"] == ["fix_story"]
    assert row["escalations"] == ["await_operator"]


def test_a_run_older_than_the_workflow_source_is_stale(tmp_path: Path, checkout: Path) -> None:
    """A report that can describe a round older than the code under test says nothing."""
    runs = tmp_path / "runs"
    events = write_entered(runs / "run1", "plan_story") / "events.jsonl"
    source = checkout / "workflows" / "src" / "workhorse_workflows" / "flow.py"
    os.utime(events, (1_000_000, 1_000_000))
    os.utime(source, (2_000_000, 2_000_000))

    assert fx.read_runs(runs, checkout)[0]["stale"]


def test_a_run_newer_than_the_workflow_source_is_not_stale(tmp_path: Path, checkout: Path) -> None:
    runs = tmp_path / "runs"
    source = checkout / "workflows" / "src" / "workhorse_workflows" / "flow.py"
    events = write_entered(runs / "run1", "plan_story") / "events.jsonl"
    os.utime(source, (1_000_000, 1_000_000))
    os.utime(events, (2_000_000, 2_000_000))

    assert not fx.read_runs(runs, checkout)[0]["stale"]


def test_a_checkout_with_no_workflow_source_is_loud(tmp_path: Path) -> None:
    """The previous spelling was a glob for a deleted layout: it matched nothing, and every staleness verdict silently became False in exactly the way the check exists to catch."""
    with pytest.raises(fx.TrialError, match="no workflow source"):
        fx.read_runs(tmp_path / "runs", tmp_path / "empty")


def test_the_real_workflow_source_dates_something() -> None:
    """And it is this tree's, so the guard cannot pass by pointing nowhere."""
    assert fx.newest_source_mtime(ROOT) > 0




def test_a_queue_loop_is_not_churn() -> None:
    """`plan → implement → qa` once per story is the workflow advancing through a queue."""
    entered = ["plan", "implement", "qa"] * 4
    found = fx.cycles(entered)
    assert all(c["cycle"] != ["plan"] for c in found)


def test_a_node_retrying_itself_is_churn() -> None:
    found = fx.cycles(["plan", "fix", "fix", "fix", "qa"])
    assert {"cycle": ["fix"], "repeats": 3} in found


def test_a_two_node_ping_pong_is_churn() -> None:
    found = fx.cycles(["qa", "fix", "qa", "fix", "qa", "fix", "done"])
    assert {"cycle": ["qa", "fix"], "repeats": 3} in found


def test_churn_reads_subflows_too(tmp_path: Path) -> None:
    """A spinning subflow is invisible from the parent, which sees one long container node."""
    runs = tmp_path / "runs"
    write_entered(runs / "run1" / "qa_phase" / "_flow", *(["author_plan", "repair_plan"] * 3))

    found = fx.churn_candidates(runs)
    assert [row["cycle"] for row in found] == [["author_plan", "repair_plan"]]
    assert found[0]["where"].endswith("_flow")


def write_transcript(run_dir: Path, name: str, compactions: int) -> None:
    folder = run_dir / "transcripts"
    folder.mkdir(parents=True, exist_ok=True)
    lines = ['{"subtype": "compact_boundary"}'] * compactions + ['{"type": "assistant"}']
    (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_a_resumed_session_charges_only_its_growth_to_the_later_turn(tmp_path: Path) -> None:
    write_transcript(tmp_path, "001-00001-dev-plan__aaa.jsonl", 1)
    write_transcript(tmp_path, "001-00002-dev-build__aaa.jsonl", 3)
    write_transcript(tmp_path, "001-00002-dev-build__aaa.acp.jsonl", 9)
    write_transcript(tmp_path, "001-00003-qa-story__bbb.jsonl", 2)

    assert fx.compactions_by_node(tmp_path) == {"dev-plan": 1, "dev-build": 2, "qa-story": 2}


def test_flow_rows_split_dollars_by_the_flow_that_holds_each_node(tmp_path: Path) -> None:
    (tmp_path / "review" / "_flow" / "review-diff").mkdir(parents=True)
    (tmp_path / "dev" / "_flow" / "dev-build").mkdir(parents=True)
    write_transcript(tmp_path, "001-00001-dev-build__aaa.jsonl", 2)
    turn = {"name": "agent_turn", "profile_duration_ms": 60000.0}

    rows = fx.flow_rows(
        [
            {**turn, "node": "dev-build", "profile_cost_usd": 3.5},
            {**turn, "node": "review-diff", "profile_cost_usd": 1.25},
            {**turn, "node": "review-diff", "profile_cost_usd": 0.75},
            {**turn, "node": "specify-story", "profile_cost_usd": None},
            {"name": "dev-build", "node": "dev-build", "profile_cost_usd": 99.0},
        ],
        tmp_path,
    )

    by_flow = {row["flow"]: row for row in rows}
    assert by_flow["dev"]["usd"] == 3.5
    assert by_flow["dev"]["compactions"] == 2
    assert [turn["usd"] for turn in by_flow["review"]["turns"]] == [1.25, 0.75]
    assert by_flow[fx.MAIN_FLOW]["unpriced"] == 1


def test_a_round_groom_never_saw_says_so_and_prints_no_zero(tmp_path: Path) -> None:
    write_transcript(tmp_path, "001-00001-dev-build__aaa.jsonl", 1)

    lines = fx.flow_cost_lines(fx.flow_rows([], tmp_path))

    assert lines == ["cost: groom holds no turn for this run, so start groom before the round"]


def test_flow_costs_count_only_turns_inside_the_run_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from groom import store

    (tmp_path / "run.json").write_text(json.dumps({
        "run_id": "coder",
        "started_at": "2026-11-23T05:00:00+00:00",
        "ended_at": "2026-11-23T06:00:00+00:00",
    }), encoding="utf-8")
    inside = 1795410000.0
    turns = [
        {"name": "agent_turn", "node": "qa-story", "start_ts": inside - 86400, "profile_cost_usd": 9.0},
        {"name": "agent_turn", "node": "qa-story", "start_ts": inside, "profile_cost_usd": 2.0},
    ]
    monkeypatch.setattr(store, "run_turn_spans", lambda run: turns)

    rows = fx.flow_costs(tmp_path)

    assert [row["usd"] for row in rows] == [2.0]


def test_an_unpriced_turn_falls_back_to_its_estimate(tmp_path: Path) -> None:
    turn = {"name": "agent_turn", "node": "dev-build", "profile_duration_ms": 1000.0}

    rows = fx.flow_rows(
        [
            {**turn, "profile_cost_usd": 2.0, "est_cost_usd": 9.0},
            {**turn, "profile_cost_usd": None, "est_cost_usd": 1.5},
            {**turn, "profile_cost_usd": None, "est_cost_usd": None},
        ],
        tmp_path,
    )

    row = rows[0]
    assert (row["usd"], row["estimated"], row["unpriced"]) == (3.5, 1, 1)
    assert [turn["usd"] for turn in row["turns"]] == [2.0, 1.5, 0.0]
    assert "est 1" in fx.flow_cost_lines(rows)[0]


def write_token_counts(run_dir: Path, name: str, *events: tuple[str, float, float, int, int]) -> None:
    folder = run_dir / "transcripts"
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["not json"]
    for stamp, primary, secondary, primary_reset, secondary_reset in events:
        limits = {
            "limit_id": "codex",
            "primary": {"used_percent": primary, "window_minutes": 300, "resets_at": primary_reset},
            "secondary": {"used_percent": secondary, "window_minutes": 10080, "resets_at": secondary_reset},
            "plan_type": "plus",
        }
        payload = {"type": "token_count", "info": {}, "rate_limits": limits}
        lines.append(json.dumps({"timestamp": stamp, "type": "event_msg", "payload": payload}))
    (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_two_events_on_one_window_give_the_difference(tmp_path: Path) -> None:
    write_token_counts(
        tmp_path,
        "001-00001-dev-build__aaa.jsonl",
        ("2026-11-22T21:00:00.000Z", 50.0, 25.0, 200, 900),
        ("2026-11-22T20:00:00.000Z", 45.0, 23.0, 200, 900),
    )

    share = fx.quota_share(tmp_path)

    assert share is not None and share["plan_type"] == "plus"
    assert share["windows"]["primary"] == {
        "window_minutes": 300, "start_pct": 45.0, "end_pct": 50.0, "used_pct": 5.0, "resets_crossed": 0,
    }
    assert share["windows"]["secondary"]["used_pct"] == 2.0


def test_a_reset_mid_round_sums_both_segments(tmp_path: Path) -> None:
    write_token_counts(
        tmp_path,
        "001-00001-dev-build__aaa.jsonl",
        ("2026-11-22T20:00:00.000Z", 70.0, 23.0, 200, 900),
        ("2026-11-22T21:00:00.000Z", 90.0, 24.0, 200, 900),
        ("2026-11-22T22:00:00.000Z", 5.0, 25.0, 500, 900),
        ("2026-11-22T23:00:00.000Z", 15.0, 26.0, 500, 900),
    )

    share = fx.quota_share(tmp_path)
    assert share is not None
    window = share["windows"]["primary"]

    assert (window["used_pct"], window["resets_crossed"]) == (30.0, 1)
    assert (window["start_pct"], window["end_pct"]) == (70.0, 15.0)
    assert fx.quota_line(share) == "quota: plus week +3.0%  5h +30.0% (1 reset)"


def test_no_rate_limits_gives_none(tmp_path: Path) -> None:
    write_transcript(tmp_path, "001-00001-dev-build__aaa.jsonl", 1)

    assert fx.quota_share(tmp_path) is None
    assert fx.quota_line(None) == "quota: no plan usage in the transcripts"
