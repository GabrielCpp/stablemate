"""`ostler book branch` opens the book branch of the code branch, and `ostler book land` lands it."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from book_fakes import git as _git
from conftest import write
from test_book_home_resolution import _artifacts, _ostler

BRANCH = "feat/one-rule"


def _commit(folder: Path, relative: str, text: str) -> None:
    write(folder / relative, text)
    _git(folder, "add", "--", relative)
    _git(folder, "commit", "--quiet", "-m", f"change {relative}")


def _code(tmp_path: Path, branch: str | None = BRANCH, manifest: str = "") -> Path:
    folder = tmp_path / "code" / "acme"
    folder.mkdir(parents=True)
    _git(folder, "init", "--quiet", "-b", "main")
    write(folder / "a.py", "x = 1\n")
    if manifest:
        write(folder / "agents.yml", manifest)
    _git(folder, "add", "-A")
    _git(folder, "commit", "--quiet", "-m", "init")
    if branch:
        _git(folder, "checkout", "--quiet", "-b", branch)
    return folder.resolve()


@pytest.fixture(autouse=True)
def _trees(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(f'worktree_dir = "{tmp_path / "trees"}"\n')
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))
    folder = _artifacts()
    _git(folder, "init", "--quiet", "-b", "main")
    _commit(folder, "services/acme/note.md", "one\n")


def _branch(code: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return _ostler(["book", "branch", *extra], code)


def test_branch_prints_a_new_artifacts_worktree_on_the_code_branch(tmp_path):
    code = _code(tmp_path)
    done = _branch(code)
    assert done.returncode == 0, done.stdout + done.stderr
    root = Path(done.stdout.strip())
    assert root.is_dir()
    assert root != _artifacts()
    assert root.parent == (tmp_path / "trees").resolve()
    assert _git(root, "symbolic-ref", "--short", "HEAD").strip() == BRANCH
    assert _git(_artifacts(), "symbolic-ref", "--short", "HEAD").strip() == "main"


def test_branch_twice_prints_the_same_root(tmp_path):
    code = _code(tmp_path)
    first = _branch(code)
    second = _branch(code)
    assert second.returncode == 0, second.stdout + second.stderr
    assert second.stdout == first.stdout


def test_branch_names_the_branch_it_is_given(tmp_path):
    code = _code(tmp_path, branch=None)
    done = _branch(code, "--branch", "feat/named")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(Path(done.stdout.strip()), "symbolic-ref", "--short", "HEAD").strip() == "feat/named"


def test_branch_on_the_base_branch_exits_2(tmp_path):
    code = _code(tmp_path, branch=None)
    done = _branch(code)
    assert done.returncode == 2, done.stdout + done.stderr
    assert done.stderr.startswith("error: ")
    assert "artifacts base" in done.stderr


def test_branch_on_the_declared_base_branch_exits_2(tmp_path):
    code = _code(tmp_path, branch="develop", manifest="repo:\n  base_branch: develop\n")
    done = _branch(code)
    assert done.returncode == 2, done.stdout + done.stderr
    assert "artifacts base" in done.stderr


def test_branch_on_a_detached_head_exits_2(tmp_path):
    code = _code(tmp_path)
    _git(code, "checkout", "--quiet", "--detach")
    done = _branch(code)
    assert done.returncode == 2, done.stdout + done.stderr
    assert "detached HEAD" in done.stderr


def test_branch_from_inside_the_artifacts_repository_exits_2():
    done = _branch(_artifacts())
    assert done.returncode == 2, done.stdout + done.stderr
    assert done.stderr.startswith("error: ")


def test_branch_with_book_in_repo_cuts_nothing(tmp_path):
    code = _code(tmp_path, manifest="book:\n  home: repo\n")
    done = _branch(code)
    assert done.returncode == 0, done.stdout + done.stderr
    assert Path(done.stdout.strip()) == code
    assert _git(_artifacts(), "worktree", "list", "--porcelain").count("worktree ") == 1


def test_land_rebases_and_fast_forwards_then_removes_worktree_and_branch(tmp_path):
    code = _code(tmp_path)
    root = Path(_branch(code).stdout.strip())
    _commit(root, "services/acme/two.md", "two\n")
    _commit(_artifacts(), "services/acme/three.md", "three\n")

    done = _ostler(["book", "land"], code)

    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.startswith(f"rebased {BRANCH} on 'main'")
    assert (_artifacts() / "services/acme/two.md").is_file()
    assert _git(_artifacts(), "log", "--merges", "--format=%H").strip() == ""
    assert not root.exists()
    assert BRANCH not in _git(_artifacts(), "branch", "--list")


def test_land_with_a_conflict_exits_1_and_names_files(tmp_path):
    code = _code(tmp_path)
    root = Path(_branch(code).stdout.strip())
    _commit(root, "services/acme/note.md", "from the branch\n")
    _commit(_artifacts(), "services/acme/note.md", "from the base\n")

    done = _ostler(["book", "land"], code)

    assert done.returncode == 1, done.stdout + done.stderr
    assert done.stdout.startswith(f"conflict {BRANCH} on 'main'")
    assert "services/acme/note.md" in done.stdout
    assert root.is_dir()
    assert BRANCH in _git(_artifacts(), "branch", "--list")


def test_land_of_a_branch_with_no_commit_removes_worktree_and_branch(tmp_path):
    code = _code(tmp_path)
    root = Path(_branch(code).stdout.strip())

    done = _ostler(["book", "land", "--branch", BRANCH], code)

    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.startswith(f"nothing {BRANCH} on 'main'")
    assert not root.exists()
