"""A run probes the book's preconditions before the book, runs its journeys before its pages, and fails on a port the app called that no runbook starts."""
from __future__ import annotations

from pathlib import Path

import pytest

from ostler.qa.attribution import Cause, Signature
from ostler.qa.verdict import Verdict
from workhorse_workflows.okf_book.shared import book_run
from workhorse_workflows.okf_book.shared.book_run import StackReadiness, run_plan
from workhorse_workflows.okf_book.shared.local_calls import Runbook
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, Scenario, ScenarioOutcome

SERVING = StackReadiness(up=True, serving=True, notes="")


def _probed(monkeypatch: pytest.MonkeyPatch, probe_cause: Cause | None, gap: str = "", *more: str) -> list[tuple[str, ...]]:
    """Run a plan of one probe, one book page and *more* scenarios, whose probe fails with *probe_cause*, and record what each run was asked for."""
    plan = (Scenario(id="probe-signed-in-editor", covers=("okf:docs/a.md#get:does:1",)),
            Scenario(id="docs-a-from-the-book", covers=("okf:docs/a.md#get:does:1",)), *(Scenario(id=name) for name in more))
    asked: list[tuple[str, ...]] = []

    def _plan_scenarios(*_args: object) -> tuple[tuple[Scenario, ...], tuple[str, ...]]:
        return plan, ()

    def _run_scenarios(_root: Path, _spec: Path, only: tuple[str, ...], _lap: Path, _check: object = None) -> RunSummary:
        asked.append(tuple(only))
        if probe_cause is None or tuple(only) != ("probe-signed-in-editor",):
            return RunSummary(status="passed", scenarios={name: ScenarioOutcome(status="passed") for name in only})
        refused = Signature(probe_cause, "docs/fixtures/signed-in-editor.md", "403", "GET /api/things", 1, "GET /api/things answers [200]", gap)
        return RunSummary(status="failed", signatures=(refused,),
                          scenarios={"probe-signed-in-editor": ScenarioOutcome(status="failed", assertions=1, failures=1)})

    monkeypatch.setattr(book_run, "plan_scenarios", _plan_scenarios)
    monkeypatch.setattr(book_run, "run_scenarios", _run_scenarios)
    return asked


def test_a_precondition_whose_probe_is_refused_stops_the_run_before_the_book(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked = _probed(monkeypatch, Cause.ARRANGEMENT)

    result = run_plan(tmp_path, tmp_path / "spec", (), SERVING)

    assert asked == [("probe-signed-in-editor",)]
    assert result.lines[0] == "problem: a precondition probe failed, so the book did not run"
    assert result.summary is not None
    assert list(result.summary.failures_by_page(())) == ["docs/fixtures/signed-in-editor.md"]


def test_the_probes_and_the_book_run_in_one_lap_that_ends_with_the_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ = _probed(monkeypatch, None)
    laps: list[Path] = []
    probing = book_run.run_scenarios

    def _run_scenarios(root: Path, spec: Path, only: tuple[str, ...], lap: Path, _check: object = None) -> RunSummary:
        laps.append(lap)
        _ = (lap / "arranged.json").write_text("{}", encoding="utf-8")
        return probing(root, spec, only, lap)

    monkeypatch.setattr(book_run, "run_scenarios", _run_scenarios)

    _ = run_plan(tmp_path, tmp_path / "spec", (), SERVING)

    assert len(laps) == 2
    assert laps[0] == laps[1]
    assert not laps[0].exists()


def test_probes_that_pass_let_the_book_run_without_them(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked = _probed(monkeypatch, None)

    result = run_plan(tmp_path, tmp_path / "spec", (), SERVING)

    assert asked == [("probe-signed-in-editor",), ("docs-a-from-the-book",)]
    assert result.passed


def test_the_book_runs_its_journeys_before_its_pages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked = _probed(monkeypatch, None, "", "docs-flows-edit-journey", "docs-b-from-the-book")
    _ = run_plan(tmp_path, tmp_path / "spec", (), SERVING)

    assert asked[-1] == ("docs-flows-edit-journey", "docs-a-from-the-book", "docs-b-from-the-book")


class _CalledAnApi:
    def __init__(self, runbooks: tuple[Runbook, ...]) -> None:
        self.runbooks = runbooks

    def __enter__(self) -> _CalledAnApi:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def unstarted(self) -> tuple[str, ...]:
        return ("the app called localhost:8080",) if self.runbooks else ()


def test_a_passing_run_whose_app_called_a_port_no_runbook_starts_fails_on_that_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ = _probed(monkeypatch, None)
    monkeypatch.setattr(book_run, "CallWatch", _CalledAnApi)

    dev = StackReadiness(up=True, serving=True, notes="", runbooks=(Runbook("docs/features/web-app/ops/dev.md", frozenset({5173})),))

    result = run_plan(tmp_path, tmp_path / "spec", (), dev)

    assert (result.passed, result.unstarted, result.lines[0]) == (
        False, ("the app called localhost:8080",), "problem: the app called localhost:8080")
    assert run_plan(tmp_path, tmp_path / "spec", (), SERVING).passed


def test_a_probe_the_app_fails_leaves_the_book_to_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked = _probed(monkeypatch, Cause.APP)

    _ = run_plan(tmp_path, tmp_path / "spec", (), SERVING)

    assert asked[-1] == ("docs-a-from-the-book",)


def test_a_probe_that_finds_a_capability_absent_leaves_the_book_to_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked = _probed(monkeypatch, Cause.ENVIRONMENT, gap="payment provider")

    _ = run_plan(tmp_path, tmp_path / "spec", (), SERVING)

    assert asked[-1] == ("docs-a-from-the-book",)


def test_a_gapped_claim_reads_as_the_capability_the_stack_lacks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    claim = "okf:docs/billing.md#charge:does:1"
    check = FailedCheck(label="a charge", covers=(claim,), cause=Cause.ENVIRONMENT, gap="payment provider")
    summary = RunSummary(status="failed", verdicts={claim: Verdict.GAPPED},
                         scenarios={"charge": ScenarioOutcome(status="failed", assertions=1, failures=1, failed_checks=(check,))})

    def _run_scenarios(*_args: object) -> RunSummary:
        return summary

    monkeypatch.setattr(book_run, "run_scenarios", _run_scenarios)

    result = run_plan(tmp_path, tmp_path / "spec", (), SERVING, only=("charge",))

    assert f"claim {claim}: gapped: payment provider absent" in result.lines
    assert not result.passed


def test_a_run_of_named_scenarios_probes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asked = _probed(monkeypatch, Cause.ARRANGEMENT)

    _ = run_plan(tmp_path, tmp_path / "spec", (), SERVING, only=("docs-a-from-the-book",))

    assert asked == [("docs-a-from-the-book",)]
