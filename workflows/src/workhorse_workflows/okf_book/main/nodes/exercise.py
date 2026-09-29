"""Run the book against the real app. It prints each check that failed, or "All N scenarios pass"."""
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

USAGE = f"usage: python -m {EXERCISE_MODULE} <writer-commands.json>"


def exercise_book(logger: logging.Logger, root: Path, service: str, spec: Path) -> ExerciseResult:
    """Compile the service's book, bring its stack up, run every scenario, and stop what the bring-up started."""
    outcome = compile_scenarios(root, service, spec)
    if not outcome.planned:
        return failed_run(outcome.gaps, "the book compiles to no plan")
    stack = bring_up(logger, root, service)
    try:
        if not stack.up:
            return stack_down_result(outcome.gaps, stack.notes)
        return run_plan(root, spec, outcome.gaps, stack.serving)
    finally:
        release(logger, stack)


def run_exercise(argv: Sequence[str]) -> CommandOutput:
    """What the run exits with and prints for command state file named in `argv`."""
    if len(argv) != 1:
        return CommandOutput(2, (USAGE,))
    state = spend_check_or_scenario_run(Path(argv[0]))
    if state is None:
        return CommandOutput(1, (CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,))
    with tempfile.TemporaryDirectory(prefix="okf-spec-") as spec:
        exercised, _ = run_quietly(lambda: exercise_book(logging.getLogger(EXERCISE_MODULE), state.root.resolve(), state.service, Path(spec)))
    return CommandOutput(0 if exercised.passed else 1, printed_lines(exercised.lines))


def main() -> int:
    """Run the current book against the real app, and print what failed."""
    return run_exercise(sys.argv[1:]).print_and_exit_code()


if __name__ == "__main__":
    sys.exit(main())
