"""An endpoint a turn leaves inline, or a page it grows past the size limit, is carved before the turn's commit."""
from __future__ import annotations

from pathlib import Path

import pytest
from ostler import fragment_carve
from okf_book.main.tally import (
    App,
    DriveBook,
    ENDPOINT_PAGES,
    LEDGER,
    NOTE,
    OTHER_PAGE,
    PAGE,
    PASSED,
    SMALL_LIMIT,
    SERVER_PAGE,
    TALLY,
    page_problems_until_noted,
    stub_a_book_sent_back_to_its_owner,
    stub_the_run_to,
    write_inline_server,
)
from okf_book.support import ScriptedRunner, git

from workhorse_workflows.okf_book.main import flow
from workhorse_workflows.okf_book.shared import book_shape
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
    monkeypatch.setattr(flow, "page_problems", page_problems_until_noted)
    repo = app("tally-cli")

    _ = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _noting(repo, "write-book", inline=True))

    assert git(repo, "status", "--porcelain").strip() == ""
    assert _committed_in_head(repo) == sorted((*ENDPOINT_PAGES, PAGE, SERVER_PAGE))
    assert "### " not in (repo / SERVER_PAGE).read_text(encoding="utf-8")


def test_an_endpoint_a_server_page_holds_inline_gets_a_page_of_its_own_after_the_owner_turn_on_an_existing_book(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_a_book_sent_back_to_its_owner(monkeypatch)
    repo = app("tally-cli")
    write_inline_server(repo)
    _ = git(repo, "add", SERVER_PAGE)
    _ = git(repo, "commit", "-q", "-m", "docs(tally): describe the tally api")

    _ = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _noting(repo, "write-book", inline=False))

    assert git(repo, "status", "--porcelain").strip() == ""
    assert _committed_in_head(repo) == sorted((*ENDPOINT_PAGES, PAGE, SERVER_PAGE))
    assert "### " not in (repo / SERVER_PAGE).read_text(encoding="utf-8")


def _growing(repo: Path) -> ScriptedRunner:
    def _reply(_args: dict[str, object]) -> dict[str, object]:
        page = repo / PAGE
        _ = page.write_text(page.read_text(encoding="utf-8") + NOTE, encoding="utf-8")
        _ = (repo / OTHER_PAGE).write_text(LEDGER, encoding="utf-8")
        return {"value": "noted tally.md"}

    return ScriptedRunner({"write-book": _reply})


def test_a_page_the_writer_grew_past_the_limit_gets_fragments_in_the_book_commit(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(flow, "page_problems", page_problems_until_noted)
    monkeypatch.setattr(book_shape, "PAGE_SIZE_LIMIT", SMALL_LIMIT)
    monkeypatch.setattr(fragment_carve, "PAGE_SIZE_LIMIT", SMALL_LIMIT)
    repo = app("tally-cli")

    _ = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _growing(repo))

    assert git(repo, "status", "--porcelain").strip() == ""
    fragments = [p for p in _committed_in_head(repo) if Path(p).stem.startswith("ledger-file-rules")]
    assert fragments and OTHER_PAGE in _committed_in_head(repo)
    assert "### rule-" not in (repo / OTHER_PAGE).read_text(encoding="utf-8")
    assert all((repo / p).stat().st_size <= SMALL_LIMIT for p in (OTHER_PAGE, *fragments))
