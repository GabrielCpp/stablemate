"""`farrier worktrees`: what the sweep removes, what it keeps, and that a listing changes nothing."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from farrier import cli
from farrier.worktree_sweep import discover_repos, last_touched, process_cwds, sweep_repo

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

WEEKS_AGO = time.time() - 30 * 86_400


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "doc.md").write_text("committed\n")
    _git(path, "add", "doc.md")
    _git(path, "commit", "-q", "-m", "one")
    return path


def _age(worktree: Path) -> None:
    git_dir = Path(_git(worktree, "rev-parse", "--absolute-git-dir"))
    for name in ("HEAD", "index", "logs/HEAD"):
        if (git_dir / name).exists():
            os.utime(git_dir / name, (WEEKS_AGO, WEEKS_AGO))


def _worktree(repo: Path, name: str, *, old: bool = True) -> Path:
    path = repo.parent / name
    _git(repo, "worktree", "add", "-q", "-b", name, str(path))
    if old:
        _age(path)
    return path


def _branch_exists(repo: Path, branch: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        check=False,
    ).returncode == 0


def _sweep(repo: Path, *, apply: bool, cwds: set[Path] | None = None) -> dict[str, tuple[str, str]]:
    rows = sweep_repo(repo.resolve(), apply=apply, idle_days=7, now=time.time(), cwds=cwds or set())
    return {row.path.name: (row.action, row.reason) for row in rows}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _repo(tmp_path / "acme")


def test_listing_marks_a_landed_worktree_and_changes_nothing(repo: Path):
    path = _worktree(repo, "landed")

    assert _sweep(repo, apply=False)["landed"] == ("remove", "merged into 'main'")
    assert path.is_dir()
    assert _branch_exists(repo, "landed")


def test_listing_does_not_reset_the_idle_clock(repo: Path):
    path = _worktree(repo, "landed")
    os.utime(path / "doc.md", (WEEKS_AGO, WEEKS_AGO))
    before = last_touched(path)

    _sweep(repo, apply=False)

    assert last_touched(path) == before


def test_apply_removes_a_landed_worktree_and_its_branch(repo: Path):
    path = _worktree(repo, "landed")

    assert _sweep(repo, apply=True)["landed"][0] == "removed"
    assert not path.exists()
    assert not _branch_exists(repo, "landed")


def test_recently_touched_worktree_stays_though_it_looks_landed(repo: Path):
    path = _worktree(repo, "fresh", old=False)

    action, reason = _sweep(repo, apply=True)["fresh"]

    assert (action, reason) == ("keep", "touched less than 7 days ago")
    assert path.is_dir()


def test_locked_worktree_stays(repo: Path):
    path = _worktree(repo, "standing")
    _git(repo, "worktree", "lock", str(path))

    assert _sweep(repo, apply=True)["standing"] == ("keep", "locked")
    assert path.is_dir()


def test_uncommitted_change_stays(repo: Path):
    path = _worktree(repo, "dirty")
    (path / "scratch.md").write_text("not committed\n")

    assert _sweep(repo, apply=True)["dirty"] == ("keep", "the worktree has uncommitted changes")
    assert (path / "scratch.md").exists()


def test_unmerged_commit_stays(repo: Path):
    path = _worktree(repo, "ahead", old=False)
    (path / "feature.md").write_text("feature\n")
    _git(path, "add", "feature.md")
    _git(path, "commit", "-q", "-m", "feature")
    _age(path)

    action, reason = _sweep(repo, apply=True)["ahead"]

    assert action == "keep"
    assert "neither merged into 'main' nor pushed" in reason
    assert path.is_dir()


def test_worktree_a_process_holds_stays(repo: Path):
    path = _worktree(repo, "busy")

    outcome = _sweep(repo, apply=True, cwds={path.resolve() / "src"})

    assert outcome["busy"] == ("keep", "a running process is using it")
    assert path.is_dir()


def test_real_process_is_seen_in_its_worktree(repo: Path):
    if process_cwds() is None:
        pytest.skip("needs /proc")
    path = _worktree(repo, "busy")
    child = subprocess.Popen(["sleep", "30"], cwd=path)
    try:
        cwds = process_cwds()
        assert cwds is not None and path.resolve() in cwds
    finally:
        child.kill()
        child.wait()


def test_platform_that_cannot_see_processes_removes_nothing(repo: Path, tmp_path: Path):
    path = _worktree(repo, "landed")

    assert process_cwds(tmp_path / "no-proc") is None
    rows = sweep_repo(repo.resolve(), apply=True, idle_days=7, now=time.time(), cwds=None)

    assert [row.action for row in rows] == ["keep"]
    assert path.is_dir()


def test_entry_whose_folder_is_gone_is_pruned_only_on_apply(repo: Path):
    path = _worktree(repo, "stale")
    shutil.rmtree(path)

    assert _sweep(repo, apply=False)["stale"][0] == "prune"
    assert "stale" in _git(repo, "worktree", "list")

    assert _sweep(repo, apply=True)["stale"][0] == "pruned"
    assert "stale" not in _git(repo, "worktree", "list")


def test_discovery_reads_a_checkout_a_folder_of_checkouts_and_the_worktree_dir(tmp_path: Path):
    one = _repo(tmp_path / "code" / "one")
    two = _repo(tmp_path / "code" / "two")
    (tmp_path / "code" / "notes").mkdir()
    three = _repo(tmp_path / "three")
    _git(three, "worktree", "add", "-q", "-b", "side", str(tmp_path / "linked" / "three-side"))

    repos = discover_repos([tmp_path / "code", one], tmp_path / "linked")

    assert repos == sorted(path.resolve() for path in (one, two, three))


def test_command_lists_then_applies(repo: Path, tmp_path: Path, monkeypatch, capsys):
    path = _worktree(repo, "landed")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setattr(cli, "process_cwds", lambda: set())

    assert cli.main(["worktrees", str(repo)]) == 0
    listing = capsys.readouterr().out
    assert "remove" in listing and "merged into 'main'" in listing
    assert "--apply" in listing
    assert path.is_dir()

    assert cli.main(["worktrees", str(repo), "--apply"]) == 0
    assert "removed" in capsys.readouterr().out
    assert not path.exists()
