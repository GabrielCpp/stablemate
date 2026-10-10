"""The `fix` flow's red gates and blocked owner turns, each parked and resumed."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.engine import RunEnv

from coder.fix.scripted import (
    BULLET,
    SLUG,
    ScriptedAgent,
    answers,
    assert_agent_story_commit,
    backlog,
)
from workhorse_workflows.coder.fix.flow import Fix
from workhorse_workflows.coder.shared.owner import MAX_LAPS


def test_a_red_gate_sends_the_owner_its_output_as_one_report(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Git names the repos, `make` judges them, and the owner's next turn reads the verdict."""
    agent = ScriptedAgent(workspace, gate_red=1)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert agent.counts()["fix-item"] == 2, agent.counts()
    assert "resolve-operator" not in agent.counts(), agent.counts()

    lap = agent.args_for("fix-item")[1]["report"]
    assert "make lint" in lap, lap
    assert "undefined: pageSize" in lap, lap
    assert str(workspace["api"]) in lap, lap

    assert BULLET not in backlog(docs), backlog(docs)


def test_a_gate_still_red_when_the_laps_run_out_parks_rather_than_giving_up(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A spent repair budget goes to the resolver, then the operator, never `WorkflowFailed`."""
    agent = ScriptedAgent(workspace, gate_red=MAX_LAPS + 1)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", answers(seen)):
        result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result

    (gate,) = seen
    assert "the gates on the fix-drain item" in gate, gate
    assert f"after {MAX_LAPS} repair turn(s)" in gate, gate
    assert "undefined: pageSize" in gate, gate

    counts = agent.counts()
    assert counts["fix-item"] == MAX_LAPS + 2, counts
    assert counts["resolve-operator"] == 1, counts
    assert "Twenty per page" in agent.args_for("fix-item")[-1]["operator_context"]
    assert BULLET not in backlog(docs), backlog(docs)


def test_an_owner_turn_that_says_it_cannot_parks_and_resumes_with_the_answer(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blocked owner is checked by nothing until the operator has answered it."""
    agent = ScriptedAgent(workspace, impl_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", answers(seen)):
        result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result

    (gate,) = seen
    assert "the page size is a product decision nobody has made" in gate, gate
    assert "the fix owner turn" in gate, gate
    assert SLUG in gate, gate

    assert agent.counts()["fix-item"] == 2, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    retried = agent.args_for("fix-item")[1]
    assert "Twenty per page" in retried["operator_context"], retried

    assert BULLET not in backlog(docs), backlog(docs)
    assert_agent_story_commit(workspace["api"], agent)
