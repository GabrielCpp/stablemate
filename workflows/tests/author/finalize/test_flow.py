from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

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
from workhorse_workflows.author.main.nodes import artifacts as artifact_nodes

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


@pytest.fixture(autouse=True)
def _no_ambient_token(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "WORKHORSE_GIT_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def test_finalizes_with_one_commit_and_reuses_the_open_pr(repo: Path, tmp_path: Path) -> None:
    _planning_graph(repo, selectable=True)
    before = int(_git(repo, "rev-list", "--count", "HEAD"))
    gh_repo = Mock()
    existing = SimpleNamespace(html_url="https://github.com/example/acme/pull/7")

    with (
        patch.object(artifact_nodes.github_kit, "resolve_github_token", return_value="token"),
        patch.object(artifact_nodes, "_resolve_github_slug", return_value="example/acme"),
        patch.object(artifact_nodes.github_kit, "push_branch", return_value=True) as push,
        patch.object(artifact_nodes.github_kit, "github_client") as client,
        patch.object(artifact_nodes.github_kit, "find_open_pr", return_value=existing),
    ):
        client.return_value.get_repo.return_value = gh_repo
        result = drive(
            Finalize(
                base_branch="main",
                author_branch="main",
                repo_dir=str(repo),
            ),
            _env(tmp_path),
        )

    assert int(_git(repo, "rev-list", "--count", "HEAD")) == before + 1
    assert _git(repo, "log", "-1", "--pretty=%s") == "author: roadmap account-access"
    assert "status: authored" in (repo / ROADMAP).read_text(encoding="utf-8")
    assert result.author_pr == "exists"
    assert result.pr_url == existing.html_url
    push.assert_called_once()
    gh_repo.create_pull.assert_not_called()


def test_terminal_validation_commits_incomplete_then_fails(repo: Path, tmp_path: Path) -> None:
    _planning_graph(repo, selectable=False)
    before = int(_git(repo, "rev-list", "--count", "HEAD"))

    with (
        patch.object(
            artifact_nodes.github_kit,
            "resolve_github_token",
            side_effect=AssertionError("delivery must not run"),
        ),
        pytest.raises(WorkflowFailed, match="authored artifacts did not validate"),
    ):
        drive(
            Finalize(
                base_branch="main",
                author_branch="main",
                repo_dir=str(repo),
            ),
            _env(tmp_path),
        )

    assert int(_git(repo, "rev-list", "--count", "HEAD")) == before + 1
    assert _git(repo, "log", "-1", "--pretty=%s") == (
        "author: INCOMPLETE — roadmap account-access, do not merge"
    )
    assert "status: approved" in (repo / ROADMAP).read_text(encoding="utf-8")
