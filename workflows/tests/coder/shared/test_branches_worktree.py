"""The run branch of a worktree run: it keeps the branch the launch cut and switches nothing."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from _workspace import Workspace, cut_run_worktrees
from workhorse_workflows.coder.shared import branches

BRANCH = "run/coder-t"


def test_cut_run_branch_in_a_worktree_run_keeps_the_run_branch_and_switches_nothing(
    workspace: Workspace,
    tmp_path: Path,
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    before = {
        folder: git(folder, "branch", "--show-current").stdout.strip()
        for folder in (workspace.artifacts, workspace.api, workspace.web)
    }
    trees = cut_run_worktrees(workspace, tmp_path / "trees", BRANCH, git)

    cut = branches.cut_run_branch(logger, "story-one", repo_dir=str(trees.api))

    assert cut.branch == BRANCH
    for folder in (trees.artifacts, trees.api, trees.web):
        assert git(folder, "branch", "--show-current").stdout.strip() == BRANCH
    for folder, branch in before.items():
        assert git(folder, "branch", "--show-current").stdout.strip() == branch
