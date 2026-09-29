"""Compile a service's book, bring its app's stack up and run every scenario, and what that run did."""
from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ostler import model
from ostler.qa.runbook import select_stack
from pydantic import BaseModel, ConfigDict
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.kit.qa.runner import ensure_stack, release_stack
from workhorse_workflows.okf_book.shared.entries import book_dir
from workhorse_workflows.okf_book.shared.book_compilation import gap_page
from workhorse_workflows.okf_book.shared.scenarios import RunSummary, compile_book, plan_scenarios, run_scenarios, select_scenarios

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
        lines.extend(f"  {line}" for line in outcome.failure_lines())
    lines.extend(f"problem: {problem}" for problem in (*summary.problems, *summary.runner_errors))
    return lines


def _run_in_copy(root: Path, spec: Path, only: Sequence[str]) -> RunSummary:
    with tempfile.TemporaryDirectory(prefix="okf-exercise-") as tmp:
        app = Path(tmp) / "app"
        _ = shutil.copytree(root, app, ignore=COPY_IGNORED)
        return run_scenarios(app, spec, only)


@dataclass(frozen=True, slots=True)
class CompileOutcome:
    """What compiling the book left: the gaps it names, whether it compiled to a plan, the scenarios the targets name, and the targets that name none."""

    gaps: tuple[str, ...]
    planned: bool
    only: tuple[str, ...] = ()
    unmatched: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StackReadiness:
    """Whether the app's stack is up, whether it serves, why it is not up, and the process groups its bring-up started."""

    up: bool
    serving: bool
    notes: str
    owned: tuple[str, ...] = ()


def failed_run(gaps: tuple[str, ...], problem: str) -> ExerciseResult:
    """The run that stopped on `problem` before any scenario ran."""
    return ExerciseResult(lines=(*gaps, f"problem: {problem}"))


def stack_down_result(gaps: tuple[str, ...], notes: str) -> ExerciseResult:
    """The run that stopped because the app's stack could not come up."""
    return ExerciseResult(lines=(*gaps, f"problem: the app's stack cannot come up: {notes}"), stack_down=True)


def compile_scenarios(root: Path, service: str, spec: Path, targets: Sequence[str] = ()) -> CompileOutcome:
    """Compile the service's whole book into `spec`, and pick the scenarios the target pages name, with only their gaps."""
    compiled = compile_book(root, (service,), spec)
    kept = [gap for gap in compiled.gaps if not targets or gap_page(gap) in targets]
    gaps = tuple(f"gap: {gap.obligation_id}: {gap.kind}: {gap.detail}" for gap in kept)
    if not targets or not compiled.planned:
        return CompileOutcome(gaps=gaps, planned=compiled.planned)
    scenarios, _problems = plan_scenarios(root, spec)
    selection = select_scenarios(scenarios, compiled.arranging, targets)
    return CompileOutcome(gaps=gaps, planned=True, only=selection.scenarios, unmatched=selection.unmatched)


def stack_pages(root: Path, service: str) -> tuple[str, ...]:
    """The runbook pages `bring_up` starts the service's stack from, or none when the book names no single stack."""
    return tuple(node.id for node in select_stack(model.load(find_docs_root("", str(root))), near=book_dir(root, service)).runbooks)


def bring_up(logger: logging.Logger, root: Path, service: str) -> StackReadiness:
    """Bring up the stack the service's book declares, or adopt one serving."""
    stack = ensure_stack(logger, repo_dir=str(root), near=str(book_dir(root, service)))
    return StackReadiness(
        up=stack.ready not in ("no", "none"), serving=stack.ready == "yes", notes=stack.notes,
        owned=stack.owned_pgids)


def release(logger: logging.Logger, stack: StackReadiness) -> None:
    """Stop the processes `bring_up` started, so the next bring-up finds the app's ports free."""
    release_stack(logger, stack.owned)


def run_plan(root: Path, spec: Path, gaps: tuple[str, ...], serving: bool, only: Sequence[str] = ()) -> ExerciseResult:
    """Run the named compiled scenarios, every one when none is named, on a copy of the app when it serves nothing."""
    summary = run_scenarios(root, spec, only) if serving else _run_in_copy(root, spec, only)
    empty = () if summary.scenarios else ("problem: the plan runs no scenario",)
    failures = (*gaps, *_failure_lines(summary), *empty)
    if failures:
        return ExerciseResult(lines=failures, summary=summary)
    return ExerciseResult(lines=(f"All {len(summary.scenarios)} scenarios pass",), passed=True, summary=summary)
