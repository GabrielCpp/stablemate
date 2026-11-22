"""`ostler book` reads the book of a lone repository from the artifacts folder, and refuses a book left in the repository."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from book_fakes import git as _git
from book_todo import FIXTURE
from conftest import write
from ostler.book.check import source_faults
from ostler.book.sources import missing
from ostler.book.stack import Fresh
from test_book_workspace import _service
from test_milestones import findings, milestone_md

MOVE_GUIDE = "docs/guide/moving-a-book-to-the-artifacts-folder.md"


def _artifacts() -> Path:
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve()


def _lone_repository(tmp_path: Path, name: str = "acme") -> Path:
    folder = tmp_path / "code" / name
    folder.mkdir(parents=True)
    _git(folder, "init", "--quiet")
    (folder / "a.py").write_text("x = 1\n")
    _git(folder, "add", "a.py")
    _git(folder, "commit", "--quiet", "-m", "init")
    return folder.resolve()


def _book_in_artifacts() -> None:
    shutil.copytree(FIXTURE / "services", _artifacts() / "services", ignore=shutil.ignore_patterns("__pycache__"))


def _ostler(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    binary = Path(sys.executable).parent / "ostler"
    return subprocess.run([str(binary), *arguments], cwd=cwd, capture_output=True, text=True, check=False)


def test_search_from_a_lone_repository_reads_its_book_in_the_artifacts_dir(tmp_path):
    acme = _lone_repository(tmp_path)
    _book_in_artifacts()
    done = _ostler(["book", "search", "todo"], acme)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "services.api" in done.stdout


def test_a_book_command_in_a_repository_with_an_unmoved_book_exits_2_naming_both_ways_out(tmp_path):
    acme = _lone_repository(tmp_path)
    write(acme / "services/old/service.py", "from ostler.book import Service\n")
    done = _ostler(["book", "search", "hello"], acme)
    assert done.returncode == 2, done.stdout + done.stderr
    assert "home: repo" in done.stderr
    assert MOVE_GUIDE in done.stderr


def test_the_module_entry_point_refuses_an_unmoved_book_with_the_same_exit(tmp_path):
    acme = _lone_repository(tmp_path)
    write(acme / "services/old/service.py", "from ostler.book import Service\n")
    done = subprocess.run([sys.executable, "-m", "ostler.book", "search", "hello"], cwd=acme, capture_output=True, text=True, check=False)
    assert done.returncode == 2, done.stdout + done.stderr
    assert done.stderr.startswith("error: ")


def test_a_repo_pointer_to_the_lone_repository_resolves_from_it(tmp_path, monkeypatch):
    acme = _lone_repository(tmp_path)
    monkeypatch.chdir(acme)
    assert missing(_service("repo://acme/a.py::x"), None) == []
    assert [f.problem for f in source_faults(_service("repo://acme/gone.py::x"), None)] == ["source repo://acme/gone.py does not exist"]


def test_check_with_app_resolves_a_repo_pointer_to_the_app_repository(tmp_path, monkeypatch):
    acme = _lone_repository(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert missing(_service("repo://acme/a.py::x"), str(acme)) == []
    assert source_faults(_service("repo://acme/a.py::x"), str(acme)) == []


def test_fresh_relative_cwd_is_under_the_book_root_when_started_in_the_code_repository(tmp_path, monkeypatch):
    acme = _lone_repository(tmp_path)
    monkeypatch.chdir(acme)
    assert Fresh(("true",), cwd="ops").directory() == str(_artifacts() / "ops")


def test_milestone_books_are_read_under_the_book_home(repo):
    write(repo / "docs/milestones/sign-in/milestone.md", milestone_md())
    write(_artifacts() / "services/area/service.py", "")
    assert findings(repo, "milestone-journey-services") == []
