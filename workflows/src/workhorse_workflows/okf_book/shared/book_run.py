"""Compile a service's book, bring its app's stack up and run every scenario, and what that run did."""
from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from workhorse_workflows.kit.qa.runner import ensure_stack
from workhorse_workflows.okf_book.shared.entries import book_dir
from workhorse_workflows.okf_book.shared.scenarios import RunSummary, compile_book, run_scenarios

COPY_IGNORED = shutil.ignore_patterns(".git", "__pycache__", ".venv", "node_modules", "*.pyc")


class ExerciseResult(BaseModel):
    """What running the book did: the lines to print, whether every scenario passed, whether the app's stack could not come up, and the run's summary when the plan ran."""

    model_config = ConfigDict(frozen=True)

    lines: tuple[str, ...]
    passed: bool = False
    summary: RunSummary | None = None
    stack_down: bool = False


def _failure_lines(summary: RunSummary) -> list[str]:
    lines: list[str] = []
    for name in summary.failed_scenarios:
        outcome = summary.scenarios[name]
        lines.append(f"scenario {name}: {outcome.status}, {outcome.failures} of {outcome.assertions} checks failed")
        lines.extend(f"  {check.failure_line()}" for check in outcome.failed_checks)
        if outcome.message.strip():
            lines.append(f"  {outcome.message.strip().splitlines()[-1]}")
    lines.extend(f"problem: {problem}" for problem in (*summary.problems, *summary.runner_errors))
    return lines


def _run_in_copy(root: Path, spec: Path) -> RunSummary:
    with tempfile.TemporaryDirectory(prefix="okf-exercise-") as tmp:
        app = Path(tmp) / "app"
        _ = shutil.copytree(root, app, ignore=COPY_IGNORED)
        return run_scenarios(app, spec, ())


@dataclass(frozen=True, slots=True)
class CompileOutcome:
    """What compiling the book left: the gaps it names, and whether it compiled to a plan."""

    gaps: tuple[str, ...]
    planned: bool


@dataclass(frozen=True, slots=True)
class StackReadiness:
    """Whether the app's stack is up, whether it serves, and why it is not up."""

    up: bool
    serving: bool
    notes: str


def failed_run(gaps: tuple[str, ...], problem: str) -> ExerciseResult:
    """The run that stopped on `problem` before any scenario ran."""
    return ExerciseResult(lines=(*gaps, f"problem: {problem}"))


def stack_down_result(gaps: tuple[str, ...], notes: str) -> ExerciseResult:
    """The run that stopped because the app's stack could not come up."""
    return ExerciseResult(lines=(*gaps, f"problem: the app's stack cannot come up: {notes}"), stack_down=True)


def compile_scenarios(root: Path, service: str, spec: Path) -> CompileOutcome:
    """Compile the service's book into `spec`."""
    compiled = compile_book(root, (service,), spec)
    gaps = tuple(f"gap: {gap.obligation_id}: {gap.kind}: {gap.detail}" for gap in compiled.gaps)
    return CompileOutcome(gaps=gaps, planned=compiled.planned)


def bring_up(logger: logging.Logger, root: Path, service: str) -> StackReadiness:
    """Bring up the stack the service's book declares, or adopt one serving."""
    stack = ensure_stack(logger, repo_dir=str(root), near=str(book_dir(root, service)))
    return StackReadiness(up=stack.ready not in ("no", "none"), serving=stack.ready == "yes", notes=stack.notes)


def run_plan(root: Path, spec: Path, gaps: tuple[str, ...], serving: bool) -> ExerciseResult:
    """Run every compiled scenario, on a copy of the app when it serves nothing."""
    summary = run_scenarios(root, spec, ()) if serving else _run_in_copy(root, spec)
    empty = () if summary.scenarios else ("problem: the plan runs no scenario",)
    failures = (*gaps, *_failure_lines(summary), *empty)
    if failures:
        return ExerciseResult(lines=failures, summary=summary)
    return ExerciseResult(lines=(f"All {len(summary.scenarios)} scenarios pass",), passed=True, summary=summary)
