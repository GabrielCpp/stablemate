"""The gate a run stops at: each blocker's rerun command, and what the run settles itself once the gate is answered."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from okf_book.main.tally import TALLY
from ostler.qa.attribution import Cause, Signature

from workhorse_workflows.okf_book.main.nodes import gate
from workhorse_workflows.okf_book.main.nodes.claim_snapshot import book_claims, changed_claims, write_snapshot
from workhorse_workflows.okf_book.main.nodes.gate import GATE_DIR, SNAPSHOT_FOLDER, GateRerun, rerun_command, settle_gate, take_failures
from workhorse_workflows.okf_book.main.nodes.writer_commands import CHECK_MODULE, EXERCISE_MODULE
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, read_blockers, record_blocker
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, ScenarioOutcome
from workhorse_workflows.okf_book.workflow import OkfBook

ADD = "docs/features/tally/add.md"
SIGNED_IN = "docs/features/tally/fixtures/signed-in.md"
SERVICES = ("tally",)


def _endpoint(status: str = "201", does: str = "records the entry") -> str:
    return "\n".join(["---", "type: endpoint", "title: add", "---", "# add", "",
                      "- method: POST", "- path: /entries", f"- status: {status}", f"- does: {does}", ""])


def _fixture(persistence: str = "keeps the signed-in user") -> str:
    return "\n".join(["---", "type: fixture", "title: signed in", "---", "# signed in", "", f"- persistence: {persistence}", ""])


def _book(root: Path) -> Path:
    for page, text in ((ADD, _endpoint()), (SIGNED_IN, _fixture())):
        (root / page).parent.mkdir(parents=True, exist_ok=True)
        _ = (root / page).write_text(text, encoding="utf-8")
    return root


def _blocker(side: Side = Side.BOOK, cause: str = "book") -> Blocker:
    return Blocker(subject=f"tally: {cause}: POST /entries/… answered 500", service="tally", phase=Phase.EXERCISE, side=side,
                   reason="2 checks failed this way", cause=cause, pages=(ADD,))


def _rerun_with(monkeypatch: pytest.MonkeyPatch, rerun: GateRerun) -> list[tuple[str, ...]]:
    asked: list[tuple[str, ...]] = []

    def _rerun(root: Path, records_dir: Path, service: str, pages: Sequence[str]) -> GateRerun:
        asked.append(tuple(pages))
        return rerun

    monkeypatch.setattr(gate, "rerun_pages", _rerun)
    return asked


def test_a_rerun_command_names_the_check_its_phase_runs_and_only_the_blockers_pages(tmp_path: Path) -> None:
    exercise = rerun_command(tmp_path, "tally", Phase.EXERCISE, (ADD, "docs/features/tally/a page.md"))
    check = rerun_command(tmp_path, "tally", Phase.WRITE, (ADD,))

    assert EXERCISE_MODULE in exercise and exercise.endswith(f"{ADD} 'docs/features/tally/a page.md'")
    assert CHECK_MODULE in check and check.endswith(ADD)
    assert rerun_command(tmp_path, "tally", Phase.EXERCISE, ()) == ""


def test_a_changed_expected_outcome_goes_back_to_its_page_s_writer(tmp_path: Path) -> None:
    before = book_claims(_book(tmp_path), SERVICES)
    _ = (tmp_path / ADD).write_text(_endpoint(status="200"), encoding="utf-8")

    [problem] = changed_claims(before, book_claims(tmp_path, SERVICES))

    assert problem.page == ADD
    assert "changed the `status` claim" in problem.text and "from `201` to `200`" in problem.text


def test_fixture_edits_and_added_claims_stay_free(tmp_path: Path) -> None:
    before = book_claims(_book(tmp_path), SERVICES)
    _ = (tmp_path / SIGNED_IN).write_text(_fixture(persistence="keeps a super admin"), encoding="utf-8")
    _ = (tmp_path / ADD).write_text(_endpoint() + "- does: returns the entry's id\n", encoding="utf-8")

    assert changed_claims(before, book_claims(tmp_path, SERVICES)) == ()


def test_a_removed_claim_goes_back_to_its_page_s_writer(tmp_path: Path) -> None:
    before = book_claims(_book(tmp_path), SERVICES)
    _ = (tmp_path / ADD).write_text(_endpoint().replace("- does: records the entry\n", ""), encoding="utf-8")

    [problem] = changed_claims(before, book_claims(tmp_path, SERVICES))

    assert "by removing it" in problem.text


def test_a_blocker_whose_rerun_passes_is_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = record_blocker(_book(tmp_path), _blocker())
    asked = _rerun_with(monkeypatch, GateRerun(result=ExerciseResult(lines=("every scenario passed",), passed=True)))

    routed = settle_gate(tmp_path, tmp_path, SERVICES)

    assert asked == [(ADD,)]
    assert read_blockers(tmp_path) == ()
    assert routed == SERVICES
    assert take_failures(tmp_path, "tally") == {}


def test_a_book_blocker_whose_rerun_fails_hands_its_writer_the_new_result_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = record_blocker(_book(tmp_path), _blocker())
    failure = PageProblem(ADD, "adds: expected [201], observed 422")
    failed = ExerciseResult(lines=("scenario tally-add: failed",), summary=RunSummary(status="failed"))
    _ = _rerun_with(monkeypatch, GateRerun(result=failed, failures={ADD: (failure,)}))

    routed = settle_gate(tmp_path, tmp_path, SERVICES)

    assert routed == SERVICES
    assert take_failures(tmp_path, "tally") == {ADD: (failure,)}
    assert take_failures(tmp_path, "tally") == {}


def test_an_escalation_whose_rerun_still_fails_is_held_with_the_new_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = record_blocker(_book(tmp_path), _blocker(Side.APP, "app"))
    crashed = FailedCheck(label="adds", expected="[201]", actual="500", cause=Cause.APP, status="500", shape="POST /entries/…",
                          covers=(f"okf:{ADD}:contract",))
    summary = RunSummary(status="failed", scenarios={"tally-add": ScenarioOutcome(status="failed", failed_checks=(crashed,))},
                         signatures=(Signature(Cause.APP, "", "500", "POST /entries/…", 3, "adds: expected [201], observed 500"),))
    _ = _rerun_with(monkeypatch, GateRerun(result=ExerciseResult(lines=("scenario tally-add: failed",), summary=summary)))

    routed = settle_gate(tmp_path, tmp_path, SERVICES)

    [held] = read_blockers(tmp_path)
    assert routed == ()
    assert held.reason == "the gate's rerun still fails: 3 checks failed this way; for example adds: expected [201], observed 500"


def test_an_answer_that_changed_a_claim_routes_its_book_with_the_finding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_snapshot(tmp_path / GATE_DIR / SNAPSHOT_FOLDER, book_claims(_book(tmp_path), SERVICES))
    _ = (tmp_path / ADD).write_text(_endpoint(status="200"), encoding="utf-8")
    _ = (tmp_path / SIGNED_IN).write_text(_fixture(persistence="keeps a super admin"), encoding="utf-8")
    asked = _rerun_with(monkeypatch, GateRerun(result=ExerciseResult(lines=(), passed=True)))

    routed = settle_gate(tmp_path, tmp_path, SERVICES)

    [problem] = take_failures(tmp_path, "tally")[ADD]
    assert routed == SERVICES and asked == []
    assert "from `201` to `200`" in problem.text


def test_a_gate_left_only_with_escalations_reopens(tmp_path: Path) -> None:
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY,))
    _ = book.start()

    step = book.route_blocked(routed=())

    assert step.state == "report"


def test_a_book_the_gate_left_failures_for_goes_to_its_writer_with_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book = OkfBook(repo_dir=str(_book(tmp_path)), parent_records_dir=str(tmp_path), surfaces=(TALLY,))
    _ = book.start()
    _ = record_blocker(tmp_path, _blocker())
    failure = PageProblem(ADD, "adds: expected [201], observed 422")
    failed = ExerciseResult(lines=("scenario tally-add: failed",), summary=RunSummary(status="failed"))
    _ = _rerun_with(monkeypatch, GateRerun(result=failed, failures={ADD: (failure,)}))
    _ = settle_gate(tmp_path, tmp_path, SERVICES)

    step = book.route_book(index=0)

    assert step.state == "copy_source"
    assert step.params["run_failures"] == {ADD: (failure,)}
