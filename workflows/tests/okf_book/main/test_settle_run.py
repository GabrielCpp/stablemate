"""A failed run's failures go to whoever can fix them: the book's writer, or a blocker per signature for everyone else."""
from __future__ import annotations

from pathlib import Path

from okf_book.main.tally import TALLY
from ostler.qa.attribution import Cause, Signature

from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, read_blockers
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, ScenarioOutcome
from workhorse_workflows.okf_book.workflow import OkfBook

UNREACHABLE = Signature(Cause.ENVIRONMENT, "", "could not connect", "GET /entries/…", 4, "lists: expected [200], observed null")
CRASHED = Signature(Cause.APP, "", "500", "POST /entries/…", 2, "adds: expected [201], observed 500")
MISREAD = Signature(Cause.BOOK, "", "422", "POST /entries/…", 1, "adds: expected [201], observed 422")


def _escalated_run(*signatures: Signature) -> ExerciseResult:
    crashed = FailedCheck(label="adds", expected="[201]", actual="500", cause=Cause.APP, status="500")
    outcome = ScenarioOutcome(status="failed", failed_checks=(crashed,))
    summary = RunSummary(status="failed", scenarios={"tally-add": outcome}, signatures=signatures)
    return ExerciseResult(lines=("scenario tally-add: failed",), summary=summary)


def _book(tmp_path: Path) -> OkfBook:
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY,))
    _ = book.start()
    return book


def test_each_signature_another_party_must_fix_is_one_blocker_on_its_side(tmp_path: Path) -> None:
    book = _book(tmp_path)

    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_escalated_run(UNREACHABLE, CRASHED, MISREAD))

    assert read_blockers(tmp_path) == (
        Blocker(subject="tally: app: POST /entries/… answered 500", service="tally", phase=Phase.EXERCISE, side=Side.APP,
                reason="2 checks failed this way; for example adds: expected [201], observed 500"),
        Blocker(subject="tally: environment: GET /entries/… answered could not connect", service="tally", phase=Phase.EXERCISE,
                side=Side.ENVIRONMENT, reason="4 checks failed this way; for example lists: expected [200], observed null"),
    )


def test_a_signature_the_next_run_no_longer_shows_is_forgotten(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_escalated_run(UNREACHABLE, CRASHED))

    _ = book.settle_run(index=0, run_failures_repaired=True, exercised=_escalated_run(CRASHED))

    assert [blocker.side for blocker in read_blockers(tmp_path)] == [Side.APP]


def test_a_run_whose_every_failure_is_escalated_skips_the_repair(tmp_path: Path) -> None:
    book = _book(tmp_path)

    step = book.map_run_failures(index=0, exercised=_escalated_run(CRASHED))

    assert step.state == "report"


def test_a_repaired_run_whose_every_failure_is_escalated_blocks_nothing_on_the_book(tmp_path: Path) -> None:
    book = _book(tmp_path)

    _ = book.settle_run(index=0, run_failures_repaired=True, exercised=_escalated_run(CRASHED))

    assert [blocker.side for blocker in read_blockers(tmp_path)] == [Side.APP]


def test_a_repaired_run_that_still_fails_the_book_is_a_book_blocker(tmp_path: Path) -> None:
    book = _book(tmp_path)
    misread = FailedCheck(label="adds", expected="[201]", actual="422", covers=("okf:docs/features/tally/tally.md#add:does:1",))
    summary = RunSummary(status="failed", scenarios={"tally-add": ScenarioOutcome(status="failed", failed_checks=(misread,))},
                         signatures=(MISREAD, CRASHED))

    _ = book.settle_run(index=0, run_failures_repaired=True, exercised=ExerciseResult(lines=("failed",), summary=summary))

    assert sorted(blocker.side for blocker in read_blockers(tmp_path)) == [Side.APP, Side.BOOK]
