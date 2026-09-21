"""The post-plan-turn clean-tree gate — `snapshot_worktrees` and `scrub_plan_mutations`."""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from workhorse_workflows.coder.shared.story import scrub_plan_mutations, snapshot_worktrees


@pytest.fixture
def workspace(
    tmp_path: Path, git: Callable[..., subprocess.CompletedProcess]
) -> dict[str, Path]:
    """A docs repo and two code repos, all named by one workspace file."""
    root = tmp_path / "ws"
    repos: dict[str, Path] = {}
    for name in ("docs", "api", "web"):
        path = root / name
        path.mkdir(parents=True)
        git(path, "init", "-q", "-b", "main")
        git(path, "config", "user.email", "test@example.com")
        git(path, "config", "user.name", "Test")
        (path / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        git(path, "add", "README.md")
        git(path, "commit", "-qm", "Initial commit")
        repos[name] = path
    workspace_file = root / "acme.code-workspace"
    workspace_file.write_text(
        json.dumps({"folders": [{"name": n, "path": n} for n in repos]}), encoding="utf-8"
    )
    repos["workspace_file"] = workspace_file
    return repos


def _snapshot(logger: logging.Logger, workspace: dict[str, Path]) -> dict[str, str]:
    return snapshot_worktrees(
        logger,
        docs_path=str(workspace["docs"]),
        workspace_file=str(workspace["workspace_file"]),
    ).status


def _scrub(
    logger: logging.Logger, workspace: dict[str, Path], before: dict[str, str]
) -> dict[str, str]:
    return scrub_plan_mutations(
        logger,
        before,
        docs_path=str(workspace["docs"]),
        workspace_file=str(workspace["workspace_file"]),
    ).reverted


def test_the_snapshot_covers_the_code_repos_and_not_the_docs_root(
    logger: logging.Logger, workspace: dict[str, Path]
) -> None:
    (workspace["api"] / "README.md").write_text("operator WIP\n", encoding="utf-8")

    status = _snapshot(logger, workspace)

    assert set(status) == {str(workspace["api"]), str(workspace["web"])}
    assert "README.md" in status[str(workspace["api"])]
    assert status[str(workspace["web"])] == ""


def test_the_scrub_reverts_what_the_turn_wrote_and_only_that(
    logger: logging.Logger, workspace: dict[str, Path]
) -> None:
    """Fresh tracked edits are restored, fresh untracked paths deleted, prior dirt kept."""
    api, web, docs = workspace["api"], workspace["web"], workspace["docs"]
    (api / "README.md").write_text("operator WIP\n", encoding="utf-8")
    before = _snapshot(logger, workspace)

    (web / "README.md").write_text("scratch experiment\n", encoding="utf-8")
    (web / "notes.txt").write_text("scratch\n", encoding="utf-8")
    (web / "tmp").mkdir()
    (web / "tmp" / "probe.py").write_text("print()\n", encoding="utf-8")
    (docs / "plan.md").write_text("# Plan\n", encoding="utf-8")

    reverted = _scrub(logger, workspace, before)

    assert set(reverted) == {str(web)}
    assert "README.md" in reverted[str(web)]
    assert (web / "README.md").read_text(encoding="utf-8") == "# web\n"
    assert not (web / "notes.txt").exists()
    assert not (web / "tmp").exists()
    assert (api / "README.md").read_text(encoding="utf-8") == "operator WIP\n"
    assert (docs / "plan.md").exists()


def test_a_turn_that_kept_to_reading_scrubs_nothing(
    logger: logging.Logger, workspace: dict[str, Path]
) -> None:
    before = _snapshot(logger, workspace)

    assert _scrub(logger, workspace, before) == {}
