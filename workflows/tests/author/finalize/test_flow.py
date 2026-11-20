from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from _fakes import StubRunner
from _epics import write_epic_prose
from _milestones import write_milestone
from ostler import Ostler, crud
from ostler.model import load
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows import author
from workhorse_workflows.author.finalize import Finalize
from workhorse_workflows.author.finalize.flow import MAX_INTEGRITY_RESOLVES
from workhorse_workflows.author.shared.schemas import Committed, Defects, MilestoneStatus, VerifyReport
from workhorse_workflows.author.workflow import workflow

MILESTONE = "docs/milestones/account-access/milestone.md"
EPIC = "accounts"
STORY = "sign-in"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "docs/milestones")
    _git(repo, "commit", "-m", message)


def _story_body(title: str) -> str:
    return f"""# Story: {title}

## Dependencies

(none)

## Fixtures

(none)

## Context

An account holder signs in to reach their account.

## Acceptance Criteria

- Given valid credentials, when they sign in, then account access is granted.

## Non-Functional Acceptance Criteria

- Existing account access remains compatible.

## Technical Notes

Use the existing account boundary.

## Implementation Status

- **Status**: Not started
"""


def _planning_graph(repo: Path, *, selectable: bool) -> None:
    write_milestone(repo)
    _commit(repo, "approved milestone")

    okf = Ostler(repo)
    assert okf.create_epic(EPIC, "Account access").ok
    assert okf.add_seed(
        EPIC,
        "credentials",
        status="researched",
        summary="Accept valid credentials",
    ).ok
    assert okf.create_story(
        EPIC,
        STORY,
        "Sign in",
        covers=["credentials"],
    ).ok
    epic = Ostler(repo).graph.epic_by_ref(EPIC)
    assert epic is not None and epic.epic_md is not None
    write_epic_prose(epic.epic_md)
    listed = crud.set_milestone_epics(load(repo), "account-access", [EPIC])
    assert listed.ok, listed.message

    story = next(row for row in Ostler(repo).list("story") if row["slug"] == STORY)
    story_path = repo / str(story["path"])
    frontmatter, separator, _body = story_path.read_text(encoding="utf-8").partition("\n---\n")
    assert separator
    body = _story_body("Sign in")
    if not selectable:
        frontmatter = frontmatter.replace("status: Not started", "status: Done")
        body = body.replace("- **Status**: Not started", "- **Status**: Done")
    story_path.write_text(f"{frontmatter}\n---\n{body}", encoding="utf-8")


