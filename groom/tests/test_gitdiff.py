"""The uncommitted-change read: the diff, the files git does not track yet, and whether the read failed."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from groom import gitdiff


def _slow_git(monkeypatch) -> None:
    monkeypatch.setattr(gitdiff, "GIT_PREFIX", [sys.executable, "-c", "import time; time.sleep(30)"])


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    )
    return done.stdout


def _checkout(base: Path) -> Path:
    repo = base / "acme"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("one\ntwo\n")
    (repo / "gone.txt").write_text("bye\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def test_a_dirty_checkout_reads_its_diff_and_names_untracked_files():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _checkout(Path(tmp))
        (repo / "src" / "app.py").write_text("one\nthree\n")
        (repo / "gone.txt").unlink()
        (repo / "src" / "new.py").write_text("x\n")
        (repo / "notes.md").write_text("y\n")
        read = gitdiff.read_local(repo, 20)
        assert read["failed"] is False
        assert read["diff"] == _git(repo, "diff", "HEAD")
        assert read["untracked"] == ["notes.md", "src/new.py"]


def test_a_clean_checkout_reads_as_empty_and_not_failed():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _checkout(Path(tmp))
        assert gitdiff.read_local(repo, 20) == {"diff": "", "untracked": [], "failed": False}


def test_ignored_files_are_not_untracked():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _checkout(Path(tmp))
        (repo / ".gitignore").write_text("*.log\n")
        _git(repo, "add", ".gitignore")
        _git(repo, "commit", "-qm", "ignore")
        (repo / "run.log").write_text("noise\n")
        assert gitdiff.read_local(repo, 20)["untracked"] == []


def test_a_directory_git_cannot_read_is_a_failed_read_not_an_empty_one():
    with tempfile.TemporaryDirectory() as tmp:
        read = gitdiff.read_local(Path(tmp), 20)
        assert read == {"diff": "", "untracked": [], "failed": True}


def test_a_missing_directory_is_a_failed_read():
    assert gitdiff.read_local(Path("/nonexistent/acme"), 20)["failed"] is True


def test_a_checkout_with_no_commit_is_a_failed_read():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git(repo, "init", "-q")
        (repo / "a.txt").write_text("a\n")
        assert gitdiff.read_local(repo, 20)["failed"] is True


def test_a_git_that_times_out_is_a_failed_read(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        repo = _checkout(Path(tmp))
        _slow_git(monkeypatch)
        assert gitdiff.read_local(repo, 0.3)["failed"] is True


def test_parse_marks_either_failing_command_as_failed():
    ok = (0, "diff --git a/x b/x\n")
    bad = (128, "")
    assert gitdiff.parse(*ok, 0, "a\0b\0")["untracked"] == ["a", "b"]
    assert gitdiff.parse(*bad, 0, "")["failed"] is True
    assert gitdiff.parse(*ok, 1, "")["failed"] is True


def _history(base: Path, default: str = "main") -> Path:
    repo = base / "acme"
    (repo / "src").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", default)
    (repo / "src" / "app.py").write_text("one\ntwo\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def _feature(repo: Path) -> str:
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "src" / "app.py").write_text("one\ntwo\nthree\n")
    (repo / "src" / "added.py").write_text("a\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "work")
    return _git(repo, "rev-parse", "HEAD~1").strip()


def _dirty(repo: Path) -> None:
    (repo / "src" / "app.py").write_text("one\ntwo\nthree\nfour\n")
    (repo / "notes.md").write_text("n\n")


def test_a_feature_branch_reads_the_whole_change_from_its_merge_base():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp))
        start = _feature(repo)
        (repo / "late.txt").write_text("l\n")
        _git(repo, "checkout", "-q", "main")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "main moves on")
        _git(repo, "checkout", "-q", "feature")
        _dirty(repo)
        read = gitdiff.read_branch_local(repo, 20)
        assert read["failed"] is False
        assert read["base"] == start
        assert read["base_branch"] == "main"
        assert read["base_ref"] == "main"
        assert read["base_reason"] == ""
        assert read["diff"] == _git(repo, "diff", _git(repo, "merge-base", "HEAD", "main").strip())
        assert "four" in read["diff"] and "added.py" in read["diff"]
        assert read["untracked"] == ["notes.md"]


def test_the_ref_origin_head_names_comes_before_a_local_main():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp))
        trunk = _git(repo, "rev-parse", "HEAD").strip()
        _git(repo, "update-ref", "refs/remotes/origin/trunk", trunk)
        _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        (repo / "later.txt").write_text("x\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "main moves on")
        _git(repo, "checkout", "-q", "-b", "feature")
        (repo / "f.txt").write_text("f\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "work")
        read = gitdiff.read_branch_local(repo, 20)
        assert (read["base"], read["base_ref"], read["base_branch"]) == (trunk, "origin/trunk", "trunk")
        assert "later.txt" in read["diff"]


def test_a_local_main_comes_before_a_local_master():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp))
        main = _git(repo, "rev-parse", "HEAD").strip()
        _git(repo, "branch", "master")
        (repo / "later.txt").write_text("x\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "main moves on")
        _git(repo, "checkout", "-q", "-b", "feature")
        read = gitdiff.read_branch_local(repo, 20)
        assert (read["base"], read["base_ref"]) == (_git(repo, "rev-parse", "main").strip(), "main")
        assert read["base"] != main


def test_a_local_master_is_the_default_when_there_is_no_origin_head_or_main():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp), "master")
        start = _feature(repo)
        read = gitdiff.read_branch_local(repo, 20)
        assert (read["base"], read["base_ref"], read["base_branch"]) == (start, "master", "master")


def test_an_origin_head_naming_a_missing_ref_falls_back_to_a_local_main():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp))
        start = _feature(repo)
        _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/gone")
        read = gitdiff.read_branch_local(repo, 20)
        assert (read["base"], read["base_ref"]) == (start, "main")


def test_a_checkout_on_its_default_branch_has_no_branch_of_its_own():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp))
        _dirty(repo)
        read = gitdiff.read_branch_local(repo, 20)
        assert read == {
            "diff": "", "untracked": [], "failed": False,
            "base": "", "base_ref": "main", "base_branch": "main", "base_reason": "default-branch",
        }


def test_a_checkout_on_the_branch_origin_head_names_is_on_its_default_branch():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp), "trunk")
        _git(repo, "update-ref", "refs/remotes/origin/trunk", "HEAD")
        _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        read = gitdiff.read_branch_local(repo, 20)
        assert (read["base_reason"], read["base_branch"], read["base_ref"]) == ("default-branch", "trunk", "origin/trunk")


def test_a_checkout_with_no_default_branch_has_no_findable_start():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp), "develop")
        _dirty(repo)
        read = gitdiff.read_branch_local(repo, 20)
        assert read == {
            "diff": "", "untracked": [], "failed": False,
            "base": "", "base_ref": "", "base_branch": "", "base_reason": "not-found",
        }


def test_a_branch_sharing_no_history_with_the_default_has_no_findable_start():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp))
        _git(repo, "checkout", "-q", "--orphan", "island")
        (repo / "other.txt").write_text("o\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "island")
        read = gitdiff.read_branch_local(repo, 20)
        assert (read["failed"], read["base"], read["base_reason"], read["base_branch"]) == (False, "", "not-found", "main")


def test_a_detached_head_still_finds_where_it_started():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp))
        start = _feature(repo)
        _git(repo, "checkout", "-q", "--detach")
        assert gitdiff.read_branch_local(repo, 20)["base"] == start


def test_a_branch_with_no_change_since_it_started_reads_an_empty_diff_with_its_base():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp))
        _git(repo, "checkout", "-q", "-b", "feature")
        read = gitdiff.read_branch_local(repo, 20)
        assert read["diff"] == "" and read["failed"] is False
        assert read["base"] == _git(repo, "rev-parse", "HEAD").strip()
        assert read["base_reason"] == ""


def test_a_branch_read_that_git_cannot_do_is_a_failed_read_not_a_missing_start():
    with tempfile.TemporaryDirectory() as tmp:
        assert gitdiff.read_branch_local(Path(tmp), 20)["failed"] is True
        assert gitdiff.read_branch_local(Path("/nonexistent/acme"), 20)["failed"] is True
        repo = Path(tmp) / "empty"
        repo.mkdir()
        _git(repo, "init", "-q")
        assert gitdiff.read_branch_local(repo, 20)["failed"] is True


def test_a_branch_read_that_times_out_is_a_failed_read(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp))
        _feature(repo)
        _slow_git(monkeypatch)
        assert gitdiff.read_branch_local(repo, 0.3)["failed"] is True


def _snapshot(repo: Path) -> tuple[bytes, str]:
    return (repo / ".git" / "index").read_bytes(), _git(repo, "for-each-ref")


def test_reading_either_view_leaves_the_index_and_the_refs_of_the_checkout_unchanged():
    import os

    with tempfile.TemporaryDirectory() as tmp:
        repo = _history(Path(tmp))
        _feature(repo)
        _dirty(repo)
        for entry in (repo / "src").iterdir():
            os.utime(entry, (1_000_000_000, 1_000_000_000))
        before = _snapshot(repo)
        gitdiff.read_local(repo, 20)
        gitdiff.read_branch_local(repo, 20)
        assert _snapshot(repo) == before
