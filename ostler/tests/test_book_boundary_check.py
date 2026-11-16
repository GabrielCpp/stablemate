"""The cross-book check of a service boundary: a reference that broke, a book that holds a record its neighbour owns, and a reference still open."""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ostler.book.check import Finding, boundary_faults, check



def test_a_needed_record_of_an_owner_with_no_book_fails_where_it_is_taken():
    from ostler.book import BookError, Foreign, Needs

    open_reference = Foreign("Ticket", owner="services.ticket", reads=("id", "status"))
    assert open_reference.record.__name__ == "Ticket"
    with pytest.raises(BookError, match="services.ticket has no book to arrange Ticket"):
        Needs(open_reference, "open")


def _edit(root: Path, book: str, relative: str, old: str, new: str) -> None:
    path = root / "services" / book / relative
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def _boundary(module: str) -> list[Finding]:
    return boundary_faults(importlib.import_module(f"{module}.service").service, module)


def test_the_fixtures_three_books_check_clean(root: Path):
    for module in ("services.api", "services.web", "services.digest"):
        assert check(importlib.import_module(f"{module}.service").service, module) == []


def test_a_field_the_owners_answers_no_longer_have_is_named_on_the_neighbours_check_with_the_owners_calls(root: Path):
    _edit(root, "api", "endpoints/shapes.py", "    status=Field(Enum(STATUSES)", "    state=Field(Enum(STATUSES)")
    [found] = _boundary("services.digest")
    assert found.blocks
    assert "services.digest" in found.problem and "services.api" in found.problem
    assert "status" in found.problem and "TodoRecord" in found.name + found.problem
    assert "FindTodos" in found.problem and "ReadTodo" in found.problem


def test_the_same_removal_is_named_on_the_owners_check_with_the_neighbours_name(root: Path):
    _edit(root, "api", "endpoints/shapes.py", "    status=Field(Enum(STATUSES)", "    state=Field(Enum(STATUSES)")
    [found] = _boundary("services.api")
    assert found.blocks
    assert "services.digest" in found.problem and "status" in found.problem


def test_a_state_the_owners_matrices_no_longer_have_is_named_on_both_checks(root: Path):
    _edit(root, "api", "model/lifecycle.py", 'Scene("overdue"', 'Scene("late"')
    digest = {"journey AnOverdueTodoIsInTheDigest", "journey AnOverdueTodoIsFinishedFromTheDigest"}
    web = {"journey TheDayPasses", "scene chore:overdue"}
    for module, names in (("services.digest", digest), ("services.api", digest | web)):
        every = _boundary(module)
        assert {found.name for found in every} == names
        for found in every:
            assert found.blocks
            assert "overdue" in found.problem and "services.api" in found.problem
            assert ("services.web" if found.name in web else "services.digest") in found.problem
            assert "late" in found.problem and "unscheduled" in found.problem


def test_a_call_that_is_no_endpoint_of_its_book_is_named(root: Path):
    _edit(root, "api", "endpoints/__init__.py", "RemoveTodo, FindTodos, ReadClock", "RemoveTodo, ReadClock")
    [found] = _boundary("services.digest")
    assert found.blocks
    assert found.name == "endpoint ReadDigest"
    assert "FindTodos" in found.problem and "services.api" in found.problem


def test_a_reference_by_a_word_to_an_owner_with_no_book_is_noted_and_does_not_block(root: Path):
    with (root / "services" / "digest" / "foreign.py").open("a") as handle:
        handle.write('\nTICKET = Foreign("Ticket", owner="services.ticket", reads=("id",))\n')
    [found] = _boundary("services.digest")
    assert found.told and not found.blocks
    assert "Ticket" in found.name + found.problem and "services.ticket" in found.problem


def test_a_reference_by_a_word_to_an_owner_that_has_a_book_blocks_and_says_to_name_the_class(root: Path):
    with (root / "services" / "digest" / "foreign.py").open("a") as handle:
        handle.write('\nTODO_BY_NAME = Foreign("TodoRecord", owner="services.api", reads=("id",))\n')
    [found] = _boundary("services.digest")
    assert found.blocks
    assert "name the record class" in found.problem and "services.api" in found.problem


