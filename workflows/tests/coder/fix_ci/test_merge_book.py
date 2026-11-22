"""`merge_pr` lands the book branch right after the code PR merges."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from _workspace import Workspace
from workhorse._vendor.stablemate_core import book_branch

from workhorse_workflows.coder.fix_ci import merge

Git = Callable[..., subprocess.CompletedProcess]


@pytest.fixture
def merging(workspace: Workspace, tmp_path: Path, git: Git, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    config = tmp_path / "home-config.toml"
    config.write_text(
        f'worktree_dir = "{tmp_path / "worktrees"}"\n' + config.read_text(encoding="utf-8"), encoding="utf-8"
    )
    git(workspace.api, "remote", "add", "origin", "https://github.com/acme/api.git")
    pull = SimpleNamespace(merge=lambda merge_method: None)
    forge = SimpleNamespace(allow_merge_commit=True)
    monkeypatch.setattr(merge, "resolve_github_token", lambda root: "token")
    monkeypatch.setattr(merge, "resolve_repo", lambda root, token: (forge, "acme/api"))
    monkeypatch.setattr(merge, "find_open_pr", lambda repo, branch: pull)
    monkeypatch.setattr(merge, "sync_to_origin", lambda root, token, base: "abc1234")
    return workspace


def _book(git: Git, workspace: Workspace) -> Path:
    book = book_branch.open_book_branch(workspace.api, "feat/EPIC-1")
    (book / "epic.md").write_text("epic", encoding="utf-8")
    git(book, "add", "-A")
    git(book, "commit", "-qm", "add epic")
    return book


def test_merge_pr_lands_the_book_branch_after_the_code_merges(merging: Workspace, git: Git) -> None:
    book = _book(git, merging)

    outcome = merge.merge_pr(logging.getLogger("test.merge"), "EPIC-1", "main", repo_dir=str(merging.api))

    assert outcome.merge_status == "merged"
    assert (merging.artifacts / "epic.md").is_file()
    assert not book.exists()
    assert git(merging.artifacts, "rev-list", "--merges", "--count", "HEAD").stdout.strip() == "0"


def test_merge_pr_leaves_the_book_branch_when_the_artifacts_repo_has_an_origin(
    merging: Workspace, tmp_path: Path, git: Git
) -> None:
    git(merging.artifacts, "remote", "add", "origin", "https://github.com/acme/book.git")
    book = _book(git, merging)

    merge.merge_pr(logging.getLogger("test.merge"), "EPIC-1", "main", repo_dir=str(merging.api))

    assert book.is_dir()
    assert not (merging.artifacts / "epic.md").exists()
