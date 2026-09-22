"""The live-audit gate (`main/flow.py::semantic_audit`): what it repairs before it parks."""
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from workhorse.pyflow import Await, Continue
from workhorse_workflows.okf_builder.main import flow as main_flow
from workhorse_workflows.okf_builder.main.flow import MAX_GATE_GAPS, OkfBuilder

SERVICE = "acme"
BOOK = f"docs/features/{SERVICE}"
NODE = f"{BOOK}/billing.md#charge"
ROW = {"kind": "fix:unarranged-scenario", "target": f"{NODE}#unarranged-scenario"}


def _gap(n: int) -> dict[str, Any]:
    return {
        "obligation_id": f"okf:{NODE}:{n}",
        "kind": "unarranged-scenario",
        "detail": "no arrangement",
    }


def _report(gaps: list[dict[str, Any]], status: str = "blocked") -> dict[str, Any]:
    return {"spec_dir": f"{BOOK}/qa", "status": status, "gaps": tuple(gaps)}


class _Engine:
    """The three engine seams `semantic_audit` reaches through, and nothing else."""

    def __init__(self, reports: list[dict[str, Any]], added: int) -> None:
        self.logger = logging.getLogger("test")
        self.reports = reports
        self.added = added
        self.recorded: list[dict[str, Any]] = []

    def handoff(self, _wf: object, _args: object, _kwargs: object) -> dict[str, Any]:
        return {"reports": self.reports}

    def call(
        self, _node: object, args: tuple[Any, ...], _kwargs: dict[str, Any], **_extra: object
    ) -> SimpleNamespace:
        self.recorded = list(args[-1])
        return SimpleNamespace(added=self.added)


def _flow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    reports: list[dict[str, Any]],
    *,
    rows: list[dict[str, Any]],
    added: int,
) -> tuple[OkfBuilder, _Engine]:
    engine = _Engine(reports, added)
    flow = OkfBuilder(service=SERVICE)
    flow._engine = engine
    flow._ctx = SimpleNamespace(
        repo_root=str(tmp_path),
        features_root=str(tmp_path / BOOK),
        worklist_path=str(tmp_path / "worklist.json"),
        scope_id=SERVICE,
    )
    monkeypatch.setattr(main_flow, "audit_gap_items", lambda *_a, **_k: list(rows))
    return flow, engine


def test_reported_gaps_go_back_through_the_repair_drain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A gap the loop can queue is book debt, and the drain exists to pay it."""
    flow, engine = _flow(
        monkeypatch, tmp_path, [_report([_gap(1)])], rows=[ROW], added=1,
    )

    transition = flow.semantic_audit()

    assert isinstance(transition, Continue)
    assert transition.state == "select"
    assert engine.recorded == [ROW]


def test_a_gap_with_no_new_row_left_reaches_the_operator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`record` adding nothing means every row for these gaps is already blocked or exhausted."""
    flow, _ = _flow(
        monkeypatch, tmp_path, [_report([_gap(1)])], rows=[ROW], added=0,
    )

    transition = flow.semantic_audit()

    assert isinstance(transition, Await)
    assert transition.state == "semantic_audit"


def test_a_clear_audit_commits_the_book(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No gap, no failing scenario, nothing blocked: the book is executable."""
    flow, _ = _flow(
        monkeypatch, tmp_path, [_report([], status="ran")], rows=[], added=0,
    )

    transition = flow.semantic_audit()

    assert isinstance(transition, Continue)
    assert transition.state == "commit"


def test_the_gate_names_a_bounded_number_of_gaps() -> None:
    """The gate question is read by a person, and 19k enumerated obligations are not."""
    report = main_flow.LiveAuditReport.model_validate(
        _report([_gap(n) for n in range(MAX_GATE_GAPS + 20)])
    )

    message = main_flow._live_audit_gate_message([report])

    assert message.count("unarranged-scenario") == MAX_GATE_GAPS + 1
    assert "... and 20 more not listed here: 20 unarranged-scenario" in message


def test_the_elided_gaps_are_counted_by_kind() -> None:
    """The gate claims nothing about the worklist, so the tally is what survives truncation."""
    listed = [_gap(n) for n in range(MAX_GATE_GAPS)]
    elided = [{**_gap(n), "kind": "unstated-claim-combiner"} for n in range(5)]
    report = main_flow.LiveAuditReport.model_validate(_report([*listed, *elided]))

    message = main_flow._live_audit_gate_message([report])

    assert "... and 5 more not listed here: 5 unstated-claim-combiner" in message
    assert "carries every one" not in message
