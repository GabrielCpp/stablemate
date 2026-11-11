"""Which stack copy a book reaches: the run's word over the lease, the lease over the book's own name."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ostler.book.environment import Environment
from ostler.qa.addresses import LEASE_ENV

from book_todo import run_book


def named(copy: str = "") -> Environment:
    return Environment("local", {"api": f"ostler:{copy}", "docs": "http://docs.test"})


@pytest.fixture(autouse=True)
def no_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LEASE_ENV, raising=False)


def test_the_copy_the_run_names_outranks_the_lease_and_the_book(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(LEASE_ENV, "lease")
    place = named("books-own")
    place.leased = "runs-own"
    assert place.copy() == "runs-own"


def test_the_lease_outranks_the_copy_the_book_names(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(LEASE_ENV, "lease")
    assert named("books-own").copy() == "lease"


def test_the_books_own_copy_serves_a_run_by_hand():
    assert named("books-own").copy() == "books-own"


def test_a_host_that_names_no_copy_reaches_the_shared_one():
    assert named().copy() == "shared"


def test_an_environment_of_plain_addresses_has_no_copy():
    assert Environment("remote", {"api": "http://api.test"}).copy() == ""


def test_an_address_is_asked_of_the_copy_the_run_named(monkeypatch: pytest.MonkeyPatch):
    asked: list[list[str]] = []

    def answer(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        asked.append(command)
        return subprocess.CompletedProcess(command, 0, "http://127.0.0.1:4000\n", "")

    monkeypatch.setattr(subprocess, "run", answer)
    place = named("books-own")
    place.leased = "runs-own"
    assert place.address("api") == "http://127.0.0.1:4000"
    assert asked == [["ostler", "env", "address", "api", "--copy", "runs-own"]]
    assert place.address("docs") == "http://docs.test"


def test_a_run_takes_the_copy_as_an_option(tmp_path: Path):
    done = run_book(["run", "services.api", "--no-stack", "--copy", "runs-own", "--out", str(tmp_path / "out"), "--print-exec"], 1)
    assert done.returncode == 0, done.stdout + done.stderr
