"""Compile a service's book, bring its app's stack up and run every scenario, and what that run did."""
from __future__ import annotations

import logging
import re
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ostler import index, model
from ostler.qa.attribution import Cause
from ostler.qa.plan_source import is_probe
from ostler.qa.runbook import select_stack
from pydantic import BaseModel, ConfigDict
from workhorse.runner.redact import REDACTED, SecretRedactor
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.kit.qa.runner import ensure_stack, release_stack, stack_stopped
from workhorse_workflows.okf_book.shared.entries import book_dir
from workhorse_workflows.okf_book.shared.book_compilation import gap_page
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.shared.scenarios import RunSummary, compile_book, plan_scenarios, run_scenarios, select_scenarios

COPY_IGNORED = shutil.ignore_patterns(".git", "__pycache__", ".venv", "node_modules", "*.pyc")
SERVER_ERROR = re.compile(r"\b(?:HTTP Error|returned|observed|answered HTTP) 5\d\d\b")
SECRET_SHAPES = (
    re.compile(r"(?i)\b((?:bearer|basic)\s+)[\w.~+/=-]+"),
    re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]*"),
    re.compile(r"(?i)\b([\w-]*(?:authorization|password|secret|token|api[_-]?key)[\w-]*[\"']?\s*[:=]\s*)[\"']?[^\s\"',}]+"),
)
LOG_TAIL_LINES = 40
LOG_TAIL_BYTES = 64_000
LOG_LINE_CHARS = 400
PROBE_STOPS = frozenset({Cause.ARRANGEMENT, Cause.ENVIRONMENT})


class ExerciseResult(BaseModel):
    """What running the book did: the lines to print, whether every scenario passed, whether the app's stack could not come up, and the run's summary when the plan ran."""

    model_config = ConfigDict(frozen=True)

    lines: tuple[str, ...]
    passed: bool = False
    summary: RunSummary | None = None
    stack_down: bool = False

    @property
    def stopped_at_probes(self) -> bool:
        """Whether a precondition probe stopped the run, so the book itself did not run."""
        return self.summary is not None and bool(self.summary.scenarios) and all(is_probe(name) for name in self.summary.scenarios)


def _failure_lines(summary: RunSummary) -> list[str]:
    lines: list[str] = []
    for name in summary.failed_scenarios:
        outcome = summary.scenarios[name]
        lines.append(f"scenario {name}: {outcome.status}, {outcome.failures} of {outcome.assertions} checks failed")
        lines.extend(f"  {line}" for line in outcome.failure_lines())
    lines.extend(f"claim {claim}: gapped: {gap} absent" for claim, gap in summary.gaps.items())
    lines.extend(f"problem: {problem}" for problem in (*summary.problems, *summary.runner_errors))
    return lines


def _masked(line: str) -> str:
    masked = SecretRedactor().redact(line)
    for shape in SECRET_SHAPES:
        masked = shape.sub(lambda hit: (hit.group(1) if hit.lastindex else "") + REDACTED, masked)
    return masked[:LOG_LINE_CHARS]


def app_log_lines(app_logs: Sequence[str], heading: str = "the app answered a server error") -> list[str]:
    """The end of each log the launched app wrote, with credentials masked, under *heading*, which says what the log explains."""
    lines: list[str] = []
    for log in app_logs:
        try:
            text = Path(log).read_bytes()[-LOG_TAIL_BYTES:].decode("utf-8", errors="replace")
        except OSError:
            continue
        tail = text.splitlines()[-LOG_TAIL_LINES:]
        if tail:
            lines.append(f"{heading}, and its log {log} ends with:")
            lines.extend(f"  {_masked(line)}" for line in tail)
    return lines


def _run_in_copy(root: Path, spec: Path, only: Sequence[str], lap: Path, stack_check: Callable[[], str] | None = None) -> RunSummary:
    with tempfile.TemporaryDirectory(prefix="okf-exercise-") as tmp:
        app = Path(tmp) / "app"
        _ = shutil.copytree(root, app, ignore=COPY_IGNORED)
        return run_scenarios(app, spec, only, lap, stack_check)


@dataclass(frozen=True, slots=True)
class CompileOutcome:
    """What compiling the book left: the gaps it names, whether it compiled to a plan, the scenarios the targets name, and the targets that name none."""

    gaps: tuple[str, ...]
    planned: bool
    only: tuple[str, ...] = ()
    unmatched: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StackReadiness:
    """Whether the app's stack is up, whether it serves, why it is not up, the process groups its bring-up started, and the logs of the apps it launched."""

    up: bool
    serving: bool
    notes: str
    owned: tuple[str, ...] = ()
    app_logs: tuple[str, ...] = ()


def failed_run(gaps: tuple[str, ...], problem: str) -> ExerciseResult:
    """The run that stopped on `problem` before any scenario ran."""
    return ExerciseResult(lines=(*gaps, f"problem: {problem}"))


