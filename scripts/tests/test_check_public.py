"""Where `check_public.py` looks for the hook git would actually run.

The hook check failed a linked worktree while that worktree's commits were visibly being
blocked by the very hooks it reported missing. `<repo>/.git/hooks/pre-commit` is a plain
clone's layout and only a plain clone's: in a worktree `.git` is a *file*, and the hooks
live in the common directory it points at. A guard whose failure mode is "the guards are
off" has to be right about that, because the fix it prints (`make hooks`) does nothing for
a clone where they were never off.

So the layout is built rather than described — `git init`, a commit, `git worktree add` —
and the resolver is asked from inside it.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_public.py"


@pytest.fixture(scope="module")
def public() -> Any:
    spec = importlib.util.spec_from_file_location("check_public", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    root = tmp_path / "clone"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "file.txt").write_text("x\n", encoding="utf-8")
    _git(root, "add", "file.txt")
    _git(root, "commit", "-qm", "init")
    return root


def test_a_plain_clone_resolves_into_its_own_git_dir(
    public: Any, clone: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(public, "REPO", clone)
    assert public._installed_hook() == clone / ".git" / "hooks" / "pre-commit"


def test_a_worktree_resolves_into_the_common_dir(
    public: Any, clone: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression: a worktree's hooks are the clone's, and `.git` there is a file."""
    tree = tmp_path / "wt"
    _git(clone, "worktree", "add", "-q", "-b", "side", str(tree))
    assert (tree / ".git").is_file()
    monkeypatch.setattr(public, "REPO", tree)

    resolved = public._installed_hook()

    assert resolved == clone / ".git" / "hooks" / "pre-commit"
    assert not resolved.is_relative_to(tree)


def test_a_redirected_hooks_path_is_followed(
    public: Any, clone: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`core.hooksPath` means the hook in `.git/hooks` is not the one git runs."""
    _git(clone, "config", "core.hooksPath", ".githooks")
    monkeypatch.setattr(public, "REPO", clone)
    assert public._installed_hook() == clone / ".githooks" / "pre-commit"


def test_a_tree_git_will_not_answer_for_reads_as_absent(
    public: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    monkeypatch.setattr(public, "REPO", bare)
    assert public._installed_hook() == bare / ".git" / "hooks" / "pre-commit"
