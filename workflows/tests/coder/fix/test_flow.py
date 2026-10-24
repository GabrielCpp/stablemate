"""End-to-end tests for the `fix` flow: the standalone backlog drain."""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from ostler import Ostler
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from coder.fix.scripted import (
    RECORD,
    RED_MAKEFILE,
    SCREENSHOT,
    STORY_REL,
    TEXT,
    ScriptedAgent,
    answers,
    assert_agent_story_commit,
    branch_of,
    dirty_paths,
    log_of,
    output,
    record_of,
)
from workhorse_workflows.coder.fix.flow import Fix
from workhorse_workflows.coder.shared.backlog import close_fix_item


def test_one_item_is_seeded_fixed_checked_committed_and_closed(
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
    assert "no open qa record" in result.reason, result

    assert agent.counts() == {
        "fix-item": 1,
        "document-story": 1,
    }, agent.counts()

    story = (docs / STORY_REL / "story.md").read_text(encoding="utf-8")
    assert f"- {TEXT}" in story, story
    assert RECORD in story, story
    assert f"debt record `{RECORD}` in `api/widget` of the artifacts register" in story, story
    assert "## Non-Functional Acceptance Criteria\n\n(none)" in story, story
    assert (
        "## Technical Notes\n\nNo prior implementation reference exists." in story
    ), story

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
    sha = subprocess.run(
        ["git", "rev-parse", "--short=7", "HEAD"], cwd=workspace["api"], check=True, capture_output=True, text=True
    ).stdout.strip()
    closed = record_of(docs)
    assert (closed.status, closed.reason) == ("done", f"fixed in api@{sha}")
    assert output(run_env, close_fix_item)["closed"] is True


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
    assert first["item_text"] == TEXT, first
    assert first["story_path"].endswith("story.md"), first
    assert first["report"] == "", first
    assert first["operator_context"] == "", first
    assert agent.counts()["fix-item"] == 1, agent.counts()


def test_the_drain_keeps_going_until_no_open_qa_record_is_left(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`commit`'s next is the draw, so two records are two full iterations in one run."""
    second = Ostler(docs).file_record(
        repo="api", area="widget", pattern="paginate",
        summary="the mobile widget list does not paginate", filed_by="qa", record_id="mobile-pagination",
    )
    assert second.record is not None, second.message
    agent = ScriptedAgent(workspace)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert agent.counts()["fix-item"] == 2, agent.counts()
    assert record_of(docs).status == "done", record_of(docs)
    assert record_of(docs, "mobile-pagination").status == "done"
    assert len([line for line in log_of(workspace["api"]) if line.startswith("fix(api):")]) == 2


def test_the_story_of_a_record_covers_the_record_id(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    drive_flow(Fix(), env(), ScriptedAgent(workspace))

    stories = Ostler(docs).list("story", epic="fixes")
    assert [story.get("covers") for story in stories] == [[RECORD]], stories


def test_a_fix_that_changed_nothing_fails_the_drain_and_leaves_the_record_open(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = ScriptedAgent(workspace, change=False)

    with pytest.raises(WorkflowFailed, match="no commit carries an exact Story trailer"):
        drive_flow(Fix(), env(), agent)

    assert record_of(docs).status == "open", record_of(docs)
    assert not any(line.startswith("fix(") for line in log_of(workspace["api"]))


def test_a_run_where_no_repository_landed_a_commit_leaves_the_record_open_and_ends(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Fix, "_landed", lambda self: {})
    agent = ScriptedAgent(workspace)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert "stays open" in result.reason, result
    assert agent.counts()["fix-item"] == 1, agent.counts()
    assert record_of(docs).status == "open", record_of(docs)


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
    assert record_of(docs).status == "done", record_of(docs)


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
    assert record_of(docs).status == "done", record_of(docs)


def test_a_turn_gets_its_tool_output_back_and_the_commit_leaves_what_was_dirty_before(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A failure screenshot goes back to the owner, and a config edited before the item stays out of every commit."""
    api = workspace["api"]
    (api / "config.yml").write_text("port: 8080\n", encoding="utf-8")
    subprocess.run(["git", "add", "config.yml"], cwd=api, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "Add config"], cwd=api, check=True, capture_output=True)
    (api / "config.yml").write_text("port: 9090\n", encoding="utf-8")
    agent = ScriptedAgent(workspace, screenshots=1)

    result = drive_flow(Fix(), env(), agent)

    assert result.has_fix is False, result
    assert agent.counts()["fix-item"] == 2, agent.counts()
    report = str(agent.args_for("fix-item")[1]["report"])
    assert f"`api:{SCREENSHOT}`" in report, report
    assert "config.yml" not in report, report
    committed = subprocess.run(
        ["git", "log", "--name-only", "--format="],
        cwd=api,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert "pagination.go" in committed, committed
    assert SCREENSHOT not in committed, committed
    assert committed.count("config.yml") == 1, committed
    assert dirty_paths(api) == {"config.yml"}, dirty_paths(api)
