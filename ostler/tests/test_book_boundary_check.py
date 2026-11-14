"""The cross-book check of a service boundary: a reference that broke, a book that holds a record its neighbour owns, and a reference still open."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterator

import pytest

from book_todo import FIXTURE, services_from


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    copy = tmp_path / "book_todo"
    shutil.copytree(FIXTURE, copy, ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
    monkeypatch.chdir(copy)
    with services_from(copy):
        yield copy


def test_a_needed_record_of_an_owner_with_no_book_fails_where_it_is_taken():
    from ostler.book import BookError, Foreign, Needs

    open_reference = Foreign("Ticket", owner="services.ticket", reads=("id", "status"))
    assert open_reference.record.__name__ == "Ticket"
    with pytest.raises(BookError, match="services.ticket has no book to arrange Ticket"):
        Needs(open_reference, "open")
