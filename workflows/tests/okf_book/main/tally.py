"""The tally app every okf-book flow test drives: its surface, its page, and the stubs that stand in for its run."""
from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from okf_book.support import ScriptedRunner, git

from workhorse_workflows.okf_book.main import exercise_book_flow
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.shared.book_run import CompileOutcome, ExerciseResult, StackReadiness
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


def answer(asked: list[str]) -> Callable[..., None]:
    def _operator(path: Path, **_kwargs: object) -> None:
        asked.append(path.read_text(encoding="utf-8"))
        _ = path.write_text("STATUS: ANSWERED\n\nRead it.\n", encoding="utf-8")

    return _operator


def no_problems(_root: Path, _service: str) -> tuple[str, ...]:
    return ()


def until_noted(root: Path, _service: str) -> tuple[str, ...]:
    return () if NOTE.strip() in (root / PAGE).read_text(encoding="utf-8") else ("tally.md needs a note",)


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
