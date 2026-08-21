"""The forensics every round is read through: timing, reliability, churn.

These are the properties that make a score trustworthy rather than merely printed, and
each of them has been wrong at least once in a way nothing else noticed:

* a node that slept on a usage cap must NEVER be flagged as a hang, while one that spent
  the same wall-clock working must be — workhorse waits caps out by design;
* an operator-gate escalation outranks an ordinary repair, because it is a run that would
  have halted and asked;
* a run that predates the workflow source is stale — the check that had itself gone stale,
  silently, by globbing a layout that no longer existed;
* churn is a cycle repeating, never merely a node running often — a loop over a queue
  re-enters the same nodes once per item, and that is the workflow working.

Everything here is literal: events files written by hand, a checkout that is a directory
with the right shape. No docker, no agent, no run.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

DATA = Path(__file__).parents[1]


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does."""
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


_spec = importlib.util.spec_from_file_location("_forensics", DATA / "tasks" / "_forensics.py")
assert _spec is not None and _spec.loader is not None  # noqa: S101 - a real file on disk
fx = importlib.util.module_from_spec(_spec)
with _tasks_dir_on_path():
    sys.modules["_forensics"] = fx
    _spec.loader.exec_module(fx)


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


# ── timing: cap-wait is never a hang ──────────────────────────────────────────────────


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


# ── reliability ───────────────────────────────────────────────────────────────────────


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
    # Stamped rather than touched: two touches in one test land in the same instant on a
    # coarse clock, and the comparison is strict.
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
    """The previous spelling was a glob for a deleted layout: it matched nothing, and every
    staleness verdict silently became False in exactly the way the check exists to catch."""
    with pytest.raises(fx.TrialError, match="no workflow source"):
        fx.read_runs(tmp_path / "runs", tmp_path / "empty")


def test_the_real_workflow_source_dates_something() -> None:
    """And it is this tree's, so the guard cannot pass by pointing nowhere."""
    assert fx.newest_source_mtime(DATA.parents[1]) > 0


# ── churn: a repeating cycle, not a busy node ─────────────────────────────────────────


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
    # Reported as one 3× period-2 cycle, not as the two period-1 non-cycles it is not.
    assert {"cycle": ["qa", "fix"], "repeats": 3} in found


def test_churn_reads_subflows_too(tmp_path: Path) -> None:
    """A spinning subflow is invisible from the parent, which sees one long container node."""
    runs = tmp_path / "runs"
    write_entered(runs / "run1" / "qa_phase" / "_flow", *(["author_plan", "repair_plan"] * 3))

    found = fx.churn_candidates(runs)
    assert [row["cycle"] for row in found] == [["author_plan", "repair_plan"]]
    assert found[0]["where"].endswith("_flow")
