"""A follow-up's own follow-ups land in the backlog as a commit, so the story's tree stays clean."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.coder.shared.backlog import file_follow_up_backlog
from workhorse_workflows.coder.shared.story_commit import check_repos_clean


def test_the_filed_follow_ups_are_committed_and_leave_the_tree_clean(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    write(repo / "docs" / "backlog.md", "# Backlog\n\n## Filed by coder\n")
    git(repo, "add", "docs/backlog.md")
    git(repo, "commit", "-qm", "seed the backlog")

    drained = file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[{"title": "Clear the cache on sign-out", "reason": "the slice works without it"}],
        repo_dir=str(repo),
    )

    assert drained.appended == 1, drained
    assert "Clear the cache on sign-out" in (repo / "docs" / "backlog.md").read_text(encoding="utf-8")
    subject = git(repo, "log", "-1", "--format=%s").stdout.strip()
    assert subject == "chore(acme): file the follow-ups of acme-story", subject
    assert check_repos_clean(logger, story_slug="acme-story", repo_dir=str(repo)).clean is True


def test_nothing_filed_commits_nothing(
    repo: Path,
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    head = git(repo, "rev-parse", "HEAD").stdout

    drained = file_follow_up_backlog(
        logger, parent="acme-story", follow_ups=[{"title": "", "reason": "no title"}], repo_dir=str(repo)
    )

    assert drained.appended == 0, drained
    assert git(repo, "rev-parse", "HEAD").stdout == head