OTHER_SERVICE = '''
from dataclasses import dataclass

from ostler.book import Answer, Collection, Endpoint, Environment, Service, Stack, State, Unique


@dataclass(frozen=True)
class TodoRecord:
    id: str


class Ping(Endpoint):
    path = "/ping"
    answers = (Answer(200, None, "pong"),)
    does = "Answers pong."


class Other(State):
    todos = Collection(TodoRecord, Unique("id"))


LOCAL = Environment("local", {"other": "http://127.0.0.1:1"})

service = Service(name="other", environments={"local": LOCAL}, default_environment="local", new_model=Other, surface=lambda environment: None, journeys=(),
                  stack=lambda directory: Stack((), directory), endpoints=(Ping,))
'''


def _other(root: Path) -> None:
    book = root / "services" / "other"
    book.mkdir()
    (book / "__init__.py").write_text("")
    (book / "service.py").write_text(OTHER_SERVICE)


def test_a_book_that_refers_to_a_neighbour_and_also_holds_a_record_of_the_same_name_is_named_and_blocks(root: Path):
    _edit(root, "digest", "model.py", "from ostler.book import State\n",
          "from dataclasses import dataclass\n\nfrom ostler.book import Collection, State, Unique\n\n\n"
          "@dataclass(frozen=True)\nclass TodoRecord:\n    id: str\n")
    _edit(root, "digest", "model.py", "class Digesting(State):\n",
          'class Digesting(State):\n    todos = Collection(TodoRecord, Unique("id"))\n\n')
    [found] = _boundary("services.digest")
    assert found.blocks
    assert "services.digest" in found.problem and "services.api" in found.problem and "TodoRecord" in found.problem
    assert "Foreign" in found.problem and "Needs" in found.problem


def test_a_book_that_refers_to_one_record_and_holds_another_a_neighbour_also_holds_is_noted_and_does_not_block(root: Path):
    _edit(root, "digest", "model.py", "from ostler.book import State\n",
          "from dataclasses import dataclass\n\nfrom ostler.book import Collection, State, Unique\n\n\n"
          "@dataclass(frozen=True)\nclass chore:\n    id: str\n")
    _edit(root, "digest", "model.py", "class Digesting(State):\n",
          'class Digesting(State):\n    chores = Collection(chore, Unique("id"))\n\n')
    [found] = _boundary("services.digest")
    assert found.told and not found.blocks
    assert found.name == "record chore" and "if it is one record" in found.problem


def test_a_note_is_printed_apart_and_the_check_still_passes(root: Path, capsys: pytest.CaptureFixture[str]):
    from ostler.book.check import report

    _other(root)
    found = _boundary("services.other")
    report(found)
    printed = capsys.readouterr().out
    assert printed.startswith("NOTE   record TodoRecord: ")
    assert printed.rstrip().endswith("check: 0 findings, 1 note")
    done = subprocess.run([sys.executable, "-m", "ostler.book", "check", "services.api"], cwd=root, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "NOTE   record TodoRecord: services.api and services.other both hold TodoRecord" in done.stdout


def test_a_book_that_states_no_reference_and_holds_a_record_another_book_holds_is_noted_and_does_not_block(root: Path):
    _other(root)
    [found] = _boundary("services.other")
    assert found.told and not found.blocks
    assert "services.other" in found.problem and "services.api" in found.problem and "TodoRecord" in found.problem


def test_a_journey_that_sends_another_books_call_is_named(root: Path):
    _edit(root, "digest", "journeys/the_todo_api_turns_a_caller_away.py", "from ..endpoints import FinishFromDigest, ReadDigest, ReadDigestEntry\n",
          "from ...api.endpoints import FindTodos\nfrom ..endpoints import FinishFromDigest, ReadDigest, ReadDigestEntry\n")
    _edit(root, "digest", "journeys/the_todo_api_turns_a_caller_away.py", "        yield OwnerRefused(ReadDigest(by=None))",
          "        yield FindTodos()\n        yield OwnerRefused(ReadDigest(by=None))")
    [found] = _boundary("services.digest")
    assert found.blocks
    assert found.name == "journey TheTodoApiTurnsACallerAway"
    assert "FindTodos" in found.problem and "services.api" in found.problem and "Foreign" in found.problem


def test_a_book_alone_under_its_root_gets_no_boundary_finding(root: Path):
    for book in ("api", "web", "digest", "kit"):
        shutil.rmtree(root / "services" / book)
    _other(root)
    assert _boundary("services.other") == []
