"""Run the book, or the pages and fixture pages named after the state file, against the real app. It prints each check that failed, or "All N scenarios pass"."""
from __future__ import annotations

import fcntl
import logging
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    EXERCISE_MODULE,
    CommandOutput,
    printed_lines,
    read_command_state,
    run_quietly,
)
from workhorse_workflows.okf_book.main.nodes.writer_jobs import Start, detached, run_or_attach
from workhorse_workflows.okf_book.main.nodes.writer_stack import KeptStack
from workhorse_workflows.okf_book.shared.book_run import (
    ExerciseResult,
    compile_scenarios,
    failed_run,
    release,
    run_plan,
    stack_down_result,
    with_app_logs,
)

USAGE = f"usage: python -m {EXERCISE_MODULE} <writer-commands.json> [page | fixture page ...]"
STACK_LOCK = "exercise.lock"


def repo_target(root: Path, target: str) -> str:
    """The repo-relative page a target names, read from the repository's root or else from where the command runs."""
    path = Path(target)
    if not path.is_absolute() and not (root / path).exists():
        path = Path.cwd() / path
    if path.is_absolute() and path.resolve().is_relative_to(root):
        path = path.resolve().relative_to(root)
    return path.as_posix()


def exercise_book(kept: KeptStack, root: Path, service: str, spec: Path, targets: Sequence[str] = ()) -> ExerciseResult:
    """Compile the service's book, bring its stack up or adopt the one the turn kept, and run every scenario or those the target pages name.

    A stack that serves stays up for the turn's next check. One that does not is stopped here.
    """
    outcome = compile_scenarios(root, service, spec, targets)
    if outcome.unmatched:
        named = ", ".join(outcome.unmatched)
        return failed_run(outcome.gaps, f"no scenario runs {named}: name a page of the book a scenario covers, or a fixture page a claim arranges")
    if not outcome.planned:
        return failed_run(outcome.gaps, "the book compiles to no plan")
    stack = kept.up(root, service)
    try:
        if not stack.up:
            return stack_down_result(outcome.gaps, stack.notes)
        return with_app_logs(run_plan(root, spec, outcome.gaps, stack.serving, outcome.only), stack.app_logs)
    finally:
        release(kept.logger, stack)


def exercised(argv: Sequence[str]) -> CommandOutput:
    """What the run for the command state file named first in `argv`, and the targets after it, exits with and prints. One run at a time holds the app."""
    state_path = Path(argv[0])
    state = read_command_state(state_path)
    root = state.root.resolve()
    targets = tuple(repo_target(root, target) for target in argv[1:])
    with (state_path.parent / STACK_LOCK).open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix="okf-spec-") as spec:
            kept = KeptStack(state_path.parent, logging.getLogger(EXERCISE_MODULE))
            result, _ = run_quietly(lambda: exercise_book(kept, root, state.service, Path(spec), targets))
    return CommandOutput(0 if result.passed else 1, printed_lines(result.lines))


def run_exercise(argv: Sequence[str], start: Start | None = None) -> CommandOutput:
    """What the writer's call of the run on the command state file named first in `argv`, and the targets after it, exits with and prints."""
    if not argv:
        return CommandOutput(2, (USAGE,))
    return run_or_attach(EXERCISE_MODULE, argv, start or detached(exercised))


def main() -> int:
    """Run the current book, or the part of it the arguments name, against the real app, and print what failed."""
    return run_exercise(sys.argv[1:]).print_and_exit_code()


if __name__ == "__main__":
    sys.exit(main())
