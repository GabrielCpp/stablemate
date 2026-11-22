"""A commit of a book takes the files it imports from outside its folder and no compiled file, in a repo and in a workspace."""
from __future__ import annotations

from pathlib import Path

import pytest
from _books import SHARED_FILES, import_shared
from okf_book.main.flows import build_flow, workspace_flow, written_book
from okf_book.support import FIX_COMMIT_NODE, git
from workhorse.pyflow import Await, Continue, Done

from workhorse_workflows.okf_book.shared import book_flow


def test_a_green_book_commit_takes_the_files_it_imports_and_no_compiled_file(tmp_path: Path) -> None:
    flow, _runner = build_flow(tmp_path)
    repo = written_book(flow)
    shared = import_shared(repo, "ledger")

    step = flow.commit(lap=1)

    assert isinstance(step, Done)
    assert sorted(git(repo, "show", "--name-only", "--format=", "HEAD").split()) == sorted([*shared, "services/ledger/service.py"])
    assert "pyc" not in git(repo, "ls-files")
    assert "scratch.txt" in git(repo, "status", "--porcelain")


def test_the_commit_checks_meet_the_files_the_book_imports_and_no_compiled_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = build_flow(tmp_path)
    repo = written_book(flow)
    shared = import_shared(repo, "ledger")
    met: list[tuple[str, ...]] = []

    def _declared(_root: Path, _message: str, pathspecs: tuple[str, ...]) -> str:
        met.append(pathspecs)
        return ""

    monkeypatch.setattr(book_flow, "declared_checks_failure", _declared)

    step = flow.checks(lap=1)

    assert isinstance(step, Continue) and step.state == "play"
    assert met == [("services/ledger/service.py", *shared)]


def test_a_commit_that_leaves_an_imported_file_behind_waits_on_the_operator_naming_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = build_flow(tmp_path, {FIX_COMMIT_NODE: lambda _args: {"fixed": "", "blocked": "cannot"}})
    repo = written_book(flow)
    _ = import_shared(repo, "ledger")
    commit = book_flow.commit_returning_refusal

    def _without_shared(root: Path, message: str, *pathspecs: str) -> str:
        return commit(root, message, *(spec for spec in pathspecs if "shared" not in spec))

    monkeypatch.setattr(book_flow, "commit_returning_refusal", _without_shared)

    waiting = flow.commit(lap=1)

    assert isinstance(waiting, Await) and waiting.path == flow.run_dir / book_flow.COMMIT_GATE
    assert all(f"- `{rel}`" in waiting.questions for rel in SHARED_FILES)
    assert "services/ledger/service.py" not in waiting.questions


def test_in_a_workspace_the_commit_of_the_book_takes_the_imported_files_into_the_artifacts_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, laid = workspace_flow(tmp_path, monkeypatch)
    book = laid.artifacts / "services/api/ledger"
    shared = laid.artifacts / "services/api/shared"
    book.mkdir(parents=True)
    shared.mkdir(parents=True)
    (book / "service.py").write_text("from ..shared.accounts import ACCOUNTS\nfrom ..shared.answers import ANSWER\n", encoding="utf-8")
    (shared / "accounts.py").write_text("ACCOUNTS = 1\n", encoding="utf-8")
    (shared / "answers.py").write_text("ANSWER = 1\n", encoding="utf-8")

    step = flow.commit(lap=1)

    assert isinstance(step, Done)
    assert sorted(git(laid.artifacts, "show", "--name-only", "--format=", "HEAD").split()) == [
        "services/api/ledger/service.py",
        "services/api/shared/accounts.py",
        "services/api/shared/answers.py",
    ]
    assert "pyc" not in git(laid.artifacts, "ls-files")
