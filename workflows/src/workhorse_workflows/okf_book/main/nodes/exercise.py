"""Run the book, or the pages and fixture pages named after the state file, against the real app. It prints each check that failed, or "All N scenarios pass"."""
from __future__ import annotations

import logging
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,
    EXERCISE_MODULE,
    CommandOutput,
    announce_running,
    printed_lines,
    run_quietly,
    spend_check_or_scenario_run,
)
from workhorse_workflows.okf_book.shared.book_run import (
    ExerciseResult,
    bring_up,
    compile_scenarios,
    failed_run,
    release,
    run_plan,
    stack_down_result,
)

USAGE = f"usage: python -m {EXERCISE_MODULE} <writer-commands.json> [page | fixture page ...]"


def repo_target(root: Path, target: str) -> str:
    """The repo-relative page a target names, read from the repository's root or else from where the command runs."""
    path = Path(target)
    if not path.is_absolute() and not (root / path).exists():
        path = Path.cwd() / path
    if path.is_absolute() and path.resolve().is_relative_to(root):
        path = path.resolve().relative_to(root)
    return path.as_posix()


def exercise_book(logger: logging.Logger, root: Path, service: str, spec: Path, targets: Sequence[str] = ()) -> ExerciseResult:
    """Compile the service's book, bring its stack up, run every scenario or those the target pages name, and stop what the bring-up started."""
    outcome = compile_scenarios(root, service, spec, targets)
    if outcome.unmatched:
        named = ", ".join(outcome.unmatched)
        return failed_run(outcome.gaps, f"no scenario runs {named}: name a page of the book a scenario covers, or a fixture page a claim arranges")
    if not outcome.planned:
        return failed_run(outcome.gaps, "the book compiles to no plan")
    stack = bring_up(logger, root, service)
    try:
        if not stack.up:
            return stack_down_result(outcome.gaps, stack.notes)
        return run_plan(root, spec, outcome.gaps, stack.serving, outcome.only)
    finally:
        release(logger, stack)


def run_exercise(argv: Sequence[str]) -> CommandOutput:
    """What the run exits with and prints for the command state file named first in `argv`, and the targets after it."""
    if not argv:
        return CommandOutput(2, (USAGE,))
    state = spend_check_or_scenario_run(Path(argv[0]))
    if state is None:
        return CommandOutput(1, (CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,))
    announce_running()
    root = state.root.resolve()
    targets = tuple(repo_target(root, target) for target in argv[1:])
    with tempfile.TemporaryDirectory(prefix="okf-spec-") as spec:
        exercised, _ = run_quietly(lambda: exercise_book(logging.getLogger(EXERCISE_MODULE), root, state.service, Path(spec), targets))
    return CommandOutput(0 if exercised.passed else 1, printed_lines(exercised.lines))


def main() -> int:
    """Run the current book, or the part of it the arguments name, against the real app, and print what failed."""
    return run_exercise(sys.argv[1:]).print_and_exit_code()


if __name__ == "__main__":
    sys.exit(main())
