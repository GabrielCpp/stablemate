"""Opening a book branch as a worktree of the artifacts repository, and landing it on the artifacts base."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from stablemate_core import book_branch, books
from stablemate_core import config as cfgmod
from stablemate_core import worktree
from stablemate_core.config import ConfigError

from test_run_checkouts import _git, _out, _repo

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

BRANCH = "run/book-t"
IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.com")


def _commit(cwd: Path, relative: str, text: str) -> None:
    (cwd / relative).parent.mkdir(parents=True, exist_ok=True)
    (cwd / relative).write_text(text)
    _git(cwd, "add", "--", relative)
    _git(cwd, *IDENTITY, "commit", "--quiet", "--message", f"add {relative}")


def _branches(repo: Path) -> str:
    return _out(repo, "branch", "--list")


@pytest.fixture(autouse=True)
def _committer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give git an identity, because landing a branch rebases it and a machine with no git config has none."""
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "t")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "t@example.com")


@pytest.fixture
def world(tmp_path, monkeypatch, cfg_file):
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(tmp_path / "artifacts"))
    cfg_file.write_text(f'worktree_dir = "{tmp_path / "trees"}"\n')
    artifacts = _repo(tmp_path / "artifacts")
    code = _repo(tmp_path / "acme-app")
    _git(code, "checkout", "-q", "-b", BRANCH)
    return {"artifacts": artifacts, "code": code, "trees": (tmp_path / "trees").resolve()}


@pytest.fixture
def landing(tmp_path):
    repo = _repo(tmp_path / "land" / "artifacts")
    _commit(repo, ".gitignore", "specs/\n")
    tree = tmp_path / "land" / "trees" / "artifacts-run-book-t"
    _git(repo, "worktree", "add", "-q", "-b", BRANCH, str(tree))
    return repo, tree


def test_a_book_branch_with_no_commit_lands_nothing_and_its_worktree_goes(landing):
    repo, tree = landing

    result = book_branch.land(repo, tree, BRANCH, "main")
    retired = worktree.retire(path=tree, branch=BRANCH, base="main", repo_dir=repo)

    assert result.action == "nothing"
    assert retired.action == "removed"
    assert not tree.exists()
    assert BRANCH not in _branches(repo)


def test_a_book_commit_fast_forwards_the_artifacts_base(landing):
    repo, tree = landing
    _commit(tree, "services/api/service.py", "x = 1\n")

    result = book_branch.land(repo, tree, BRANCH, "main")

    assert result.action == "landed"
    assert (repo / "services/api/service.py").read_text() == "x = 1\n"


def test_a_base_that_moved_on_is_rebased_onto_then_fast_forwarded(landing):
    repo, tree = landing
    _commit(tree, "services/api/a.py", "a\n")
    _commit(repo, "services/web/b.py", "b\n")

    result = book_branch.land(repo, tree, BRANCH, "main")

    assert result.action == "rebased"
    assert (repo / "services/api/a.py").is_file()
    assert (repo / "services/web/b.py").is_file()
    assert _out(repo, "rev-list", "--count", "main") == "4"
    assert _out(repo, "rev-list", "--merges", "--count", "main") == "0"


def test_a_rebase_conflict_aborts_keeps_the_worktree_and_branch_and_names_the_files(landing):
    repo, tree = landing
    _commit(tree, "services/api/journeys/a.py", "mine\n")
    tip = _out(tree, "rev-parse", BRANCH)
    _commit(repo, "services/api/journeys/a.py", "theirs\n")

    result = book_branch.land(repo, tree, BRANCH, "main")

    assert result.action == "conflict"
    assert result.files == ("services/api/journeys/a.py",)
    assert tree.is_dir()
    assert _out(repo, "rev-parse", BRANCH) == tip
    git_dir = Path(_out(tree, "rev-parse", "--absolute-git-dir"))
    assert not (git_dir / "rebase-merge").exists()
    assert (repo / "services/api/journeys/a.py").read_text() == "theirs\n"


def test_an_artifacts_main_folder_on_another_branch_lands_nothing_and_keeps_it(landing):
    repo, tree = landing
    _commit(tree, "services/api/a.py", "a\n")
    _git(repo, "checkout", "-q", "-b", "elsewhere")

    result = book_branch.land(repo, tree, BRANCH, "main")

    assert result.action == "kept"
    assert "elsewhere" in result.reason
    assert tree.is_dir()
    assert BRANCH in _branches(repo)


def test_land_of_a_gone_branch_and_worktree_is_nothing(landing):
    repo, tree = landing
    _git(repo, "worktree", "remove", str(tree))
    _git(repo, "branch", "-D", BRANCH)

    result = book_branch.land(repo, tree, BRANCH, "main")

    assert result.action == "nothing"
    assert BRANCH in result.reason and "gone" in result.reason


def test_land_of_a_gone_branch_with_its_worktree_still_there_is_kept(landing):
    repo, tree = landing
    _git(tree, "checkout", "-q", "--detach")
    _git(repo, "branch", "-D", BRANCH)

    result = book_branch.land(repo, tree, BRANCH, "main")

    assert result.action == "kept"


