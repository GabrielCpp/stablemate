"""The tally app every okf-book flow test drives: its surface, its page, and the stubs that stand in for its run."""
from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from okf_book.support import ScriptedRunner, StoppedAtTheGate, git
from workhorse.pyflow import park as pyflow_park

from workhorse_workflows.okf_book.main import exercise_book_flow, flow
from workhorse_workflows.okf_book.main.nodes.report import read_report
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.shared.book_run import CompileOutcome, ExerciseResult, StackReadiness
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.workflow import OkfBook

App = Callable[[str], Path]
DriveBook = Callable[[OkfBook, ScriptedRunner], object]
TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
PAGE = "docs/features/tally/tally.md"
NOTE = "\nThe ledger keeps every expense in the order it was added.\n"
REFUSAL = "the hook refuses this commit"


PASSED = ExerciseResult(lines=("All 3 scenarios pass",), passed=True)
FAILED = ExerciseResult(lines=("scenario add: failed, 1 of 2 checks failed",))


def _no_gaps(_root: Path, _service: str, _spec: Path) -> CompileOutcome:
    return CompileOutcome(gaps=(), planned=True)


def _serving(_logger: logging.Logger, _root: Path, _service: str) -> StackReadiness:
    return StackReadiness(up=True, serving=True, notes="")


def stub_the_run_to(monkeypatch: pytest.MonkeyPatch, exercised: ExerciseResult) -> None:
    def _run(_root: Path, _spec: Path, _gaps: tuple[str, ...], _serving: bool) -> ExerciseResult:
        return exercised

    monkeypatch.setattr(exercise_book_flow, "compile_scenarios", _no_gaps)
    monkeypatch.setattr(exercise_book_flow, "bring_up", _serving)
    monkeypatch.setattr(exercise_book_flow, "run_plan", _run)


def stub_the_runs_to(monkeypatch: pytest.MonkeyPatch, *results: ExerciseResult) -> None:
    """Each run of the book ends on the next of *results*."""
    left = list(results)

    def _run(_root: Path, _spec: Path, _gaps: tuple[str, ...], _serving: bool) -> ExerciseResult:
        return left.pop(0)

    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(exercise_book_flow, "run_plan", _run)


def stopping_operator(asked: list[str]) -> Callable[..., None]:
    """An operator who reads the report at the gate and stops the run there."""

    def _operator(path: Path, **_kwargs: object) -> None:
        asked.append(path.read_text(encoding="utf-8"))
        raise StoppedAtTheGate(read_report(path.parent))

    return _operator


def answering_operator(asked: list[str]) -> Callable[..., None]:
    """An operator who reads the report at the gate and answers it."""

    def _operator(path: Path, **_kwargs: object) -> None:
        asked.append(path.read_text(encoding="utf-8"))
        _ = path.write_text("STATUS: ANSWERED\n\nRead it.\n", encoding="utf-8")

    return _operator


def no_problems(_root: Path, _service: str) -> tuple[PageProblem, ...]:
    return ()


def refuse_commits_until_answered(repo: Path, asked: list[str]) -> Callable[..., None]:
    """A hook that refuses every commit in *repo*, and an operator whose answer removes it."""
    hook = repo / git(repo, "rev-parse", "--git-path", "hooks/pre-commit").strip()
    hook.parent.mkdir(parents=True, exist_ok=True)
    _ = hook.write_text(f"#!{sys.executable}\nimport sys\nprint({REFUSAL!r}, file=sys.stderr)\nsys.exit(1)\n", encoding="utf-8")
    hook.chmod(0o755)

    def _operator(path: Path, **_kwargs: object) -> None:
        asked.append(path.read_text(encoding="utf-8"))
        hook.unlink(missing_ok=True)
        _ = path.write_text("STATUS: ANSWERED\n\nRemoved the hook.\n", encoding="utf-8")

    return _operator


OTHER_PAGE = "docs/features/tally/concepts/ledger-file.md"
SERVER_PAGE = "docs/features/tally/http/server.md"
ENDPOINT_PAGES = ("docs/features/tally/http/add-expense.md", "docs/features/tally/http/get-total.md")
INLINE_SERVER = (
    "---\ntype: server\ntitle: Tally API\n---\n# Tally API\n\n- entry-url: http://localhost:8000\n\n"
    "## Endpoints\n\n### get-total\n\n- method: GET\n- path: /total\n\n"
    "### add-expense\n\n- method: POST\n- path: /expenses\n"
)


def write_inline_server(repo: Path) -> None:
    """A server page in the tally book that holds its two endpoints inline."""
    page = repo / SERVER_PAGE
    page.parent.mkdir(parents=True, exist_ok=True)
    _ = page.write_text(INLINE_SERVER, encoding="utf-8")


def page_problems_until_noted(root: Path, _service: str) -> tuple[PageProblem, ...]:
    return () if NOTE.strip() in (root / PAGE).read_text(encoding="utf-8") else (PageProblem(PAGE, "tally.md needs a note"),)


def stub_a_book_sent_back_to_its_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Send an existing book that passes its run back to its owner, with the page check clean once tally.md is noted."""
    stub_the_run_to(monkeypatch, PASSED)
    monkeypatch.setattr(flow, "page_problems", page_problems_until_noted)
    monkeypatch.setattr(pyflow_park, "wait_for_answer", stopping_operator([]))


SMALL_LIMIT = 1500


def _rule(n: int) -> str:
    return f"### rule-{n}\n\n- rule: an expense obeys rule {n}\n\n" + "The ledger checks this rule on every expense it records. " * 4 + "\n\n"


LEDGER = "---\ntype: concept\ntitle: Ledger file\n---\n# Ledger file\n\n## Rules\n\n" + "".join(_rule(n) for n in range(1, 9))
