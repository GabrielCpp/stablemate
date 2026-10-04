"""A committed entries page that links nothing is written again once the book has an entry page, and one that links a page is left as it is."""
from __future__ import annotations

from pathlib import Path

from okf_book.main.tally import App
from okf_book.support import git
from workhorse.pyflow import Continue, Done

from workhorse_workflows.okf_book.main import root_book_flow

ENTRIES = "docs/features/tally/entries.md"
EMPTY = "---\ntype: entries\nslug: entries\ntitle: tally\n---\n\n# tally\n"


def _commit_entries(repo: Path, text: str) -> None:
    _ = (repo / ENTRIES).write_text(text, encoding="utf-8")
    _ = git(repo, "add", ENTRIES)
    _ = git(repo, "commit", "-q", "-m", "docs(tally): root the tally book")


def test_a_committed_entries_page_that_links_nothing_is_written_again_once_the_book_has_an_entry_page(app: App) -> None:
    repo = app("tally-cli")
    _commit_entries(repo, EMPTY)
    book = root_book_flow.RootBook(repo_dir=str(repo), service="tally")

    rooted = book.root_book(uncommitted_at_start=())

    assert isinstance(rooted, Continue)
    assert rooted.state == "render_agent_files"
    assert "](tally.md)" in (repo / ENTRIES).read_text(encoding="utf-8")


def test_a_committed_entries_page_that_links_a_page_roots_the_book_as_it_is(app: App) -> None:
    repo = app("tally-cli")
    written = EMPTY + "\n- [Other](other.md)\n"
    _commit_entries(repo, written)
    book = root_book_flow.RootBook(repo_dir=str(repo), service="tally")

    assert isinstance(book.root_book(uncommitted_at_start=()), Done)
    assert (repo / ENTRIES).read_text(encoding="utf-8") == written
