"""The folders a worktree run reads: books in its artifacts worktree, code in its member worktrees."""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from _workspace import Workspace, cut_run_worktrees
from workhorse_workflows.coder.shared import story, story_commit, worktree
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


@pytest.mark.parametrize("start", ["api", "artifacts"])
def test_a_file_already_untracked_in_a_member_repo_is_not_the_storys_leftover(
    workspace: Workspace, logger: logging.Logger, start: str
) -> None:
    """The snapshot read the book root only, so the review of a workspace story looped on files it never wrote."""
    (workspace.api / "notes.txt").write_text("the operator's own\n", encoding="utf-8")
    repo_dir = str(getattr(workspace, start))

    dirty = worktree.snapshot_worktree_state(logger, repo_dir=repo_dir, workspace="acme")
    clean = story_commit.check_repos_clean(
        logger,
        preexisting=dirty.entries,
        repo_dir=repo_dir,
        workspace="acme",
        roots=[str(workspace.api)],
    )

    assert clean.clean, clean.dirty


def test_in_one_repo_the_snapshot_names_no_checkout(tmp_path: Path, git: Git, logger: logging.Logger) -> None:
    """An entry of a single repository carries no owner, so every lane that reads it by path still matches."""
    repo = tmp_path / "solo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "agents.yml").write_text("book:\n  home: repo\n", encoding="utf-8")
    git(repo, "add", "agents.yml")
    git(repo, "commit", "-qm", "Initial commit")
    (repo / "scratch.py").write_text("x = 1\n", encoding="utf-8")

    dirty = worktree.snapshot_worktree_state(logger, repo_dir=str(repo))

    assert [entry.count("\0") for entry in dirty.entries] == [1], dirty.entries
