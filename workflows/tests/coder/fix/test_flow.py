"""End-to-end tests for the `fix` flow: the standalone backlog drain."""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from coder.fix.scripted import (
    BACKLOG,
    BULLET,
    RED_MAKEFILE,
    STORY_REL,
    TEXT,
    ScriptedAgent,
    answers,
    assert_agent_story_commit,
    backlog,
    branch_of,
    log_of,
    output,
)
from workhorse_workflows.coder.fix.flow import Fix
from workhorse_workflows.coder.shared.backlog import prune_fix_item


def test_one_item_is_seeded_fixed_checked_pruned_and_committed(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A whole iteration, and the second draw that ends the run."""
    agent = ScriptedAgent(workspace)
    run_env = env()

    result = drive_flow(Fix(), run_env, agent)

    assert result.has_fix is False, result
    assert "no drainable bullet" in result.reason, result

    assert agent.counts() == {
        "fix-item": 1,
        "document-story": 1,
    }, agent.counts()

    story = (docs / STORY_REL / "story.md").read_text(encoding="utf-8")
    assert f"- {TEXT}" in story, story
    assert BULLET in story, story
    assert "## Non-Functional Acceptance Criteria\n\n(none)" in story, story
    assert (
        "## Technical Notes\n\nNo prior implementation reference exists." in story
    ), story

    assert BULLET not in backlog(docs), backlog(docs)
    assert "## Filed by coder" in backlog(docs)

    story_id = str(agent.args_for("fix-item")[0]["story_id"])
    subject = log_of(workspace["api"])[0]
    assert subject.startswith("fix(api): ")
    assert story_id not in subject
    body = subprocess.run(
        ["git", "log", "-1", "--format=%b"],
        cwd=workspace["api"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert f"Story: {story_id}" in body
    assert (workspace["api"] / "pagination.go").is_file()
    assert output(run_env, prune_fix_item)["pruned"] is True


def test_the_first_pass_is_handed_the_item_and_no_report_at_all(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A first turn has no gate to report and no answer to carry."""
    agent = ScriptedAgent(workspace)

    drive_flow(Fix(), env(), agent)

    first = agent.args_for("fix-item")[0]
    assert first["bullet_text"] == TEXT, first
    assert first["story_path"].endswith("story.md"), first
    assert first["report"] == "", first
    assert first["operator_context"] == "", first
    assert agent.counts()["fix-item"] == 1, agent.counts()


def test_the_drain_keeps_going_until_the_section_is_empty(
    docs: Path,
    workspace: dict[str, Path],
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`commit`'s next is the draw, so two items are two full iterations in one run."""
    write(
        docs / "docs" / "backlog.md",
        BACKLOG + "- [mobile-pagination] the mobile widget list does not paginate\n",
    )
    agent = ScriptedAgent(workspace)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert agent.counts()["fix-item"] == 2, agent.counts()
    assert "widget-pagination" not in backlog(docs), backlog(docs)
    assert "mobile-pagination" not in backlog(docs), backlog(docs)
    assert len([line for line in log_of(workspace["api"]) if line.startswith("fix(api):")]) == 2


def test_an_untouched_repo_is_neither_gated_nor_committed(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The targets are git's account of the change, not the workspace manifest's list."""
    (workspace["web"] / "Makefile").write_text(RED_MAKEFILE, encoding="utf-8")
    subprocess.run(
        ["git", "add", "Makefile"], cwd=workspace["web"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-qm", "Add a lint target that fails"],
        cwd=workspace["web"],
        check=True,
        capture_output=True,
    )
    agent = ScriptedAgent(workspace)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert agent.counts()["fix-item"] == 1, agent.counts()
    assert not any(line.startswith("fix(web):") for line in log_of(workspace["web"]))
    assert_agent_story_commit(workspace["api"], agent)


def test_the_commits_land_on_the_branch_the_repos_were_already_on(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """No story branch, no fix branch — "commit this one drained item onto the CURRENT branch"."""
    agent = ScriptedAgent(workspace)

    drive_flow(Fix(), env(), agent)

    assert branch_of(workspace["api"]) == "main"
    assert branch_of(docs) == "main"
    assert_agent_story_commit(workspace["api"], agent)


def test_the_docs_sub_flow_runs_for_real_and_its_verdict_gates_the_commit(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`document` is a handoff, so the whole `docs` flow runs per drained item."""
    agent = ScriptedAgent(workspace)

    drive_flow(Fix(), env(), agent)

    assert agent.counts()["document-story"] == 1, agent.counts()
    assert agent.args_for("document-story")[0]["story_path"].endswith("story.md")
    assert_agent_story_commit(workspace["api"], agent)


def test_documentation_that_blocks_parks_and_keeps_the_agent_commit(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blocked docs owner parks the drain, and the answer resumes it onto the same commit."""
    agent = ScriptedAgent(workspace, docs_blocks=1)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", answers(seen)):
        result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    (gate,) = seen
    assert "cannot be described as built" in gate, gate
    assert agent.counts()["document-story"] == 2, agent.counts()
    assert_agent_story_commit(workspace["api"], agent)
    assert BULLET not in backlog(docs), backlog(docs)


def test_a_run_killed_after_the_owner_turn_does_not_run_it_again(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The checkpoint is written before a state runs, so the drawn item survives the kill."""
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during document-story"):
        drive_flow(Fix(), run_env, ScriptedAgent(workspace, explode={"document-story"}))

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "document", resume
    assert resume.flow == "Fix", resume

    agent = ScriptedAgent(workspace)
    result = drive_flow(Fix(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.has_fix is False, result
    assert "fix-item" not in agent.counts(), agent.counts()
    assert agent.counts()["document-story"] == 1, agent.counts()
    assert BULLET not in backlog(docs), backlog(docs)
