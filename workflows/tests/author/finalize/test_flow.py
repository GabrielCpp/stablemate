from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from _fakes import StubRunner
from ostler import Ostler
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows import author
from workhorse_workflows.author.finalize import Finalize
from workhorse_workflows.author.workflow import workflow

ROADMAP = "docs/roadmaps/account-access.md"
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
    _git(repo, "add", "docs/roadmaps")
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
    roadmap = repo / ROADMAP
    roadmap.parent.mkdir(parents=True)
    roadmap.write_text(
        "---\ntype: roadmap\ntitle: Account access\nstatus: approved\n---\n"
        "# Account access\n\n## User Journeys\n\nAn account holder signs in.\n",
        encoding="utf-8",
    )
    _commit(repo, "approved roadmap")

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

    milestone = repo / "docs/milestones/account-access.md"
    milestone.parent.mkdir(parents=True)
    milestone.write_text(
        "---\ntype: milestone\nid: account-access\ntitle: Account access\n"
        "status: planned\ndependsOn: []\nsourceItems:\n"
        f"  - {ROADMAP}\nepics:\n  - {EPIC}\n---\n# Account access\n",
        encoding="utf-8",
    )

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
    assert _git(repo, "log", "-1", "--pretty=%s") == "author: roadmap account-access"
    assert "status: authored" in (repo / ROADMAP).read_text(encoding="utf-8")
    assert result.committed is True, result


def test_terminal_validation_commits_incomplete_then_fails(repo: Path, tmp_path: Path) -> None:
    _planning_graph(repo, selectable=False)
    before = int(_git(repo, "rev-list", "--count", "HEAD"))

    with pytest.raises(WorkflowFailed, match="authored artifacts did not validate"):
        drive(Finalize(repo_dir=str(repo)), _env(tmp_path))

    assert int(_git(repo, "rev-list", "--count", "HEAD")) == before + 1
    assert _git(repo, "log", "-1", "--pretty=%s") == (
        "author: INCOMPLETE — roadmap account-access, do not merge"
    )
    assert "status: approved" in (repo / ROADMAP).read_text(encoding="utf-8")
