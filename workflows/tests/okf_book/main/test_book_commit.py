"""A book commit renders the repo's agent files first, so a skill the library changed since the last render does not refuse it."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest
from okf_book.main.tally import NOTE, PAGE, PASSED, TALLY, App, DriveBook, answering_operator, book_problems_until_noted, stub_the_run_to
from okf_book.support import ScriptedRunner, git
from workhorse.pyflow import driver as pyflow_driver

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
    monkeypatch.setattr(flow, "book_problems", book_problems_until_noted)


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
    monkeypatch.setattr(pyflow_driver, "wait_for_answer", answering_operator(asked))

    def _render(root: Path, _logger: logging.Logger) -> None:
        (root / ".drifted").unlink(missing_ok=True)

    monkeypatch.setattr(book_flow, "render_agent_files", _render)

    result = drive_book(OkfBook(repo_dir=str(repo), surfaces=(TALLY,)), _writer(repo))

    assert isinstance(result, BookReport)
    assert asked == []
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == [PAGE]
