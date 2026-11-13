"""Landing a run's book branch on the artifacts base, and retiring its worktree."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from workhorse.pyflow import workspace_worktrees
from workhorse.records import RunWorktree

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

BRANCH = "run/book-t"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(cwd: Path, relative: str, text: str) -> None:
    target = cwd / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    _git(cwd, "add", relative)
    _git(cwd, "commit", "-q", "-m", f"add {relative}")


@pytest.fixture
def books(tmp_path) -> tuple[RunWorktree, Path]:
    repo = tmp_path / "artifacts"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _commit(repo, ".gitignore", "specs/\n")
    tree = tmp_path / "trees" / "artifacts-run-book-t"
    _git(repo, "worktree", "add", "-q", "-b", BRANCH, str(tree))
    entry = RunWorktree(
        name="artifacts", path=str(tree), branch=BRANCH, repo=str(repo.resolve()), base="main", books=True
    )
    return entry, repo


def _branches(repo: Path) -> str:
    return _git(repo, "branch", "--list")


def test_a_book_branch_with_no_commit_lands_nothing_and_its_worktree_goes(books):
    entry, repo = books

    [done] = workspace_worktrees.end([entry])

    assert done.landing is not None and done.landing.action == "nothing"
    assert done.outcome is not None and done.outcome.action == "removed"
    assert not Path(entry.path).exists()
    assert BRANCH not in _branches(repo)


def test_a_book_commit_fast_forwards_the_artifacts_base_and_the_worktree_and_branch_go(books):
    entry, repo = books
    _commit(Path(entry.path), "services/api/service.py", "x = 1\n")

    [done] = workspace_worktrees.end([entry])

    assert done.landing is not None and done.landing.action == "landed"
    assert (repo / "services/api/service.py").read_text() == "x = 1\n"
    assert done.outcome is not None and done.outcome.action == "removed"
    assert not Path(entry.path).exists()
    assert BRANCH not in _branches(repo)


def test_a_base_that_moved_on_is_rebased_onto_then_fast_forwarded(books):
    entry, repo = books
    _commit(Path(entry.path), "services/api/a.py", "a\n")
    _commit(repo, "services/web/b.py", "b\n")

    [done] = workspace_worktrees.end([entry])

    assert done.landing is not None and done.landing.action == "rebased"
    assert (repo / "services/api/a.py").is_file()
    assert (repo / "services/web/b.py").is_file()
    assert _git(repo, "rev-list", "--count", "main") == "3"
    assert not Path(entry.path).exists()


def test_a_rebase_conflict_aborts_keeps_the_worktree_and_branch_and_names_the_files(books):
    entry, repo = books
    tree = Path(entry.path)
    _commit(tree, "services/api/journeys/a.py", "mine\n")
    tip = _git(tree, "rev-parse", BRANCH)
    _commit(repo, "services/api/journeys/a.py", "theirs\n")

    [done] = workspace_worktrees.end([entry])

    assert done.landing is not None and done.landing.action == "conflict"
    assert done.landing.files == ["services/api/journeys/a.py"]
    assert done.outcome is not None and done.outcome.action == "kept"
    assert tree.is_dir()
    assert _git(repo, "rev-parse", BRANCH) == tip
    git_dir = Path(_git(tree, "rev-parse", "--absolute-git-dir"))
    assert not (git_dir / "rebase-merge").exists()
    assert (repo / "services/api/journeys/a.py").read_text() == "theirs\n"


def test_an_artifacts_main_folder_on_another_branch_lands_nothing_and_keeps_it(books):
    entry, repo = books
    _commit(Path(entry.path), "services/api/a.py", "a\n")
    _git(repo, "checkout", "-q", "-b", "elsewhere")

    [done] = workspace_worktrees.end([entry])

    assert done.landing is not None and done.landing.action == "kept"
    assert "elsewhere" in done.landing.reason
    assert done.outcome is not None and done.outcome.action == "kept"
    assert Path(entry.path).is_dir()
    assert BRANCH in _branches(repo)


def test_every_entry_of_a_run_is_kept_for_the_reason_given(books):
    entry, _ = books

    [kept] = workspace_worktrees.keep([entry], "the run failed")

    assert kept.outcome is not None and (kept.outcome.action, kept.outcome.reason) == ("kept", "the run failed")