def _env(tmp_path: Path) -> RunEnv:
    writer = ArtifactWriter("author-finalize", tmp_path / "runs", run_id="t")

    def reject_agent(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("finalize must not run an authoring agent turn")

    return RunEnv(
        writer=writer,
        workflow_dir=Path(author.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
        agent_runner=StubRunner(reject_agent),
    )


def test_finalizes_with_one_commit_on_the_current_branch(repo: Path, tmp_path: Path) -> None:
    """The tail commits the epics and stops — there is no branch to cut and no PR to open."""
    _planning_graph(repo, selectable=True)
    before = int(_git(repo, "rev-list", "--count", "HEAD"))
    branch = _git(repo, "branch", "--show-current")

    result = drive(Finalize(repo_dir=str(repo)), _env(tmp_path))

    assert int(_git(repo, "rev-list", "--count", "HEAD")) == before + 1
    assert _git(repo, "branch", "--show-current") == branch
    assert _git(repo, "log", "-1", "--pretty=%s") == "author: milestone account-access"
    assert "status: authored" in (repo / MILESTONE).read_text(encoding="utf-8")
    assert result.committed is True, result


def test_terminal_validation_commits_incomplete_then_fails(repo: Path, tmp_path: Path) -> None:
    _planning_graph(repo, selectable=False)
    (repo / "docs" / "notes.md").write_text("# Notes\n\nWork the run left under docs.\n", encoding="utf-8")
    before = int(_git(repo, "rev-list", "--count", "HEAD"))

    with pytest.raises(WorkflowFailed, match="authored artifacts did not validate"):
        drive(Finalize(repo_dir=str(repo)), _env(tmp_path))

    assert int(_git(repo, "rev-list", "--count", "HEAD")) == before + 1
    assert _git(repo, "log", "-1", "--pretty=%s") == (
        "author: INCOMPLETE — milestone account-access, do not merge"
    )
    assert "status: approved" in (repo / MILESTONE).read_text(encoding="utf-8")


class _Checks:
    """Scripted closing checks: each name maps to the verdicts it returns, in order, the last one repeating."""

    def __init__(self, repo: Path, **verdicts: list[bool]) -> None:
        self.repo = repo
        self.verdicts = {"reconcile": [True], "integrity": [True], "milestone": [True], **verdicts}
        self.events: list[str] = []
        self.gates: list[str] = []
        self.decisions: list[str] = []

    def _next(self, name: str) -> bool:
        self.events.append(name)
        queue = self.verdicts[name]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def nodes(self) -> Any:
        def reconcile(logger: Any, *args: Any, **kwargs: Any) -> VerifyReport:
            holds = self._next("reconcile")
            return VerifyReport(holds=holds, errors="" if holds else "reconcile drifted")

        def integrity(logger: Any, *args: Any, **kwargs: Any) -> VerifyReport:
            holds = self._next("integrity")
            return VerifyReport(holds=holds, errors="" if holds else "integrity broken")

        def milestone(logger: Any, *args: Any, **kwargs: Any) -> Defects:
            ok = self.verdicts["milestone"][0] if self.events[-1:] == ["close"] else self._next("milestone")
            return Defects(ok=ok, errors="" if ok else "milestone epics wrong")

        def artifacts(logger: Any, *args: Any, **kwargs: Any) -> Defects:
            self.events.append("close")
            return Defects(ok=True)

        def mark(logger: Any, *args: Any, **kwargs: Any) -> MilestoneStatus:
            return MilestoneStatus()

        def commit(logger: Any, *args: Any, **kwargs: Any) -> Committed:
            self.events.append("commit")
            return Committed(committed=True)

        return workflow.override(
            verify_reconcile=reconcile,
            verify_integrity=integrity,
            validate_milestone_epics=milestone,
            validate_artifacts=artifacts,
            mark_milestone_authored=mark,
            commit_author=commit,
        )

    def agent(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        assert Path(node.prompt).stem == "resolve-integrity"
        self.events.append("resolve")
        decision = self.decisions.pop(0) if self.decisions else "repaired"
        return "scripted", {"decision": decision, "notes": ""}

    def answered(self, path: Path, **kwargs: Any) -> None:
        self.gates.append(path.read_text(encoding="utf-8"))


def _verify(repo: Path, tmp_path: Path, checks: _Checks, mode: str = "auto") -> Any:
    _planning_graph(repo, selectable=True)
    env = replace(_env(tmp_path), nodes=checks.nodes(), agent_runner=StubRunner(checks.agent))
    with patch.object(pyflow_park, "wait_for_answer", checks.answered):
        return drive(Finalize(repo_dir=str(repo), operator_mode=mode), env)


def test_a_repaired_check_runs_again_before_the_next_one(repo: Path, tmp_path: Path) -> None:
    checks = _Checks(repo, integrity=[False, True])

    result = _verify(repo, tmp_path, checks)

    assert result.committed is True
    assert checks.events == ["reconcile", "integrity", "resolve", "integrity", "milestone", "close", "commit"]
    assert checks.gates == []


def test_a_check_the_agent_cannot_repair_parks_after_its_budget_and_the_next_check_runs(
    repo: Path, tmp_path: Path
) -> None:
    checks = _Checks(repo, integrity=[False])

    _verify(repo, tmp_path, checks)

    assert checks.events.count("resolve") == MAX_INTEGRITY_RESOLVES
    assert checks.events[-3:] == ["milestone", "close", "commit"]
    assert len(checks.gates) == 1 and "integrity broken" in checks.gates[0]


def test_a_human_operator_is_asked_before_any_repair(repo: Path, tmp_path: Path) -> None:
    checks = _Checks(repo, milestone=[False, True])

    _verify(repo, tmp_path, checks, mode="human")

    assert "resolve" not in checks.events
    assert len(checks.gates) == 1 and "milestone epics wrong" in checks.gates[0]


def test_a_reconcile_drift_parks_without_a_repair(repo: Path, tmp_path: Path) -> None:
    checks = _Checks(repo, reconcile=[False])

    _verify(repo, tmp_path, checks)

    assert checks.events[:2] == ["reconcile", "integrity"]
    assert "resolve" not in checks.events
    assert len(checks.gates) == 1 and "reconcile drifted" in checks.gates[0]


def test_an_escalated_repair_parks_and_the_next_check_runs(repo: Path, tmp_path: Path) -> None:
    checks = _Checks(repo, integrity=[False])
    checks.decisions = ["escalated"]

    _verify(repo, tmp_path, checks)

    assert checks.events[:4] == ["reconcile", "integrity", "resolve", "milestone"]
    assert len(checks.gates) == 1 and "integrity broken" in checks.gates[0]
