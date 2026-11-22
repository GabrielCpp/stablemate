"""The paths a commit of a service's book takes: its folder, the files it imports from outside it, and never a compiled file."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from _books import SHARED_FILES, import_shared
from workhorse.testing import make_git_repo

from workhorse_workflows.kit import book_files
from workhorse_workflows.kit.book_files import (
    BOOK_ENV,
    book_command,
    book_pathspecs,
    is_compiled,
    left_behind,
    left_behind_refusal,
    outside_paths,
    stageable,
)

LAYOUTS = ("monorepo", "workspace")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture(params=LAYOUTS)
def root(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """The book root of a monorepo, which is the code repo, or of a workspace, which is the artifacts repo beside it."""
    if request.param == "workspace":
        _ = make_git_repo(tmp_path / "api")
    folder = tmp_path / ("artifacts" if request.param == "workspace" else "acme")
    folder.mkdir()
    (folder / "agents.yml").write_text("book:\n  home: repo\n", encoding="utf-8")
    return make_git_repo(folder)


def test_the_book_command_runs_the_book_module_and_its_env_turns_bytecode_off() -> None:
    assert book_command("files", "services.x")[1:] == ["-m", "ostler.book", "files", "services.x"]
    assert BOOK_ENV == {"PYTHONDONTWRITEBYTECODE": "1"}


def test_a_compiled_file_and_a_bytecode_folder_are_compiled() -> None:
    assert [is_compiled(p) for p in ("a/__pycache__/x.py", "a/x.pyc", "a/x.pyo", "a/x.py", "a/pyc.md")] == [True, True, True, False, False]


def test_the_pathspecs_are_the_books_folder_then_what_it_imports(root: Path) -> None:
    _ = import_shared(root, "ticket")

    assert book_pathspecs(root, "services.ticket") == ("services/ticket", *SHARED_FILES)


def test_the_init_files_on_the_way_are_taken_where_they_exist(root: Path) -> None:
    _ = import_shared(root, "ticket")
    (root / "services/__init__.py").write_text("", encoding="utf-8")

    assert outside_paths(root, "services.ticket") == ("services/__init__.py", *SHARED_FILES)


def test_a_book_that_imports_nothing_outside_its_folder_has_only_its_folder(root: Path) -> None:
    (root / "services/solo").mkdir(parents=True)
    (root / "services/solo/service.py").write_text("import os\n", encoding="utf-8")

    assert book_pathspecs(root, "services.solo") == ("services/solo",)


def test_a_namespaced_book_stages_its_repository_folder(root: Path) -> None:
    assert book_pathspecs(root, "services.acme.ticket")[0] == "services/acme/ticket"


def test_a_service_with_no_folder_has_only_its_folder_in_the_list(root: Path) -> None:
    assert book_pathspecs(root, "services.absent") == ("services/absent",)


def test_what_a_commit_may_stage_holds_the_folder_and_the_shared_files_and_no_compiled_file(root: Path) -> None:
    _ = import_shared(root, "ticket")

    staged = stageable(root, book_pathspecs(root, "services.ticket"))

    assert staged == ["services/shared/accounts.py", "services/shared/answers.py", "services/ticket/service.py"]


def test_a_deletion_already_staged_is_still_staged(root: Path) -> None:
    _ = import_shared(root, "ticket")
    _git(root, "add", "services/shared/accounts.py")
    _git(root, "commit", "-qm", "add")
    _git(root, "rm", "-q", "services/shared/accounts.py")

    assert "services/shared/accounts.py" in stageable(root, ["services/shared"])


def test_what_a_commit_left_behind_names_untracked_and_modified_files_but_not_compiled_ones(root: Path) -> None:
    _ = import_shared(root, "ticket")
    specs = book_pathspecs(root, "services.ticket")
    assert left_behind(root, specs) == ["services/shared/accounts.py", "services/shared/answers.py", "services/ticket/service.py"]
    _git(root, "add", *stageable(root, specs))
    _git(root, "commit", "-qm", "book")
    assert left_behind(root, specs) == []
    (root / "services/shared/answers.py").write_text("ACCOUNTS = ANSWER = 2\n", encoding="utf-8")

    assert left_behind(root, specs) == ["services/shared/answers.py"]


def test_the_refusal_names_each_path_and_is_empty_when_none_is_left() -> None:
    assert left_behind_refusal([]) == ""
    refusal = left_behind_refusal(["services/shared/a.py", "services/shared/b.py"])
    assert "- `services/shared/a.py`\n- `services/shared/b.py`" in refusal


def test_a_verb_that_cannot_answer_lists_nothing_outside(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _broken(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="no folder")

    monkeypatch.setattr(book_files, "run_tool", _broken)

    assert outside_paths(root, "services.ticket") == ()
