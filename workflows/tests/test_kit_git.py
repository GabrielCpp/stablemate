"""What `kit.git`'s two committing helpers are allowed to stage.

The distinction they draw is the whole point of the file. A workflow run is frequently
launched *from* a checkout somebody else is working in — `repo_dir` is the launch
directory unless a `--param` says otherwise — so "commit my work" and "commit the
working tree" are different operations with very different blast radii, and the
difference has to be visible at the call site.

Git runs for real here against a throwaway repo (`workhorse.testing.make_git_repo`);
there is nothing to monkeypatch.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from git.exc import GitError

from workhorse.testing import make_git_repo
from workhorse_workflows.kit.git import commit_all, commit_paths


def _tracked(root: Path, ref: str = "HEAD") -> set[str]:
    """The paths touched by commit ``ref``."""
    out = subprocess.run(
        ["git", "show", "--name-only", "--pretty=format:", ref],
        cwd=str(root),
        check=True,
        capture_output=True,
        text=True,
    )
    return {line for line in out.stdout.splitlines() if line}


def _head_subject(root: Path) -> str:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=str(root), check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def _write(root: Path, rel: str, text: str = "x\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_commit_paths_stages_only_the_named_paths(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    _write(root, "docs/epics/index.md")
    _write(root, "src/unrelated.py")  # somebody else's in-flight edit

    assert commit_paths(root, "author: epic backlog authoring", "docs") is True
    assert _tracked(root) == {"docs/epics/index.md"}
    assert (root / "src/unrelated.py").exists()  # left in the working tree, uncommitted


def test_commit_paths_with_no_pathspecs_commits_nothing(tmp_path: Path) -> None:
    """The regression this file exists for.

    `commit_paths(root, msg, *changed)` with an empty `changed` used to fall through to
    `git add -A` — a caller that computed "nothing changed" got a commit of the entire
    working tree instead of no commit at all.
    """
    root = make_git_repo(tmp_path / "acme")
    _write(root, "src/unrelated.py")

    assert commit_paths(root, "should not land") is False
    assert _head_subject(root) == "init"
    assert _tracked(root) == {"README.md"}


def test_commit_paths_is_false_when_the_scope_did_not_change(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    _write(root, "src/unrelated.py")

    assert commit_paths(root, "author: nothing to say", "docs") is False
    assert _head_subject(root) == "init"


def test_commit_all_still_sweeps_the_whole_tree(tmp_path: Path) -> None:
    """The deliberate sweep survives — it is correct in a checkout the run owns."""
    root = make_git_repo(tmp_path / "acme")
    _write(root, "docs/epics/index.md")
    _write(root, "src/unrelated.py")

    assert commit_all(root, "coder: STORY-1") is True
    assert _tracked(root) == {"docs/epics/index.md", "src/unrelated.py"}


def test_commit_all_is_false_on_a_clean_tree(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    assert commit_all(root, "nothing") is False
    assert _head_subject(root) == "init"


def test_commit_helpers_are_fail_soft_off_a_repo(tmp_path: Path) -> None:
    """A bad path returns False rather than raising into an unattended run."""
    not_a_repo = tmp_path / "nowhere"
    not_a_repo.mkdir()
    assert commit_paths(not_a_repo, "m", "docs") is False
    assert commit_all(not_a_repo, "m") is False


def test_a_refused_commit_raises_instead_of_reading_as_an_empty_one(tmp_path: Path) -> None:
    """The regression that killed a real run.

    A stale `.git/index.lock` makes `git add` refuse. Both helpers used to swallow that
    and return False — the same value they return for a clean tree — so the coder's
    zero-diff guard counted three stories' worth of *refused* commits as three stories
    that did no work and stopped the run, with the git error printed nowhere and the work
    still sitting in the tree.
    """
    root = make_git_repo(tmp_path / "acme")
    _write(root, "src/feature.py")
    (root / ".git" / "index.lock").write_text("", encoding="utf-8")

    with pytest.raises(GitError):
        commit_all(root, "coder: STORY-1")
    with pytest.raises(GitError):
        commit_paths(root, "coder: STORY-1", "src")

    (root / ".git" / "index.lock").unlink()
    assert commit_all(root, "coder: STORY-1") is True  # and it lands once git will take it
