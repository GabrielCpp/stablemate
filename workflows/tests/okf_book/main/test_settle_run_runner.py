"""A run the runner itself stopped measured nothing of the book: it is a blocker on the runner's side, and no lap of the book. A run stopped on one repeated failure measured the book, and goes to its owner."""
from __future__ import annotations

from pathlib import Path

from okf_book.main.tally import TALLY
from ostler.qa.attribution import Cause, Signature

from workhorse_workflows.okf_book.main.nodes.progress_ledger import read_laps
from workhorse_workflows.okf_book.shared.blockers import Phase, Side, read_blockers
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, ScenarioOutcome
from workhorse_workflows.okf_book.workflow import OkfBook

LAUNCH_ERROR = "OSError: [Errno 7] Argument list too long: 'python3'"


def _settled(tmp_path: Path, summary: RunSummary) -> OkfBook:
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY,))
    exercised = ExerciseResult(lines=tuple(f"problem: {error}" for error in summary.runner_errors), summary=summary)
    _ = book.settle_run(index=0, run_failures_repaired=True, exercised=exercised)
    return book


def test_a_runner_that_raised_is_an_ostler_blocker_and_no_lap(tmp_path: Path) -> None:
    _ = _settled(tmp_path, RunSummary(status="invalid", runner_errors=(LAUNCH_ERROR,)))

    (blocker,) = read_blockers(tmp_path)
    assert (blocker.service, blocker.phase, blocker.side) == ("tally", Phase.EXERCISE, Side.OSTLER)
    assert LAUNCH_ERROR in blocker.reason
    assert read_laps(tmp_path) == ()


def test_a_driver_that_could_not_start_is_an_environment_blocker(tmp_path: Path) -> None:
    _ = _settled(tmp_path, RunSummary(status="blocked", runner_errors=("maestro CLI is not installed",)))

    (blocker,) = read_blockers(tmp_path)
    assert blocker.side is Side.ENVIRONMENT


def test_a_run_stopped_on_one_repeated_book_failure_goes_to_the_book_s_owner_as_a_lap_that_stopped_early(tmp_path: Path) -> None:
    repeat = "the run stopped after 3 scenarios on 3 pages failed on one observation: landed on /login"
    redirected = FailedCheck(label="opens", expected="/editor", actual="/login", cause=Cause.BOOK,
                             covers=("okf:docs/features/tally/tally.md#list:does:1",))
    summary = RunSummary(status="failed", stopped_on_repeat=repeat,
                         scenarios={"tally-list": ScenarioOutcome(status="failed", failed_checks=(redirected,))},
                         signatures=(Signature(Cause.BOOK, "", "", "/editor", 3, "opens: expected /editor, observed /login"),))
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY,))

    step = book.settle_run(index=0, run_failures_repaired=False, exercised=ExerciseResult(lines=(f"problem: {repeat}",), summary=summary))

    assert step.state == "map_run_failures"
    assert read_blockers(tmp_path) == ()
    [lap] = read_laps(tmp_path)
    assert lap.stopped_early
