"""The rework budgets, as span dimensions."""
from __future__ import annotations

from typing import ClassVar

from workhorse import otel
from workhorse.pyflow import Continue, Done, Workflow
from workhorse.pyflow.driver import drive
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.author.epic_edit.flow import EpicEdit
from workhorse_workflows.coder.shared.schemas.qa import QaFlowResult
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import (
    counter_labels,
    progress_verdict,
    verdict_labels,
)


def test_counters_are_prefixed_and_stringified():
    labels = counter_labels({"rework": 2, "review_rework": 0}, "docs", ("rework", "review_rework"))
    assert labels == {"docs.rework": "2", "docs.review_rework": "0"}


def test_a_counter_the_state_does_not_carry_is_absent_not_zero():
    """`implement` has no repair-lap parameter, so it has no opinion about that budget."""
    labels = counter_labels({"plan_rework": 1}, "dev", ("plan_rework", "fix_lap"))
    assert labels == {"dev.plan_rework": "1"}


def test_a_bool_is_not_an_attempt_count():
    """`bool` is an `int` subclass in Python, and a state can carry flags beside counters."""
    assert counter_labels({"bonus_used": True}, "qa", ("bonus_used",)) == {}


def test_missing_documentation_taint_fails_closed():
    assert QaFlowResult(status="passed").docs_recheck_required is True


def test_verdicts_skip_the_gate_that_has_not_run():
    """Blank means "has not spoken", which is distinct from "found nothing wrong"."""
    source = {"audit_verdict": "refuted", "assessment_disposition": ""}
    labels = verdict_labels(source, "qa", ("audit_verdict", "assessment_disposition"))
    assert labels == {"qa.audit_verdict": "refuted"}


def test_epic_edit_reports_reworks_and_omits_defaulted_absent_counters():
    flow = EpicEdit(epic="accounts")
    assert flow.state_labels({"reworks": 2}) == {
        "work_id": "accounts",
        "epic": "accounts",
        "epic_edit.reworks": "2",
    }
    assert "epic_edit.reworks" not in flow.state_labels({})


def test_progress_verdict_names_what_a_pass_bought():
    """The six outcomes, as a table."""
    cases = [
        (None, ["D1"], "first_pass"),
        (["D1", "D2"], [], "cleared"),
        (None, [], "cleared"),
        (["D1", "D2"], ["D1"], "reduced"),
        (["D1"], ["D1", "D2"], "regressed"),
        (["D1", "D2"], ["D1", "D2"], "stalled"),
        (["D1", "D2"], ["D3", "D4"], "churned"),
    ]
    for previous, current, expected in cases:
        assert progress_verdict(previous, current) == expected, (previous, current)


def test_a_pass_that_closed_two_and_opened_two_is_not_a_stall():
    """`churned` is deliberately distinct from `stalled`, and this is the whole reason the helper compares identities rather than counts."""
    assert progress_verdict(["D1", "D2"], ["D3", "D4"]) == "churned"
    assert progress_verdict(["D1", "D2"], ["D1", "D2"]) == "stalled"


def test_an_empty_baseline_is_a_first_pass_not_a_reduction():
    """A lane that has never failed carries no ids, and must not read as "had zero findings, now has two, therefore regressed"."""
    assert progress_verdict(None, ["G:a.py::b"]) == "first_pass"
    assert progress_verdict([], ["G:a.py::b"]) == "first_pass"


def _sealed(cls: type[Workflow], slug: str = "04-tabs") -> Workflow:
    """A flow with `ctx` in place, as the driver leaves it after `setup()`."""
    flow = cls()
    flow._seal(StoryPaths(story_slug=slug))
    return flow


def test_qa_reports_its_repair_laps_and_its_blocks():
    """The owner's budgets are state parameters, so they land on the span as counters."""
    labels = _sealed(Qa).state_labels({"laps": 2, "blocks": 1, "report": "a note"})
    assert labels == {"work_id": "04-tabs", "qa.laps": "2", "qa.blocks": "1"}


def test_docs_reports_its_repair_laps_and_its_blocks():
    """The owner's budgets are state parameters, so they land on the span as counters."""
    labels = _sealed(Docs).state_labels({"laps": 2, "blocks": 1, "report": "a note"})
    assert labels == {"work_id": "04-tabs", "docs.laps": "2", "docs.blocks": "1"}


def test_a_state_with_no_loop_yet_reports_only_the_base_labels():
    """`start` runs before any lap, and must not invent counters for it."""
    assert _sealed(Qa).state_labels({}) == {"work_id": "04-tabs"}
    assert _sealed(Docs).state_labels({}) == {"work_id": "04-tabs"}


class _Recording(otel._NullTelemetry):
    """Records what the driver published, inert for every other signal."""

    def __init__(self) -> None:
        self.labels: list[dict[str, str]] = []

    def set_labels(self, labels: dict[str, str]) -> None:
        self.labels.append(dict(labels))


def test_labels_reach_telemetry_across_a_rework_loop(env):
    """The counter must climb on the spans, not just in the checkpoint."""

    class Loops(Workflow):
        BUDGET: ClassVar[tuple[str, ...]] = ("rework",)

        def state_labels(self, params: dict) -> dict[str, str]:
            return counter_labels(params, "loop", self.BUDGET)

        def start(self) -> Continue:
            return Continue(None, self.work, rework=0)

        def work(self, rework: int = 0) -> Continue | Done:
            if rework < 2:
                return Continue(None, self.work, rework=rework + 1)
            return Done("done")

    recorder = _Recording()
    previous = otel.install(otel.TelemetryHost(active=recorder))
    try:
        assert drive(Loops(), env()) == "done"
    finally:
        otel.install(previous)

    assert [labels.get("loop.rework") for labels in recorder.labels] == [None, "0", "1", "2"]
