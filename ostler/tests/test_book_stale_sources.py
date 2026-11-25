"""`ostler book stale` reads every pointer of the book against the commits since the stamp."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from book_fakes import app_repo, commit_files, git, sourced_book
from ostler.book import sources
from test_book_affected import FILES, edited

BOOK: dict[str, tuple[str, ...]] = {"RemoveItem": ("remove.go::Remove",), "PutItem": ("svc.go::Server.Get",)}


def with_an_action_named_like_its_endpoint(book: Any) -> Any:
    endpoint = next(e for e in book.endpoints if e.__name__ == "RemoveItem")
    action = type("RemoveItem", (endpoint.carries,), {"source": (), "__module__": endpoint.carries.__module__})
    renamed = type("RemoveItem", (endpoint,), {"carries": action, "__module__": endpoint.__module__})
    book.endpoints = tuple(renamed if e is endpoint else e for e in book.endpoints)
    return book


def test_an_action_without_code_keeps_the_pointers_of_the_endpoint_it_shares_a_name_with(tmp_path: Path):
    where, base = app_repo(tmp_path, FILES)
    commit_files(where, edited("remove.go", "return id", "return id + id"))
    book = with_an_action_named_like_its_endpoint(sourced_book(BOOK))
    report = sources.stale(book, str(where), str(tmp_path), since=base)
    assert "remove.go" not in report.unnamed
    assert "remove.go::Remove" in report.stale["RemoveItem"]


def test_a_file_deleted_since_the_stamp_is_not_unnamed_code(tmp_path: Path):
    where, base = app_repo(tmp_path, FILES)
    git(where, "rm", "--quiet", "other.go")
    git(where, "commit", "--quiet", "-m", "drop other")
    report = sources.stale(sourced_book(BOOK), str(where), str(tmp_path), since=base)
    assert "other.go" not in report.unnamed
