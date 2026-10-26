"""One service's book run against the app: compile the book, bring the stack up, and run every scenario."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from workhorse.pyflow import Continue, Done
from workhorse_workflows.kit.qa.runner import release_stack, stack_stopped
from workhorse_workflows.okf_book.shared.blueprint import blueprint
from workhorse_workflows.okf_book.shared.book_run import (
    CompileOutcome,
    ExerciseResult,
    StackReadiness,
    bring_up,
    compile_scenarios,
    copy_env,
    failed_run,
    release,
    book_runbooks,
    run_plan,
    stack_down_result,
    unplanned_problem,
    with_app_logs,
)
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.source_repo import SourceRepo

SPEC_DIR = "spec"
_THIS_PROCESS = uuid.uuid4().hex
DRY_RUN_NOTE = "dry run: the stack stayed down and no scenario ran"


def _compiled_in_dry_run(_logger: logging.Logger, *_args: object) -> CompileOutcome:
    return CompileOutcome(gaps=(), planned=True)


def _stack_in_dry_run(_logger: logging.Logger, *_args: object) -> StackReadiness:
    return StackReadiness(up=True, serving=True, notes=DRY_RUN_NOTE)


def _exercised_in_dry_run(_logger: logging.Logger, *_args: object) -> ExerciseResult:
    return ExerciseResult(lines=(DRY_RUN_NOTE,), passed=True)


@blueprint.node(stub=_compiled_in_dry_run)
def compile_book_scenarios(logger: logging.Logger, root: Path, service: str, spec: Path, source: SourceRepo) -> CompileOutcome:
    """Compile the service's book into `spec`. A dry run compiles nothing and holds a plan."""
    del logger
    return compile_scenarios(root, service, spec, (), source)


@blueprint.node(stub=_stack_in_dry_run)
def bring_book_stack_up(logger: logging.Logger, root: Path, service: str) -> StackReadiness:
    """Bring the service's stack up. A dry run starts nothing and reports a serving stack."""
    return bring_up(logger, root, service)


@blueprint.node(stub=_exercised_in_dry_run)
def run_book_scenarios(logger: logging.Logger, root: Path, spec: Path, gaps: tuple[str, ...], stack: StackReadiness) -> ExerciseResult:
    """Run the compiled scenarios against the stack. A dry run runs none and passes."""
    del logger
    return run_plan(root, spec, gaps, stack)


class ExerciseBook(BookFlow):
    """Runs one service's book against the real app, and ends on what the run did for the caller to settle."""

    service: str = ""
    source: SourceRepo | None = None

    @property
    def source_repo(self) -> SourceRepo:
        return self.source or SourceRepo(path=self.root)

    def start(self) -> Continue[...] | Done:
        """Compile the book into scenarios. A book that compiles to no plan has failed its run, with the reason it has none."""
        outcome = self.call(compile_book_scenarios, self.root, self.service, self.records_dir / SPEC_DIR / self.service, self.source_repo)
        if not outcome.planned:
            problem = unplanned_problem(self.root, self.service)
            return Done(failed_run(outcome.gaps, problem)).because("the book compiles to no plan")
        return Continue(outcome, self.bring_up_stack, gaps=outcome.gaps).because("bring the app's stack up")

    def bring_up_stack(self, gaps: tuple[str, ...], retried_in: str = "") -> Continue[...] | Done:
        """Bring the app's stack up, or adopt one serving. A stack that cannot come up ends the run."""
        stack = self.call(bring_book_stack_up, self.root, self.service)
        if not stack.up:
            release(self.logger, stack)
            return Done(stack_down_result(gaps, stack.notes)).because("the app's stack cannot come up")
        return Continue(
            stack, self.run_scenarios, gaps=gaps, serving=stack.serving, owned=stack.owned, app_logs=stack.app_logs, retried_in=retried_in,
        ).because("run the scenarios")

    def run_scenarios(
        self, gaps: tuple[str, ...], serving: bool, owned: tuple[str, ...] = (), app_logs: tuple[str, ...] = (), retried_in: str = "",
    ) -> Continue[...] | Done:
        """Run every scenario against the app, on a copy of it when it serves nothing, then stop what bring-up started. A server gone before the first scenario comes up once more first. A resumed run gets that once more again, because the process before it stopped the server on its way out."""
        if retried_in != _THIS_PROCESS and stack_stopped(owned):
            release_stack(self.logger, owned)
            return Continue(owned, self.bring_up_stack, gaps=gaps, retried_in=_THIS_PROCESS).because("the stack's server is gone: bring it up again")
        try:
            stack = StackReadiness(up=True, serving=serving, notes="", owned=owned, app_logs=app_logs, runbooks=book_runbooks(self.root, self.service),
                                  env=copy_env(self.root, self.service), source=self.source_repo)
            exercised = with_app_logs(self.call(run_book_scenarios, self.root, self.records_dir / SPEC_DIR / self.service, gaps, stack), app_logs)
        finally:
            release_stack(self.logger, owned)
        return Done(exercised).because("the scenarios ran")
