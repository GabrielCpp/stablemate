"""What `kit.git`'s two committing helpers are allowed to stage."""
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
    _write(root, "src/unrelated.py")

    assert commit_paths(root, "author: epic backlog authoring", "docs") is True
    assert _tracked(root) == {"docs/epics/index.md"}
    assert (root / "src/unrelated.py").exists()


def test_commit_paths_with_no_pathspecs_commits_nothing(tmp_path: Path) -> None:
    """The regression this file exists for."""
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


def _reject_commits(root: Path) -> None:
    """Install a pre-commit hook that refuses every commit."""
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho refused by the repo hook >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)


def test_commit_paths_runs_the_repo_hooks_unless_told_not_to(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path / "acme")
    _reject_commits(root)
    _write(root, "docs/features/api/index.md")

    with pytest.raises(GitError):
        commit_paths(root, "docs: update the book", "docs")
    assert _head_subject(root) == "init"

    assert commit_paths(root, "docs: update the book", "docs", verify=False) is True
    assert _tracked(root) == {"docs/features/api/index.md"}


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
    """The regression that killed a real run."""
    root = make_git_repo(tmp_path / "acme")
    _write(root, "src/feature.py")
    (root / ".git" / "index.lock").write_text("", encoding="utf-8")

    with pytest.raises(GitError):
        commit_all(root, "coder: STORY-1")
    with pytest.raises(GitError):
        commit_paths(root, "coder: STORY-1", "src")

    (root / ".git" / "index.lock").unlink()
    assert commit_all(root, "coder: STORY-1") is True
