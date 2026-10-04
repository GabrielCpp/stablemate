"""A book commit renders the repo's agent files first, so a skill the library changed since the last render does not refuse it."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from okf_book.main.tally import (
    NOTE,
    PAGE,
    PASSED,
    REFUSAL,
    TALLY,
    App,
    DriveBook,
    answering_operator,
    stopping_operator,
    page_problems_until_noted,
    refuse_commits_until_answered,
    stub_the_run_to,
)
from okf_book.support import FIX_COMMIT_NODE, ScriptedRunner, always, git
from workhorse.pyflow import park as pyflow_park

from workhorse_workflows.okf_book.main import flow
from workhorse_workflows.okf_book.main.nodes.report import BookReport
from workhorse_workflows.okf_book.shared import book_flow
from workhorse_workflows.okf_book.workflow import OkfBook


def _writer(repo: Path) -> ScriptedRunner:
    def _reply(_args: dict[str, object]) -> dict[str, object]:
        page = repo / PAGE
        _ = page.write_text(page.read_text(encoding="utf-8") + NOTE, encoding="utf-8")
        return {"value": "wrote tally.md"}

    return ScriptedRunner({"write-book": _reply})


@pytest.fixture
def passing(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(flow, "page_problems", page_problems_until_noted)


@pytest.mark.usefixtures("passing")
def test_the_agent_files_are_rendered_before_the_book_commit_so_their_drift_is_not_refused(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    drift = repo / ".drifted"
    _ = drift.write_text("stale skill\n", encoding="utf-8")
    hook = repo / git(repo, "rev-parse", "--git-path", "hooks/pre-commit").strip()
    hook.parent.mkdir(parents=True, exist_ok=True)
    _ = hook.write_text(
        f"#!{sys.executable}\nimport pathlib, sys\nsys.exit(1 if pathlib.Path({str(drift)!r}).exists() else 0)\n", encoding="utf-8"
    )
    hook.chmod(0o755)
    asked: list[str] = []
    monkeypatch.setattr(pyflow_park, "wait_for_answer", stopping_operator(asked))

    def _render(root: Path) -> str:
        (root / ".drifted").unlink(missing_ok=True)
        return ""

    monkeypatch.setattr(book_flow, "render_agent_files_returning_failure", _render)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _writer(repo))

    assert isinstance(result, BookReport)
    assert asked == []
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]


@pytest.mark.usefixtures("passing")
def test_a_render_that_failed_waits_for_the_operator_and_the_book_is_committed_after_their_answer(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    asked: list[str] = []
    failures = ["farrier could not run: no farrier"]
    monkeypatch.setattr(pyflow_park, "wait_for_answer", answering_operator(asked))

    def _render(_root: Path) -> str:
        return failures.pop() if failures else ""

    monkeypatch.setattr(book_flow, "render_agent_files_returning_failure", _render)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _writer(repo))

    assert isinstance(result, BookReport)
    assert len(asked) == 1
    assert "farrier could not run: no farrier" in asked[0]
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]


@pytest.mark.usefixtures("passing")
def test_an_answer_to_a_refused_commit_commits_again_without_rendering_again(
    app: App, drive_book: DriveBook, rendered_repos: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    asked: list[str] = []
    monkeypatch.setattr(pyflow_park, "wait_for_answer", refuse_commits_until_answered(repo, asked))

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _writer(repo))

    assert isinstance(result, BookReport)
    assert len(asked) == 1
    assert rendered_repos == [repo.resolve()]
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]


def _hook(repo: Path) -> Path:
    return repo / git(repo, "rev-parse", "--git-path", "hooks/pre-commit").strip()


@pytest.mark.usefixtures("passing")
def test_a_refused_commit_goes_to_a_turn_that_fixes_it_and_no_operator_is_asked(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    asked: list[str] = []
    _ = refuse_commits_until_answered(repo, asked)
    monkeypatch.setattr(pyflow_park, "wait_for_answer", stopping_operator(asked))
    runner = _writer(repo)

    def _fix(_args: dict[str, object]) -> dict[str, object]:
        _hook(repo).unlink()
        return {"fixed": "removed what refused it"}

    runner.replies[FIX_COMMIT_NODE] = _fix

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    assert asked == []
    [args] = runner.args_of(FIX_COMMIT_NODE)
    assert REFUSAL in str(args["refusal"])
    assert args["paths"] == [PAGE]
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]


@pytest.mark.usefixtures("passing")
def test_a_commit_the_turn_could_not_fix_reaches_the_operator_with_what_the_turn_said(
    app: App, drive_book: DriveBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = app("tally-cli")
    asked: list[str] = []
    monkeypatch.setattr(pyflow_park, "wait_for_answer", refuse_commits_until_answered(repo, asked))
    runner = _writer(repo)
    runner.replies[FIX_COMMIT_NODE] = always({"blocked": "the hook refuses every commit"})

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert isinstance(result, BookReport)
    [gate] = asked
    assert REFUSAL in gate
    assert "the hook refuses every commit" in gate
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]
