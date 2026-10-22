from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

from workhorse_workflows.okf_book.shared.confine import GitFailed, kept_changes, put_back_outside, restore, snapshot


def _committed_page(root: Path) -> Path:
    for args in (("init", "-q"), ("config", "user.email", "t@example.com"), ("config", "user.name", "t")):
        _ = subprocess.run(["git", *args], cwd=root, check=True)
    page = root / "page.md"
    _ = page.write_text("committed\n", encoding="utf-8")
    for args in (("add", "page.md"), ("commit", "-qm", "page")):
        _ = subprocess.run(["git", *args], cwd=root, check=True)
    return page


def test_a_put_back_waits_for_another_git_process_to_release_the_index(tmp_path: Path) -> None:
    page = _committed_page(tmp_path)
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


OTHER = "docs/services/other/start.md"
LINK = "See [totals](../ledger/old.md#totals).\n"


def _repo_with_a_link_into_the_book(root: Path) -> Path:
    for args in (("init", "-q"), ("config", "user.email", "t@example.com"), ("config", "user.name", "t")):
        _ = subprocess.run(["git", *args], cwd=root, check=True)
    page = root / OTHER
    page.parent.mkdir(parents=True)
    _ = page.write_text(LINK, encoding="utf-8")
    for args in (("add", OTHER), ("commit", "-qm", "page")):
        _ = subprocess.run(["git", *args], cwd=root, check=True)
    return page


def test_a_page_of_another_book_whose_links_the_turn_pointed_into_the_book_is_kept(tmp_path: Path) -> None:
    page = _repo_with_a_link_into_the_book(tmp_path)
    before = snapshot(tmp_path)
    retargeted = LINK.replace("old.md", "flows/new.md")
    _ = page.write_text(retargeted, encoding="utf-8")

    stray = put_back_outside(tmp_path, "ledger", before, tmp_path / ".run")

    assert (stray, page.read_text(encoding="utf-8")) == ((), retargeted)
    assert kept_changes(tmp_path, "ledger", before, tmp_path / ".run") == (OTHER,)


def test_a_page_of_another_book_the_turn_changed_past_its_links_is_put_back(tmp_path: Path) -> None:
    page = _repo_with_a_link_into_the_book(tmp_path)
    before = snapshot(tmp_path)
    _ = page.write_text(LINK.replace("old.md", "new.md").replace("See", "Read"), encoding="utf-8")

    stray = put_back_outside(tmp_path, "ledger", before, tmp_path / ".run")

    assert (stray, page.read_text(encoding="utf-8")) == ((OTHER,), LINK)
