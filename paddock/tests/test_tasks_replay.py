"""The replay plan: which pinned stories run on which flows."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import fake_run

from paddock.tasks import replay
from paddock.tasks.stablemate import TrialError

FIXTURE = replay.Fixture(
    app="apps/x",
    pins=(
        replay.Pin("S-1", {"qa": "c1", "docs": "c2"}),
        replay.Pin("S-2", {"qa": "c3"}),
    ),
    flows=("qa", "docs"),
)


def test_the_plan_runs_every_pinned_story_on_every_flow_it_has(tmp_path: Path) -> None:
    plan = replay.plan_round(fake_run(tmp_path), FIXTURE)
    assert [(pin.story, flow) for pin, flow in plan] == [("S-1", "qa"), ("S-1", "docs"), ("S-2", "qa")]


def test_the_stories_and_flows_inputs_narrow_the_plan(tmp_path: Path) -> None:
    run = fake_run(tmp_path, inputs={"stories": ["S-1"], "flows": ["docs"]})
    assert [(pin.story, flow) for pin, flow in replay.plan_round(run, FIXTURE)] == [("S-1", "docs")]


def test_an_unpinned_story_or_unknown_flow_is_refused(tmp_path: Path) -> None:
    with pytest.raises(TrialError, match="no pin for: S-9"):
        replay.plan_round(fake_run(tmp_path, inputs={"stories": ["S-9"]}), FIXTURE)
    with pytest.raises(TrialError, match="this fixture replays"):
        replay.plan_round(fake_run(tmp_path, inputs={"flows": ["dev"]}), FIXTURE)


def test_a_pin_without_a_commit_for_the_flow_is_named() -> None:
    with pytest.raises(TrialError, match="no dev commit pinned"):
        FIXTURE.pins[0].commit("dev")
    assert FIXTURE.pins[0].entry_ref("qa") == "c1~"
