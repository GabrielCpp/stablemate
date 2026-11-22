"""The run branch opens the book branch: a worktree of the artifacts repository on the code branch's name."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from _workspace import Workspace, cut_run_worktrees
from workhorse._vendor.stablemate_core import book_branch, config

from workhorse_workflows.coder.shared import branches

Git = Callable[..., subprocess.CompletedProcess]


@pytest.fixture
def worktrees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "worktrees"
    path = tmp_path / "home-config.toml"
    path.write_text(f'worktree_dir = "{folder}"\n', encoding="utf-8")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(path))
    return folder


def _lone(tmp_path: Path, git: Git, *, key: str = "") -> Path:
    root = tmp_path / "lone"
    root.mkdir()
    (root / "agents.yml").write_text(f"repo:\n  id_prefix: X\n{key}", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "Initial commit")
    return root


def _book_worktrees(git: Git) -> list[str]:
    top = config.ensure_artifacts_repo()
    listing = git(top, "worktree", "list", "--porcelain").stdout
    return [line for line in listing.splitlines() if line.startswith("worktree ")]


def test_a_pr_run_in_a_lone_repository_cuts_the_book_worktree_and_leaves_the_artifacts_main_folder_on_its_base(
    tmp_path: Path, worktrees: Path, logger: logging.Logger, git: Git
) -> None:
    lone = _lone(tmp_path, git)
    artifacts = config.ensure_artifacts_repo()
    base = git(artifacts, "branch", "--show-current").stdout.strip()

    cut = branches.cut_run_branch(logger, "story-one", repo_dir=str(lone))

    assert cut.branch == "feat/story-one"
    assert git(lone, "branch", "--show-current").stdout.strip() == "feat/story-one"
    assert git(artifacts, "branch", "--show-current").stdout.strip() == base
    book = config.checkout_on(artifacts, "feat/story-one")
    assert book != artifacts
    assert book == book_branch.book_worktree_path("feat/story-one").resolve()
    assert book.parent == worktrees.resolve()


def test_a_pr_run_with_book_in_repo_cuts_no_book_worktree(
    tmp_path: Path, worktrees: Path, logger: logging.Logger, git: Git
) -> None:
    lone = _lone(tmp_path, git, key="book:\n  home: repo\n")

    cut = branches.cut_run_branch(logger, "story-one", repo_dir=str(lone))

    assert cut.branch == "feat/story-one"
    assert git(lone, "branch", "--show-current").stdout.strip() == "feat/story-one"
    assert len(_book_worktrees(git)) == 1
    assert not worktrees.exists()


def test_a_pr_run_in_a_workspace_never_switches_the_artifacts_main_folder(
    workspace: Workspace, worktrees: Path, logger: logging.Logger, git: Git
) -> None:
    base = git(workspace.artifacts, "branch", "--show-current").stdout.strip()

    cut = branches.cut_run_branch(logger, "story-one", repo_dir=str(workspace.api))

    assert cut.branch == "feat/story-one"
    assert git(workspace.artifacts, "branch", "--show-current").stdout.strip() == base
    assert config.checkout_on(workspace.artifacts, "feat/story-one") != workspace.artifacts


def test_a_worktree_run_in_a_lone_repository_cuts_the_book_worktree_once(
    tmp_path: Path, worktrees: Path, logger: logging.Logger, git: Git
) -> None:
    lone = _lone(tmp_path, git)
    tree = tmp_path / "lone-run"
    git(lone, "worktree", "add", "-q", "-b", "run/coder-t", str(tree))

    first = branches.cut_run_branch(logger, "story-one", repo_dir=str(tree))
    second = branches.cut_run_branch(logger, "story-one", repo_dir=str(tree))

    assert first.branch == second.branch == "run/coder-t"
    assert git(tree, "branch", "--show-current").stdout.strip() == "run/coder-t"
    artifacts = config.ensure_artifacts_repo()
    assert config.checkout_on(artifacts, "run/coder-t") == book_branch.book_worktree_path("run/coder-t").resolve()
    assert len(_book_worktrees(git)) == 2


def test_a_worktree_run_keeps_its_branch_and_reuses_the_book_worktree(
    workspace: Workspace, tmp_path: Path, worktrees: Path, logger: logging.Logger, git: Git
) -> None:
    trees = cut_run_worktrees(workspace, tmp_path / "trees", "run/coder-t", git)
    before = _book_worktrees(git)

    cut = branches.cut_run_branch(logger, "story-one", repo_dir=str(trees.api))

    assert cut.branch == "run/coder-t"
    assert _book_worktrees(git) == before
    assert config.checkout_on(workspace.artifacts, "run/coder-t") == trees.artifacts
