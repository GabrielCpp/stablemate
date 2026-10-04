"""A failed lap goes to its lead before any page repair: only the groups it names the book's reach the writer, and the rest stop as blockers on the side it named."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter
from okf_book.main.tally import TALLY
from okf_book.support import ScriptedRunner, always, git
from ostler.qa.attribution import Cause, Signature
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import AgentTurnFailed, Continue
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main.lead_lap_flow import LeadLap
from workhorse_workflows.okf_book.main.nodes.lead_findings import LeadFinding, LedLap, read_findings
from workhorse_workflows.okf_book.shared.blockers import Side, read_blockers
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, ScenarioOutcome
from workhorse_workflows.okf_book.workflow import OkfBook, workflow

PAGE = "docs/features/tally/tally.md"
REFUSED = Signature(Cause.BOOK, "", "401", "POST /entries/…", 6, "adds: expected [201], observed 401")
CRASHED = Signature(Cause.APP, "", "500", "POST /entries/…", 2, "adds: expected [201], observed 500")


def _check(signature: Signature) -> FailedCheck:
    return FailedCheck(label="adds", expected="[201]", actual=signature.status, cause=signature.cause, status=signature.status,
                       shape=signature.shape, covers=(f"okf:{PAGE}#add:does:1",))


def _run(*signatures: Signature) -> ExerciseResult:
    outcome = ScenarioOutcome(status="failed", failed_checks=tuple(_check(signature) for signature in signatures))
    return ExerciseResult(lines=("scenario tally-add: failed",), summary=RunSummary(status="failed", scenarios={"tally-add": outcome}, signatures=signatures))


def _lead(tmp_path: Path, runner: ScriptedRunner, exercised: ExerciseResult) -> LedLap:
    writer = ArtifactWriter("okf-book", tmp_path / "runs", run_id=f"t{runner.total}")
    env = RunEnv(writer=writer, workflow_dir=Path(okf_book.__file__).parent, session_id_path=writer.run_dir / ".session_id",
                 config=RunConfig(), nodes=workflow.nodes, agent_runner=runner)
    repo = tmp_path / "repo"
    if not repo.is_dir():
        repo.mkdir()
        _ = git(repo, "init")
    flow = LeadLap(repo_dir=str(repo), parent_records_dir=str(tmp_path), service="tally", exercised=exercised)
    return LedLap.model_validate(drive(flow, env))


def _finding(signature: Signature, side: Side, instruction: str = "") -> LeadFinding:
    return LeadFinding(service="tally", lap=1, signature=signature.text(), count=signature.count, side=side,
                       evidence="spec/tally/qa_plan.py sends the request with no Authorization header", instruction=instruction, pages=(PAGE,))


def _book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *findings: LeadFinding) -> OkfBook:
    def _handoff(_self: OkfBook, _flow: object, **_params: object) -> LedLap:
        return LedLap(findings=findings)

    monkeypatch.setattr(OkfBook, "handoff", _handoff)
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY,))
    _ = book.start()
    return book


def _mapped(book: OkfBook, step: Continue[...]) -> Continue[...]:
    params: dict[str, object] = step.params
    index, exercised, repaired, lead = params["index"], params["exercised"], params["run_failures_repaired"], params["lead"]
    assert isinstance(index, int)
    assert isinstance(exercised, ExerciseResult)
    assert isinstance(repaired, bool)
    findings = LedLap.model_validate({"findings": lead}).findings
    return book.map_run_failures(index=index, exercised=exercised, run_failures_repaired=repaired, lead=findings)


def test_the_lead_is_shown_every_group_and_its_verdict_is_kept_for_the_next_lap(tmp_path: Path) -> None:
    runner = ScriptedRunner({"lead-lap": always({"findings": [
        {"group": 1, "side": "ostler", "evidence": "the plan drops the token the page arranges"},
        {"group": 2, "side": "app", "evidence": "api/entries.go panics on an empty body"},
        {"group": 7, "side": "book", "evidence": "no such group"},
    ]})})

    led = _lead(tmp_path, runner, _run(REFUSED, CRASHED))
    _ = _lead(tmp_path, runner, _run(REFUSED))

    assert [(finding.signature, finding.side, finding.pages) for finding in led.findings] == [
        ("book: POST /entries/… answered 401", Side.OSTLER, (PAGE,)),
        ("app: POST /entries/… answered 500", Side.APP, (PAGE,)),
    ]
    first, second = runner.args_of("lead-lap")
    assert first["groups"] == [
        {"number": 1, "text": "book: POST /entries/… answered 401", "cause": "book", "count": 6, "sample": REFUSED.sample, "pages": [PAGE]},
        {"number": 2, "text": "app: POST /entries/… answered 500", "cause": "app", "count": 2, "sample": CRASHED.sample, "pages": [PAGE]},
    ]
    assert first["earlier"] == []
    assert second["earlier"] == [finding.model_dump(mode="json") for finding in led.findings]
    assert len(read_findings(tmp_path)) == 3


def test_a_lead_turn_that_ends_without_a_verdict_names_nothing(tmp_path: Path) -> None:
    def _fails(_args: dict[str, object]) -> dict[str, object]:
        raise AgentTurnFailed("the model returned nothing")

    led = _lead(tmp_path, ScriptedRunner({"lead-lap": _fails}), _run(REFUSED))

    assert led == LedLap()
    assert read_findings(tmp_path) == ()


def test_a_group_the_lead_names_the_toolchain_s_is_a_blocker_and_never_reaches_the_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book = _book(tmp_path, monkeypatch, _finding(REFUSED, Side.OSTLER))

    step = book.lead_lap(index=0, exercised=_run(REFUSED))

    [blocker] = read_blockers(tmp_path)
    assert (blocker.side, blocker.pages) == (Side.OSTLER, (PAGE,))
    assert blocker.reason.endswith("the lead read the whole lap: spec/tally/qa_plan.py sends the request with no Authorization header")
    assert step.state == "map_run_failures"
    assert _mapped(book, step).state == "report"


def test_a_group_the_lead_names_the_book_s_reaches_the_writer_with_what_the_lead_said(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book = _book(tmp_path, monkeypatch, _finding(CRASHED, Side.BOOK, "send the body the handler requires: `amount` is missing"))
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=_run(CRASHED))

    step = book.lead_lap(index=0, exercised=_run(CRASHED))
    mapped = _mapped(book, step)

    assert read_blockers(tmp_path) == ()
    assert mapped.state == "copy_source"
    failures = TypeAdapter(dict[str, tuple[PageProblem, ...]]).validate_python(mapped.params["run_failures"])
    first = failures[PAGE][0]
    assert first.text == "the lead read the whole lap, and says of app: POST /entries/… answered 500: send the body the handler requires: `amount` is missing"


def test_a_lead_that_names_nothing_leaves_the_run_s_own_attribution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book = _book(tmp_path, monkeypatch)
    exercised = _run(REFUSED, CRASHED)
    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=exercised)

    step = book.lead_lap(index=0, exercised=exercised)

    assert [blocker.side for blocker in read_blockers(tmp_path)] == [Side.APP]
    assert _mapped(book, step).state == "copy_source"
