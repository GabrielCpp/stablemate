from __future__ import annotations

import logging
from pathlib import Path

from _milestones import milestone_folder, milestone_key, write_milestone
from git import Repo
from workhorse_workflows.author.shared.nodes.commit import commit_author
from workhorse_workflows.kit.paths import artifacts_root

LOGGER = logging.getLogger("test.author")


def _artifacts_repo() -> Repo:
    artifacts = artifacts_root()
    artifacts.mkdir(parents=True, exist_ok=True)
    git = Repo.init(artifacts)
    with git.config_writer() as writer:
        writer.set_value("user", "name", "Author Test")
        writer.set_value("user", "email", "author@example.com")
    return git


def test_the_author_commit_ships_the_milestone_folder_in_the_artifacts_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    write_milestone(repo)
    git = _artifacts_repo()

    result = commit_author(LOGGER, milestone=milestone_key(repo), repo_dir=str(repo))

    assert result.committed
    assert git.head.commit.message.strip() == "author: milestone account-access"
    shipped = git.git.show("--name-only", "--format=", "HEAD").splitlines()
    assert shipped == [milestone_key(repo)]
    assert milestone_folder(repo).is_dir()


def test_a_milestone_outside_a_git_artifacts_folder_commits_nothing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    write_milestone(repo)

    result = commit_author(LOGGER, milestone=milestone_key(repo), repo_dir=str(repo))

    assert not result.committed
