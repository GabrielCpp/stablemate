"""A story's change: its own commits and the uncommitted work on a shared trunk, the range on its own branch."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.coder.shared.provenance import changed_files, story_change

Git = Callable[..., subprocess.CompletedProcess]
Commit = Callable[[Path, dict[str, str], str | None], str]
LOGGER = logging.getLogger("test.story_change")


def test_on_trunk_the_change_is_the_storys_commits_and_the_uncommitted_work(
    repo: Path, commit_story: Commit, git: Git
) -> None:
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    commit_story(repo, {"api/a.go": "a\n"}, "acme-1")
    commit_story(repo, {"web/b.ts": "b\n"}, "acme-2")
    commit_story(repo, {"api/c.go": "c\n"}, "acme-1")
    (repo / "api/d.go").write_text("d\n", encoding="utf-8")

    change = story_change(repo, ("acme-1",))

    assert set(change.files) == {"api/a.go", "api/c.go", "api/d.go"}
    assert change.base == base
    assert change.narrowed
    assert change.among == 3
    assert len(change.commits) == 2


def test_on_a_story_branch_the_change_is_the_range(
    repo: Path, commit_story: Commit, git: Git
) -> None:
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "-b", "story")
    commit_story(repo, {"x.go": "x\n"}, "acme-1")
    git(repo, "rm", "-q", "x.go")
    git(repo, "commit", "-qm", "feat(acme): drop\n\nStory: acme-1")
    commit_story(repo, {"kept.go": "k\n"}, "acme-1")
    (repo / "dirty.go").write_text("d\n", encoding="utf-8")

    change = story_change(repo, ("acme-1",))

    tracked = git(repo, "diff", "--name-only", "--no-renames", base).stdout.split()
    assert change.whole
    assert not change.narrowed
    assert list(change.files) == [*tracked, "dirty.go"]
    assert "x.go" not in change.files
    assert change.reading == f"story acme-1: 3 commit(s), the whole range since {base}"


def test_before_the_first_story_commit_the_change_is_the_uncommitted_work(
    repo: Path, git: Git
) -> None:
    (repo / "README.md").write_text("# changed\n", encoding="utf-8")
    (repo / "new.go").write_text("n\n", encoding="utf-8")

    change = story_change(repo, ("acme-1",))

    assert change.base == git(repo, "rev-parse", "HEAD").stdout.strip()
    assert set(change.files) == {"README.md", "new.go"}
    assert change.commits == ()
    assert not change.narrowed
    assert change.reading == f"the range since {change.base}, no commit carries 'Story: acme-1'"


def test_a_trailer_naming_a_longer_id_is_not_the_storys(repo: Path, commit_story: Commit) -> None:
    commit_story(repo, {"api/a.go": "a\n"}, "acme-12")

    change = story_change(repo, ("acme-1",))

    assert change.commits == ()
    assert changed_files(LOGGER, str(repo), "", "acme-1").paths == []


def test_changed_files_on_trunk_leaves_out_other_work(repo: Path, commit_story: Commit) -> None:
    commit_story(repo, {"api/a.go": "a\n"}, "acme-1")
    commit_story(repo, {"web/b.ts": "b\n"}, "acme-2")

    assert changed_files(LOGGER, str(repo), "", "acme-1").paths == ["api/a.go"]
