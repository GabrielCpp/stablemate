"""The folders a worktree run reads: books in its artifacts worktree, code in its member worktrees."""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from _workspace import Workspace, cut_run_worktrees
from workhorse_workflows.coder.shared import story, story_commit
from workhorse_workflows.kit import find_book_root, find_docs_root, resolve_workspace

BRANCH = "run/coder-t"

Git = Callable[..., subprocess.CompletedProcess]


@pytest.fixture
def trees(workspace: Workspace, tmp_path: Path, git: Git) -> Workspace:
    return cut_run_worktrees(workspace, tmp_path / "trees", BRANCH, git)


def test_mode_a_find_book_root_is_the_artifacts_worktree_and_find_docs_root_the_main_folder(
    workspace: Workspace, trees: Workspace
) -> None:
    assert find_book_root(str(trees.api)) == trees.artifacts
    assert find_docs_root(str(trees.api)) == workspace.artifacts


def test_mode_b_find_docs_root_from_the_artifacts_worktree_is_the_main_folder(
    workspace: Workspace, trees: Workspace
) -> None:
    assert find_docs_root(str(trees.artifacts)) == workspace.artifacts


def test_mode_b_find_book_root_is_the_artifacts_worktree(trees: Workspace) -> None:
    assert find_book_root(str(trees.artifacts)) == trees.artifacts


def test_outside_a_worktree_run_the_book_root_is_the_docs_root(workspace: Workspace) -> None:
    assert find_book_root(str(workspace.api)) == workspace.artifacts


@pytest.mark.parametrize("start", ["api", "artifacts"])
def test_resolve_workspace_maps_members_to_their_run_worktrees(
    workspace: Workspace, trees: Workspace, start: str
) -> None:
    repos = resolve_workspace("acme", str(getattr(trees, start)))

    assert repos["api"]["path"] == str(trees.api)
    assert repos["web"]["path"] == str(trees.web)


def test_resolve_workspace_dirs_holds_the_docs_root_the_book_root_and_the_member_worktrees(
    workspace: Workspace, trees: Workspace, logger: logging.Logger
) -> None:
    dirs = story.resolve_workspace_dirs(logger, repo_dir=str(trees.api), workspace="acme").dirs

    assert {str(workspace.artifacts), str(trees.artifacts), str(trees.api), str(trees.web)} <= set(dirs)
    assert str(workspace.api) not in dirs


def test_a_story_commit_in_mode_b_commits_in_the_member_worktree(
    workspace: Workspace,
    trees: Workspace,
    logger: logging.Logger,
    git: Git,
    write: Callable[[Path, str], Path],
) -> None:
    spec = workspace.artifacts / "specs" / "s1"
    write(spec / "plan-context.json", json.dumps({"services": [{"repo": "api"}]}))
    main_head = git(workspace.api, "rev-parse", "HEAD").stdout
    write(trees.api / "feature.py", "VALUE = 1\n")

    result = story_commit.commit_story(
        logger, story_slug="s1", spec_dir=str(spec), repo_dir=str(trees.artifacts), workspace="acme"
    )

    assert result.committed
    assert git(trees.api, "show", "--name-only", "--format=", "HEAD").stdout.split() == ["feature.py"]
    assert git(workspace.api, "rev-parse", "HEAD").stdout == main_head

