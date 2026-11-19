"""`ostler book files`: what a book needs to load, found by reading its imports."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler.book import check as book_check
from ostler.book import cli, index
from ostler.book.files import files, outside


def _write(root: Path, name: str, text: str = "") -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(text)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    _write(tmp_path, "services/ticket/service.py", "from .endpoints import x\nfrom ..shared.accounts import Account\n")
    _write(tmp_path, "services/ticket/endpoints.py", "import services.shared.answers\nimport os\nimport ostler.book\nimport yaml\n")
    _write(tmp_path, "services/ticket/index.tsv", "x\n")
    _write(tmp_path, "services/ticket/decisions/one.md", "# one\n")
    _write(tmp_path, "services/ticket/__pycache__/service.cpython-312.pyc", "x")
    _write(tmp_path, "services/shared/accounts.py", "from .places import Stack\n")
    _write(tmp_path, "services/shared/places.py", "")
    _write(tmp_path, "services/shared/answers.py", "")
    _write(tmp_path, "services/shared/unused.py", "")
    _write(tmp_path, "services/user/service.py", "")
    _write(tmp_path, "services/user/accounts.py", "")
    return tmp_path


def test_outside_follows_a_relative_and_an_absolute_import_and_what_those_import(root):
    assert outside(root, "services.ticket") == [
        "services/shared/accounts.py",
        "services/shared/answers.py",
        "services/shared/places.py",
    ]


def test_outside_lists_the_init_files_on_the_way_where_they_exist(root):
    _write(root, "services/__init__.py")
    _write(root, "services/shared/__init__.py")
    assert outside(root, "services.ticket") == [
        "services/__init__.py",
        "services/shared/__init__.py",
        "services/shared/accounts.py",
        "services/shared/answers.py",
        "services/shared/places.py",
    ]


def test_outside_leaves_another_services_book_to_its_own_commit(root):
    _write(root, "services/ticket/records.py", "from ..user.accounts import Seat\nfrom ..user import service\n")
    assert not [path for path in outside(root, "services.ticket") if path.startswith("services/user")]


def test_outside_is_empty_for_a_book_that_imports_nothing_under_the_root(tmp_path):
    _write(tmp_path, "services/solo/service.py", "import os\nimport ostler\n")
    assert outside(tmp_path, "services.solo") == []


def test_files_adds_the_books_own_folder_without_compiled_files(root):
    listed = files(root, "services.ticket")
    assert "services/ticket/service.py" in listed
    assert "services/ticket/index.tsv" in listed
    assert "services/ticket/decisions/one.md" in listed
    assert "services/shared/accounts.py" in listed
    assert not [path for path in listed if "__pycache__" in path]


def test_the_verb_prints_one_path_per_line_and_outside_keeps_only_those_beyond_the_folder(root, monkeypatch, capsys):
    monkeypatch.setattr(cli, "book_root", lambda cwd: str(root))
    assert cli.main(["files", "services.ticket", "--outside"]) == 0
    assert capsys.readouterr().out.splitlines() == outside(root, "services.ticket")
    assert cli.main(["files", "services.ticket"]) == 0
    assert capsys.readouterr().out.splitlines() == files(root, "services.ticket")


def test_the_verb_exits_2_for_a_service_with_no_folder(root, monkeypatch, capsys):
    monkeypatch.setattr(cli, "book_root", lambda cwd: str(root))
    assert cli.main(["files", "services.nothing"]) == 2
    assert "no folder" in capsys.readouterr().err


def test_check_notes_the_outside_files_without_failing(root, monkeypatch):
    monkeypatch.setattr(index, "book_root", lambda cwd: str(root))
    [note] = book_check.outside_notes("services.ticket")
    assert note.told and not note.blocks
    assert str(note) == (
        "files: the book imports 3 file(s) outside its folder: services/shared/accounts.py, "
        "services/shared/answers.py, services/shared/places.py; a commit of the book takes them with it"
    )


def test_check_notes_nothing_for_a_book_that_imports_nothing_outside(tmp_path, monkeypatch):
    _write(tmp_path, "services/solo/service.py", "import os\n")
    monkeypatch.setattr(index, "book_root", lambda cwd: str(tmp_path))
    assert book_check.outside_notes("services.solo") == []
