"""An endpoint a turn leaves inline on its server page is moved onto a page of its own before the turn's commit."""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_book.main.tally import (
    App,
    DriveBook,
    ENDPOINT_PAGES,
    NOTE,
    PAGE,
    PASSED,
    SERVER_PAGE,
    TALLY,
    book_problems_until_noted,
    stub_a_book_sent_to_repair,
    stub_the_run_to,
    write_inline_server,
)
from okf_book.support import ScriptedRunner, git

from workhorse_workflows.okf_book.main import flow
from workhorse_workflows.okf_book.workflow import OkfBook


def _noting(repo: Path, task: str, *, inline: bool) -> ScriptedRunner:
    def _reply(_args: dict[str, object]) -> dict[str, object]:
        page = repo / PAGE
        _ = page.write_text(page.read_text(encoding="utf-8") + NOTE, encoding="utf-8")
        if inline:
            write_inline_server(repo)
        return {"value": "noted tally.md"}

    return ScriptedRunner({task: _reply})


def _committed_in_head(repo: Path) -> list[str]:
    return sorted(git(repo, "show", "--name-only", "--format=", "HEAD").split())


def test_an_endpoint_the_writer_left_inline_gets_a_page_of_its_own_in_the_book_commit(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(flow, "book_problems", book_problems_until_noted)
    repo = app("tally-cli")

    _ = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _noting(repo, "write-book", inline=True))

    assert git(repo, "status", "--porcelain").strip() == ""
    assert _committed_in_head(repo) == sorted((*ENDPOINT_PAGES, PAGE, SERVER_PAGE))
    assert "### " not in (repo / SERVER_PAGE).read_text(encoding="utf-8")


def test_an_endpoint_a_server_page_holds_inline_gets_a_page_of_its_own_after_a_repair_turn(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_a_book_sent_to_repair(monkeypatch)
    repo = app("tally-cli")
    write_inline_server(repo)
    _ = git(repo, "add", SERVER_PAGE)
    _ = git(repo, "commit", "-q", "-m", "docs(tally): describe the tally api")

    _ = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _noting(repo, "repair-pages", inline=False))

    assert git(repo, "status", "--porcelain").strip() == ""
    assert _committed_in_head(repo) == sorted((*ENDPOINT_PAGES, PAGE, SERVER_PAGE))
    assert "### " not in (repo / SERVER_PAGE).read_text(encoding="utf-8")