def stack_down_result(gaps: tuple[str, ...], notes: str) -> ExerciseResult:
    """The run that stopped because the app's stack could not come up."""
    return ExerciseResult(lines=(*gaps, f"problem: the app's stack cannot come up: {notes}"), stack_down=True)


def stack_stopped_result(gaps: tuple[str, ...], reason: str, app_logs: Sequence[str]) -> ExerciseResult:
    """The run that stopped because the app stopped serving partway through, which measured nothing of the book after that."""
    logs = tuple(f"problem: {line}" for line in app_log_lines(app_logs, "the app stopped serving"))
    return ExerciseResult(lines=(*gaps, f"problem: the app's stack stopped serving: {reason}", *logs), stack_down=True)


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
    """The runbook pages `bring_up` starts the service's stack from, or none when the book names no single stack.

    The pages parse through ostler's index, so a turn's later checks reparse only the pages written since.
    """
    with index.session(root):
        graph = model.load(find_docs_root("", str(root)))
    return tuple(node.id for node in select_stack(graph, near=book_dir(root, service)).runbooks)


def stack_down_failures(root: Path, service: str, exercised: ExerciseResult) -> dict[str, tuple[PageProblem, ...]]:
    """Each runbook page of the service's own book its stack came up from, with why it did not, or none when the run reached the app."""
    if not exercised.stack_down:
        return {}
    folder = book_dir(root, service).relative_to(root).as_posix()
    problem = "\n".join(line.removeprefix("problem: ") for line in exercised.lines if line.startswith("problem: "))
    return {page: (PageProblem(page, f"{page}: {problem}"),) for page in stack_pages(root, service) if page.startswith(f"{folder}/")}


def bring_up(logger: logging.Logger, root: Path, service: str) -> StackReadiness:
    """Bring up the stack the service's book declares, or adopt one serving."""
    stack = ensure_stack(logger, repo_dir=str(root), near=str(book_dir(root, service)))
    return StackReadiness(
        up=stack.ready not in ("no", "none"), serving=stack.ready == "yes", notes=stack.notes,
        owned=stack.owned_pgids, app_logs=stack.app_logs)


def release(logger: logging.Logger, stack: StackReadiness) -> None:
    """Stop the processes `bring_up` started, so the next bring-up finds the app's ports free."""
    release_stack(logger, stack.owned)


def run_plan(root: Path, spec: Path, gaps: tuple[str, ...], stack: StackReadiness, only: Sequence[str] = ()) -> ExerciseResult:
    """Run the named compiled scenarios, every one when none is named, on a copy of the app when it serves nothing.

    The run stops at the first scenario after a server the stack's bring-up launched exited, since
    every later scenario would fail on the app's absence, and the result sends the runbook to repair.

    A run of every scenario probes each precondition first. A probe that fails on what its fixture
    arranges, or on the environment, stops the run before the book, since every claim that fixture
    arranges would fail the same way. A probe that finds a capability absent stops nothing, because
    the book's run gaps the claims that need it and runs the rest. The probes and the book are one
    lap, so each precondition is built once across both.
    """
    runner = run_scenarios if stack.serving else _run_in_copy
    with tempfile.TemporaryDirectory(prefix="okf-lap-") as lap:
        result = _run_lap(root, spec, gaps, only, lambda names: runner(root, spec, names, Path(lap), lambda: stack_stopped(stack.owned)))
    stopped = stack_stopped(stack.owned)
    return stack_stopped_result(gaps, stopped, stack.app_logs) if stopped else result


def _run_lap(root: Path, spec: Path, gaps: tuple[str, ...], only: Sequence[str], run: Callable[[Sequence[str]], RunSummary]) -> ExerciseResult:
    if not only:
        scenarios, _problems = plan_scenarios(root, spec)
        probes = [scenario.id for scenario in scenarios if is_probe(scenario.id)]
        if probes:
            probed = run(probes)
            if any(signature.cause in PROBE_STOPS and not signature.gap for signature in probed.signatures):
                lines = ("problem: a precondition probe failed, so the book did not run", *gaps, *_failure_lines(probed))
                return ExerciseResult(lines=lines, summary=probed)
            only = [scenario.id for scenario in scenarios if not is_probe(scenario.id)]
    summary = run(only)
    empty = () if summary.scenarios else ("problem: the plan runs no scenario",)
    failures = (*gaps, *_failure_lines(summary), *empty)
    if failures:
        return ExerciseResult(lines=failures, summary=summary)
    return ExerciseResult(lines=(f"All {len(summary.scenarios)} scenarios pass",), passed=True, summary=summary)


def with_app_logs(result: ExerciseResult, app_logs: Sequence[str]) -> ExerciseResult:
    """The run's result with the end of the app's logs after its lines, when a check failed on a server error the app answered."""
    if not any(SERVER_ERROR.search(line) for line in result.lines):
        return result
    return result.model_copy(update={"lines": (*result.lines, *app_log_lines(app_logs))})
