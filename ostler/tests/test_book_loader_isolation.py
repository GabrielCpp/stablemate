"""`ostler book` names the child books of a folder with no service.py, and a check reads only the books of its own product."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from book_todo import services_from
from ostler.book import cli
from ostler.book.check import Finding, boundary_faults

BOOK = '''
from dataclasses import dataclass

from ostler.book import Answer, Collection, Endpoint, Environment, Service, Stack, State, Unique


@dataclass(frozen=True)
class Claim:
    id: str


class Ping{suffix}(Endpoint):
    path = "/ping"
    answers = (Answer(200, None, "pong"),)
    does = "Answers pong."


class Holder(State):
    claims = Collection(Claim, Unique("id"))


LOCAL = Environment("local", {{"api": "http://127.0.0.1:1"}})

service = Service(name="api", environments={{"local": LOCAL}}, default_environment="local", new_model=Holder, surface=lambda environment: None,
                  journeys=(), stack=lambda directory: Stack((), directory), endpoints=(Ping{suffix},))
'''


def _book(root: Path, folder: str, text: str = "") -> None:
    path = root / "services" / folder
    for package in (root / "services", *[root / "services" / "/".join(folder.split("/")[:n]) for n in range(1, len(folder.split("/")) + 1)]):
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text("")
    (path / "service.py").write_text(text)


def _claims(root: Path, *folders: str) -> None:
    for number, folder in enumerate(folders):
        _book(root, folder, BOOK.format(suffix=number))


def _boundary(module: str) -> list[Finding]:
    return boundary_faults(importlib.import_module(f"{module}.service").service, module)


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "book_root", lambda start: str(tmp_path))
    with services_from(tmp_path):
        yield tmp_path


def test_a_folder_with_no_service_py_lists_its_child_books_and_no_internal_error(tree: Path):
    _book(tree, "acme/groom/http")
    _book(tree, "acme/groom/web")
    with pytest.raises(SystemExit) as stopped:
        cli.load("services.acme.groom")
    message = str(stopped.value)
    assert "services.acme.groom.http" in message and "services.acme.groom.web" in message
    assert "internal error" not in message


def test_a_folder_with_no_service_py_and_no_child_book_says_so(tree: Path):
    (tree / "services" / "acme" / "empty").mkdir(parents=True)
    with pytest.raises(SystemExit, match="no service.py exists under"):
        cli.load("services.acme.empty")


def test_a_book_whose_own_import_is_missing_still_names_the_missing_module(tree: Path):
    _book(tree, "acme/api", "import nonexistent_pkg_xyz\n")
    with pytest.raises(ModuleNotFoundError, match="nonexistent_pkg_xyz"):
        cli.load("services.acme.api")


def test_a_record_another_repositorys_book_holds_is_not_a_trespass(tree: Path):
    _claims(tree, "acme/api", "globex/api")
    assert _boundary("services.acme.api") == []


def test_a_record_a_sibling_book_of_the_same_repository_holds_is_still_noted(tree: Path):
    _claims(tree, "acme/http", "acme/web")
    [found] = _boundary("services.acme.http")
    assert found.told and not found.blocks
    assert "services.acme.http" in found.problem and "services.acme.web" in found.problem and "Claim" in found.problem