def test_open_adds_a_linked_worktree_of_the_artifacts_repo_from_its_base(world):
    root = book_branch.open_book_branch(world["code"])

    expected = world["trees"] / f"artifacts-{BRANCH.replace('/', '-')}"
    assert root == expected
    assert cfgmod.checkout_on(world["artifacts"], BRANCH) == expected
    assert _out(expected, "symbolic-ref", "--short", "HEAD") == BRANCH
    assert _out(expected, "rev-parse", "HEAD") == _out(world["artifacts"], "rev-parse", "main")
    assert books.book_home(world["code"]) == expected


def test_open_is_idempotent(world):
    first = book_branch.open_book_branch(world["code"])
    second = book_branch.open_book_branch(world["code"])

    assert first == second
    assert _out(world["artifacts"], "worktree", "list", "--porcelain").count("worktree ") == 2


def test_open_on_the_artifacts_base_cuts_nothing(world):
    _git(world["artifacts"], "checkout", "-q", "-b", BRANCH)

    root = book_branch.open_book_branch(world["code"])

    assert root == world["artifacts"]
    assert _out(world["artifacts"], "worktree", "list", "--porcelain").count("worktree ") == 1


def test_open_for_a_repository_with_its_book_in_repo_cuts_nothing(world):
    (world["code"] / "agents.yml").write_text("book:\n  home: repo\n")

    root = book_branch.open_book_branch(world["code"])

    assert root == world["code"]
    assert _out(world["artifacts"], "worktree", "list", "--porcelain").count("worktree ") == 1
    assert not world["trees"].exists()


def test_open_reuses_a_branch_without_a_worktree(world):
    _git(world["artifacts"], "branch", BRANCH)

    root = book_branch.open_book_branch(world["code"])

    assert root == world["trees"] / f"artifacts-{BRANCH.replace('/', '-')}"
    assert _out(root, "symbolic-ref", "--short", "HEAD") == BRANCH


def test_open_on_a_detached_head_is_refused(world):
    _git(world["code"], "checkout", "-q", "--detach")

    with pytest.raises(ConfigError, match="detached HEAD"):
        book_branch.open_book_branch(world["code"])


def test_open_with_an_explicit_branch_ignores_the_start_head(world):
    _git(world["code"], "checkout", "-q", "--detach")

    root = book_branch.open_book_branch(world["code"], "feat/named")

    assert _out(root, "symbolic-ref", "--short", "HEAD") == "feat/named"


def test_open_with_no_worktree_dir_uses_the_data_dir(world, cfg_file, tmp_path, monkeypatch):
    cfg_file.write_text("")
    data = tmp_path / "data"
    monkeypatch.setattr(book_branch, "user_data_dir", lambda name: str(data / name))

    root = book_branch.open_book_branch(world["code"])

    assert root == (data / "stablemate" / "worktrees" / f"artifacts-{BRANCH.replace('/', '-')}").resolve()
    assert root.is_dir()


def test_close_lands_by_rebase_with_no_merge_commit_and_removes_worktree_and_branch(world):
    root = book_branch.open_book_branch(world["code"])
    artifacts = world["artifacts"]
    _commit(root, "services/api/a.py", "a\n")
    _commit(artifacts, "services/web/b.py", "b\n")

    result, retired = book_branch.close_book_branch(BRANCH)

    assert result.action == "rebased"
    assert retired is not None and retired.action == "removed" and retired.branch_deleted
    assert (artifacts / "services/api/a.py").is_file()
    assert (artifacts / "services/web/b.py").is_file()
    assert _out(artifacts, "rev-list", "--merges", "--count", "main") == "0"
    assert not root.exists()
    assert BRANCH not in _branches(artifacts)


def test_close_with_a_conflict_keeps_everything_and_names_the_files(world):
    root = book_branch.open_book_branch(world["code"])
    artifacts = world["artifacts"]
    _commit(root, "services/api/a.py", "mine\n")
    _commit(artifacts, "services/api/a.py", "theirs\n")

    result, retired = book_branch.close_book_branch(BRANCH)

    assert result.action == "conflict"
    assert result.files == ("services/api/a.py",)
    assert retired is None
    assert root.is_dir()
    assert BRANCH in _branches(artifacts)


def test_close_with_no_commit_removes_worktree_and_branch(world):
    root = book_branch.open_book_branch(world["code"])

    result, retired = book_branch.close_book_branch(BRANCH)

    assert result.action == "nothing"
    assert retired is not None and retired.action == "removed"
    assert not root.exists()
    assert BRANCH not in _branches(world["artifacts"])


def test_close_twice_lands_nothing_the_second_time(world):
    book_branch.open_book_branch(world["code"])
    book_branch.close_book_branch(BRANCH)

    result, retired = book_branch.close_book_branch(BRANCH)

    assert result.action == "nothing"
    assert retired is not None and retired.action == "removed"
