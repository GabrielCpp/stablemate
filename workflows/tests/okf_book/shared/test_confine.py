from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

from workhorse_workflows.okf_book.shared.confine import GitFailed, restore, snapshot


def _repo(root: Path) -> Path:
    for args in (("init", "-q"), ("config", "user.email", "t@example.com"), ("config", "user.name", "t")):
        _ = subprocess.run(["git", *args], cwd=root, check=True)
    page = root / "page.md"
    _ = page.write_text("committed\n", encoding="utf-8")
    for args in (("add", "page.md"), ("commit", "-qm", "page")):
        _ = subprocess.run(["git", *args], cwd=root, check=True)
    return page


def test_a_put_back_waits_for_another_git_process_to_release_the_index(tmp_path: Path) -> None:
    page = _repo(tmp_path)
    before = snapshot(tmp_path)
    _ = page.write_text("the turn's edit\n", encoding="utf-8")
    lock = tmp_path / ".git" / "index.lock"
    lock.touch()
    release = threading.Timer(0.3, lock.unlink)
    release.start()

    left = restore(tmp_path, ["page.md"], before)
    release.join()

    assert (left, page.read_text(encoding="utf-8")) == ((), "committed\n")


def test_a_git_failure_says_what_git_said(tmp_path: Path) -> None:
    with pytest.raises(GitFailed, match="not a git repository"):
        _ = snapshot(tmp_path)
