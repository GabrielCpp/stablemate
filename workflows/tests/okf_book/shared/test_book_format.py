"""A book is judged against the commit of the writer's instructions it was last written to, read from real git history."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from okf_book.support import commit_at, git, skill_history

from workhorse_workflows.okf_book.shared import book_format
from workhorse_workflows.okf_book.shared.book_format import SKILL_DIR, book_format_delta, mark_book_format

LOGGER = logging.getLogger("test")


def book_repo(root: Path, monkeypatch: pytest.MonkeyPatch, when: str = "2026-11-02T12:00:00+00:00") -> Path:
    """A repo whose `services/ledger/` was committed between the first and the second skill commit."""
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "services/ledger").mkdir(parents=True)
    (root / "services/ledger/service.py").write_text("SERVICE = 1\n", encoding="utf-8")
    git(root, "add", "services")
    commit_at(root, "docs(ledger): write the ledger book", when, monkeypatch)
    return root


def test_a_book_with_no_mark_is_judged_against_the_last_instructions_commit_before_its_own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shas = skill_history(tmp_path / "history", monkeypatch)
    book = book_repo(tmp_path / "book", monkeypatch)

    delta = book_format_delta(LOGGER, book, "ledger", str(tmp_path / "history"))

    assert delta.unreadable == ""
    assert (delta.mark, delta.derived, delta.head) == (shas[0], True, shas[2])
    assert [commit.sha for commit in delta.commits] == shas[1:]
    assert [commit.subject for commit in delta.commits] == ["docs(base-library): teach two", "docs(base-library): teach three"]
    assert delta.behind
    assert "-one" in delta.diff and "+three" in delta.diff


def test_a_book_marked_at_the_head_is_not_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shas = skill_history(tmp_path / "history", monkeypatch)
    book = book_repo(tmp_path / "book", monkeypatch)
    mark_book_format(LOGGER, book, "ledger", shas[2])

    delta = book_format_delta(LOGGER, book, "ledger", str(tmp_path / "history"))

    assert (delta.mark, delta.derived, delta.head) == (shas[2], False, shas[2])
    assert delta.commits == []
    assert delta.diff == ""
    assert not delta.behind
    assert (book / "services/ledger/FORMAT").read_text(encoding="utf-8") == f"{shas[2]}\n"


def test_a_mark_in_the_middle_lists_only_the_commits_after_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shas = skill_history(tmp_path / "history", monkeypatch)
    book = book_repo(tmp_path / "book", monkeypatch)
    mark_book_format(LOGGER, book, "ledger", shas[1])

    delta = book_format_delta(LOGGER, book, "ledger", str(tmp_path / "history"))

    assert [commit.sha for commit in delta.commits] == [shas[2]]


def test_a_book_with_no_commit_is_never_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shas = skill_history(tmp_path / "history", monkeypatch)
    book = tmp_path / "book"
    (book / "services/ledger").mkdir(parents=True)

    delta = book_format_delta(LOGGER, book, "ledger", str(tmp_path / "history"))

    assert (delta.mark, delta.head) == (shas[2], shas[2])
    assert not delta.behind


def test_a_book_older_than_every_instructions_commit_lists_them_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shas = skill_history(tmp_path / "history", monkeypatch)
    book = book_repo(tmp_path / "book", monkeypatch, "2026-10-01T12:00:00+00:00")

    delta = book_format_delta(LOGGER, book, "ledger", str(tmp_path / "history"))

    assert delta.mark == ""
    assert [commit.sha for commit in delta.commits] == shas


def test_a_history_that_cannot_be_read_says_which_command_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book = book_repo(tmp_path / "book", monkeypatch)
    (tmp_path / "nowhere").mkdir()

    delta = book_format_delta(LOGGER, book, "ledger", str(tmp_path / "nowhere"))

    assert "git -C" in delta.unreadable and "rev-list" in delta.unreadable and "exited" in delta.unreadable
    assert delta.commits == [] and delta.head == "" and not delta.behind


def test_no_checkout_above_the_package_is_unreadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(book_format, "history_repo", lambda: None)
    book = book_repo(tmp_path / "book", monkeypatch)

    delta = book_format_delta(LOGGER, book, "ledger", "")

    assert SKILL_DIR in delta.unreadable
    assert not delta.behind


def test_a_diff_past_the_limit_is_cut_and_names_the_command_that_shows_each_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shas = skill_history(tmp_path / "history", monkeypatch)
    history = tmp_path / "history"
    _ = (history / SKILL_DIR / "SKILL.md").write_text("long\n" * 20000, encoding="utf-8")
    git(history, "add", SKILL_DIR)
    commit_at(history, "docs(base-library): teach a lot", "2026-11-06T12:00:00+00:00", monkeypatch)
    book = book_repo(tmp_path / "book", monkeypatch)
    mark_book_format(LOGGER, book, "ledger", shas[2])

    delta = book_format_delta(LOGGER, book, "ledger", str(history))

    assert len(delta.diff) < 61000
    assert f"the diff is cut here: read each commit with `git -C {history} show <sha> -- {SKILL_DIR}`" in delta.diff


def test_the_checkout_the_package_runs_from_holds_the_instructions() -> None:
    found = book_format.history_repo()

    assert found is not None and (found / SKILL_DIR).is_dir()
