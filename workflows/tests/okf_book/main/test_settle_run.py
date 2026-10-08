"""A failed run's failures go to whoever can fix them: the book's writer, or a blocker per signature for everyone else."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from okf_book.main.tally import TALLY
from ostler.qa.attribution import Cause, Signature

from workhorse_workflows.okf_book.main import flow
from workhorse_workflows.okf_book.main.nodes.lead_findings import LeadFinding, record_findings
from workhorse_workflows.okf_book.main.nodes.progress_ledger import PROGRESS_NAME, UNRECORDED_STOP, LapCounts, read_laps, stalled
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, read_blockers
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult, stack_down_result
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, ScenarioOutcome
from workhorse_workflows.okf_book.workflow import OkfBook

UNREACHABLE = Signature(Cause.ENVIRONMENT, "", "could not connect", "GET /entries/…", 4, "lists: expected [200], observed null")
CRASHED = Signature(Cause.APP, "", "500", "POST /entries/…", 2, "adds: expected [201], observed 500")
MISREAD = Signature(Cause.BOOK, "", "422", "POST /entries/…", 1, "adds: expected [201], observed 422")
STRANDED = Signature(Cause.UNATTRIBUTED, "", "", "", 1, "signs out: expected /login, observed /editor")
GAPPED = Signature(Cause.ENVIRONMENT, "docs/fixtures/payment-provider.md", "", "", 3, "charges: probe exited 1", "payment provider")


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
                reason="2 checks failed this way; for example adds: expected [201], observed 500", cause="app"),
        Blocker(subject="tally: environment: GET /entries/… answered could not connect", service="tally", phase=Phase.EXERCISE,
                side=Side.ENVIRONMENT, reason="4 checks failed this way; for example lists: expected [200], observed null",
                cause="environment"),
    )


def test_an_absent_capability_is_parked_for_a_person_and_never_reaches_the_writer(tmp_path: Path) -> None:
    book = _book(tmp_path)
    gapped = FailedCheck(label="charges", cause=Cause.ENVIRONMENT, precondition="docs/fixtures/payment-provider.md", gap="payment provider")
    summary = RunSummary(status="failed", signatures=(GAPPED,),
                         scenarios={"tally-charge": ScenarioOutcome(status="failed", failed_checks=(gapped,))})
    exercised = ExerciseResult(lines=("scenario tally-charge: failed",), summary=summary)

    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=exercised)

    [blocker] = read_blockers(tmp_path)
    assert (blocker.subject, blocker.side) == ("tally: gapped: payment provider absent", Side.ENVIRONMENT)
    assert "only a person can supply it" in blocker.reason
    assert book.map_run_failures(index=0, exercised=exercised).state == "report"


def test_a_signature_the_next_run_no_longer_shows_is_forgotten(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_escalated_run(UNREACHABLE, CRASHED))

    _ = book.settle_run(index=0, run_failures_repaired=True, exercised=_escalated_run(CRASHED))

    assert [blocker.side for blocker in read_blockers(tmp_path)] == [Side.APP]


def test_a_run_whose_every_failure_is_escalated_skips_the_repair(tmp_path: Path) -> None:
    book = _book(tmp_path)

    step = book.map_run_failures(index=0, exercised=_escalated_run(CRASHED))

    assert step.state == "report"


def test_a_run_whose_only_failures_no_side_was_found_for_goes_to_the_owner_to_name_their_side(tmp_path: Path) -> None:
    book = _book(tmp_path)
    exercised = _escalated_run(STRANDED, CRASHED)

    step = book.map_run_failures(index=0, exercised=exercised)

    assert (step.state, step.params["run_failures"], step.params["exercised"]) == ("copy_source", {}, exercised)


def test_a_group_no_side_was_found_for_goes_to_report_once_the_owner_named_it(tmp_path: Path) -> None:
    book = _book(tmp_path)
    record_findings(tmp_path, (LeadFinding(service="tally", lap=1, signature=STRANDED.text(), count=1, side=Side.APP, evidence="redirect"),))

    step = book.map_run_failures(index=0, exercised=_escalated_run(STRANDED))

    assert step.state == "report"


def test_a_group_no_side_was_found_for_goes_to_report_after_the_owner_s_turn(tmp_path: Path) -> None:
    book = _book(tmp_path)

    step = book.map_run_failures(index=0, exercised=_escalated_run(STRANDED), run_failures_repaired=True)

    assert step.state == "report"


def test_a_repaired_run_whose_every_failure_is_escalated_blocks_nothing_on_the_book(tmp_path: Path) -> None:
    book = _book(tmp_path)

    exercised = _escalated_run(CRASHED)
    step = book.settle_run(index=0, run_failures_repaired=True, exercised=exercised)
    _ = book.map_run_failures(index=0, exercised=exercised, run_failures_repaired=True)

    assert step.state == "map_run_failures"

    assert [blocker.side for blocker in read_blockers(tmp_path)] == [Side.APP]


def _book_run(*signatures: Signature) -> ExerciseResult:
    misread = FailedCheck(label="adds", expected="[201]", actual="422", cause=Cause.BOOK, status="422", shape="POST /entries/…",
                          covers=("okf:docs/features/tally/tally.md#add:does:1",))
    summary = RunSummary(status="failed", scenarios={"tally-add": ScenarioOutcome(status="failed", failed_checks=(misread,))},
                         signatures=signatures)
    return ExerciseResult(lines=("failed",), summary=summary)


def test_a_repair_that_lowers_the_book_s_failed_checks_goes_back_to_its_writer(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_book_run(replace(MISREAD, count=9)))

    exercised = _book_run(MISREAD, CRASHED)
    _ = book.settle_run(index=0, run_failures_repaired=True, exercised=exercised)
    step = book.map_run_failures(index=0, exercised=exercised, run_failures_repaired=True)

    assert step.state == "copy_source"
    assert [blocker.side for blocker in read_blockers(tmp_path)] == [Side.APP]


def test_a_repair_that_leaves_the_book_s_failed_checks_flat_asks_the_attendant_with_the_trend(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_book_run(MISREAD))

    exercised = _book_run(MISREAD, CRASHED)
    step = book.settle_run(index=0, run_failures_repaired=True, exercised=exercised)
    _ = book.map_run_failures(index=0, exercised=exercised, run_failures_repaired=True)

    assert step.state == "map_run_failures"
    [stall] = [blocker for blocker in read_blockers(tmp_path) if blocker.side is Side.BOOK]
    assert stall.subject == "tally: book: POST /entries/… answered 422"
    assert stall.reason.startswith("the repair did not lower the book's failed checks, lap by lap: 1 → 1; 1 checks failed this way")
    assert (stall.cause, stall.pages) == ("book", ("docs/features/tally/tally.md",))
    assert stall.rerun.endswith(" docs/features/tally/tally.md")


def test_a_stall_no_signature_attributes_to_the_book_asks_the_attendant_about_the_workflow(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_book_run(CRASHED))

    exercised = _book_run(CRASHED)
    _ = book.settle_run(index=0, run_failures_repaired=True, exercised=exercised)
    _ = book.map_run_failures(index=0, exercised=exercised, run_failures_repaired=True)

    [stall] = [blocker for blocker in read_blockers(tmp_path) if blocker.side is Side.WORKFLOW]
    assert stall.subject == "tally: the book's failed checks did not fall"
    assert stall.pages == ("docs/features/tally/tally.md",)


def _probe_run() -> ExerciseResult:
    refused = FailedCheck(label="signs in", expected="[200]", actual="401", cause=Cause.ARRANGEMENT, status="401")
    summary = RunSummary(status="failed", scenarios={"probe-signed-in": ScenarioOutcome(status="failed", failed_checks=(refused,))},
                         signatures=(Signature(Cause.ARRANGEMENT, "docs/fixtures/signed-in.md", "401", "", 1, "signs in: observed 401"),))
    return ExerciseResult(lines=("problem: a precondition probe failed, so the book did not run",), summary=summary)


def test_a_stack_that_cannot_come_up_goes_to_its_runbook_s_writer_once_then_is_the_app_s_blocker_naming_only_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = _book(tmp_path)
    runbook = "docs/features/tally/ops/tally-stack.md"
    failures: dict[str, tuple[PageProblem, ...]] = {runbook: (PageProblem(runbook, f"{runbook}: the app's stack cannot come up: port 8080 is taken"),)}

    def _runbook(_root: Path, _service: str, exercised: ExerciseResult) -> dict[str, tuple[PageProblem, ...]]:
        return failures if exercised.stack_down else {}

    monkeypatch.setattr(flow, "stack_down_failures", _runbook)
    down = stack_down_result(("gap: okf:docs/features/tally/tally.md#adds:does:1: no-verify-declared: declare a check",), "port 8080 is taken")

    sent = book.settle_run(index=0, run_failures_repaired=False, exercised=down)
    assert (sent.state, sent.params["run_failures"], read_blockers(tmp_path)) == ("copy_source", failures, ())

    _ = book.settle_run(index=0, run_failures_repaired=True, exercised=down)
    [blocker] = read_blockers(tmp_path)
    assert (blocker.phase, blocker.side) == (Phase.EXERCISE, Side.APP)
    assert blocker.reason == "problem: the app's stack cannot come up: port 8080 is taken"


def _settle_and_map(book: OkfBook, exercised: ExerciseResult, *, repaired: bool = True) -> str:
    _ = book.settle_run(index=0, run_failures_repaired=repaired, exercised=exercised)
    return book.map_run_failures(index=0, exercised=exercised, run_failures_repaired=repaired).state


def test_a_run_a_probe_stopped_goes_back_to_its_writer_whatever_the_lap_before_counted(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_book_run(MISREAD))

    assert _settle_and_map(book, _probe_run()) == "copy_source"
    assert [lap.probes_only for lap in read_laps(tmp_path)] == [False, True]


def test_a_book_run_after_a_probe_stopped_one_is_measured_against_the_last_book_run(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_book_run(replace(MISREAD, count=9)))
    _ = _settle_and_map(book, _probe_run())

    assert _settle_and_map(book, _book_run(replace(MISREAD, count=5))) == "copy_source"
    assert not [blocker for blocker in read_blockers(tmp_path) if blocker.side is Side.WORKFLOW]


def _stopped_on(observation: str, count: int) -> ExerciseResult:
    early = _book_run(replace(MISREAD, count=count))
    assert early.summary is not None
    stop = {"stopped_on_repeat": f"the run stopped on one observation: {observation}", "stopped_on_observation": observation}
    return early.model_copy(update={"summary": early.summary.model_copy(update=stop)})


def test_a_whole_book_run_after_one_that_stopped_early_is_measured_against_nothing(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_stopped_on("landed on /login", 3))

    assert _settle_and_map(book, _book_run(replace(MISREAD, count=9))) == "copy_source"
    assert [lap.stopped_early for lap in read_laps(tmp_path)] == [True, False]


def test_a_run_that_stopped_early_on_another_observation_than_the_last_got_further_and_is_measured_against_nothing(
    tmp_path: Path,
) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_stopped_on("landed on /login", 3))

    assert _settle_and_map(book, _stopped_on("no Save button", 9)) == "copy_source"
    assert [lap.stopped_on for lap in read_laps(tmp_path)] == ["landed on /login", "no Save button"]


def test_a_run_that_stopped_early_on_the_same_observation_as_the_last_and_no_lower_stalls(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_stopped_on("landed on /login", 3))

    _ = _settle_and_map(book, _stopped_on("landed on /login", 3))

    [stall] = [blocker for blocker in read_blockers(tmp_path) if blocker.side is Side.BOOK]
    assert stall.reason.startswith("the repair did not lower the book's failed checks, lap by lap: 3 before the run stopped early → 3 before")


def test_a_lap_recorded_only_as_stopped_early_stopped_on_an_observation_no_later_lap_repeats(tmp_path: Path) -> None:
    (tmp_path / PROGRESS_NAME).write_text(
        json.dumps({"laps": [{"service": "tally", "failures": {"book": 3}, "stopped_early": True}, {"service": "tally"}]}),
        encoding="utf-8")

    laps = read_laps(tmp_path)
    assert [lap.stopped_on for lap in laps] == [UNRECORDED_STOP, ""]
    assert not stalled((laps[0], laps[0]))


def test_a_book_run_no_lower_than_the_last_book_run_stalls_with_the_probe_lap_marked_in_its_trend(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_book_run(replace(MISREAD, count=9)))
    _ = _settle_and_map(book, _probe_run())

    _ = _settle_and_map(book, _book_run(replace(MISREAD, count=9)))

    [stall] = [blocker for blocker in read_blockers(tmp_path) if blocker.side is Side.BOOK]
    assert stall.reason.startswith("the repair did not lower the book's failed checks, lap by lap: 9 → 1 at the probes → 9;")


def test_a_probe_stopped_run_no_lower_than_the_probe_stopped_run_before_it_stalls(tmp_path: Path) -> None:
    book = _book(tmp_path)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_probe_run())

    _ = _settle_and_map(book, _probe_run())

    [stall] = [blocker for blocker in read_blockers(tmp_path) if blocker.side is Side.BOOK]
    assert (stall.subject, stall.cause, stall.pages) == (
        "tally: arrangement: docs/fixtures/signed-in.md answered 401", "arrangement", ("docs/fixtures/signed-in.md",)
    )


def test_a_gapped_check_counts_as_no_failure_of_its_lap(tmp_path: Path) -> None:
    book = _book(tmp_path)

    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_escalated_run(GAPPED, CRASHED))

    assert read_laps(tmp_path) == (LapCounts(service="tally", failures={Cause.APP: 2}),)
