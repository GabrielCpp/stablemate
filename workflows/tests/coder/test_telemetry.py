"""The rework budgets, as span dimensions.

`shared/telemetry.py` is pure shaping over a state's bound parameters, so these are unit
tests over dicts. What they pin is the two rules that decide whether an aggregate over a
real run is readable: a counter the current state does not carry must be *absent* rather
than zero, and a bool must never be mistaken for an attempt count.

The end-to-end half — that these reach a span at all — is `test_labels_reach_telemetry`
below, which drives a real flow through a real rework loop.
"""
from __future__ import annotations

from typing import ClassVar

from workhorse import otel
from workhorse.pyflow import Continue, Done, Workflow
from workhorse.pyflow.driver import drive
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.shared.schemas.qa import QaFlowResult, QaLoop
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.coder.shared.telemetry import counter_labels, verdict_labels


def test_counters_are_prefixed_and_stringified():
    labels = counter_labels({"rework": 2, "review_rework": 0}, "docs", ("rework", "review_rework"))
    assert labels == {"docs.rework": "2", "docs.review_rework": "0"}


def test_a_counter_the_state_does_not_carry_is_absent_not_zero():
    """`implement` has no reuse budget parameter, so it has no opinion about that budget.

    Stamping a zero would read as "first attempt" on every span of every state that never
    sees the counter, which is a wrong answer rather than a missing one — and it would put
    those spans in the attempt-0 bucket of any group-by.
    """
    labels = counter_labels({"plan_rework": 1}, "dev", ("plan_rework", "reuse_rework"))
    assert labels == {"dev.plan_rework": "1"}


def test_a_bool_is_not_an_attempt_count():
    """`bool` is an `int` subclass in Python, and `QaLoop` carries flags beside counters."""
    assert counter_labels({"bonus_used": True}, "qa", ("bonus_used",)) == {}


def test_missing_documentation_taint_fails_closed():
    assert QaLoop().docs_recheck_required is True
    assert QaFlowResult(status="passed").docs_recheck_required is True


def test_verdicts_skip_the_gate_that_has_not_run():
    """Blank means "has not spoken", which is distinct from "found nothing wrong"."""
    source = {"audit_verdict": "refuted", "plan_review_disposition": ""}
    labels = verdict_labels(source, "qa", ("audit_verdict", "plan_review_disposition"))
    assert labels == {"qa.audit_verdict": "refuted"}


def test_a_recorded_verdict_reaches_the_labels():
    loop = QaLoop(
        plan_review_disposition="revise",
        assessment_disposition="repair_plan",
        assessment_failure_class="plan",
    )
    labels = _sealed(Qa).state_labels({"loop": loop})
    assert labels["qa.plan_review_disposition"] == "revise"
    assert labels["qa.assessment_disposition"] == "repair_plan"
    assert labels["qa.assessment_failure_class"] == "plan"
    # The audit has not run, so it says nothing rather than claiming a verdict.
    assert "qa.audit_verdict" not in labels


def test_verdicts_are_forgotten_with_the_notes_they_summarise():
    """`cleared()` blanks each gate's findings before the plan is re-run. A verdict left
    behind would let a span claim `revise` for a finding already forgotten — the two are
    the same statement in two forms."""
    loop = QaLoop(
        plan_review_disposition="revise",
        plan_review_notes="the plan does not test the story",
        audit_verdict="refuted",
        audit_refutation_class="plan-defect",
        # A budget is not a finding: `cleared` must not reset the counters, or the loop
        # it bounds would never end.
        plan_rework=2,
        plan_validation_rework=1,
        docs_recheck_required=True,
    )
    cleared = loop.cleared()
    assert cleared.plan_review_disposition == ""
    assert cleared.plan_review_notes == ""
    assert cleared.audit_verdict == "" and cleared.audit_refutation_class == ""
    assert cleared.plan_rework == 2
    assert cleared.plan_rework_total == 3
    assert cleared.docs_recheck_required is True


def _sealed(cls: type[Workflow], slug: str = "04-tabs") -> Workflow:
    """A flow with `ctx` in place, as the driver leaves it after `setup()`."""
    flow = cls()
    flow._seal(StoryPaths(story_slug=slug))
    return flow


def test_qa_reports_every_budget_on_its_loop():
    """The loop is a state parameter, so the counters are in hand with no state stashing
    a copy of them."""
    loop = QaLoop(plan_rework=2, plan_review_rework=1, qa_rework=3)
    labels = _sealed(Qa).state_labels({"loop": loop})
    assert labels["work_id"] == "04-tabs"
    assert labels["qa.plan_rework"] == "2"
    assert labels["qa.plan_review_rework"] == "1"
    assert labels["qa.plan_rework_total"] == "3"
    assert labels["qa.qa_rework"] == "3"
    # Every budget is reported, including the ones still at zero — the loop carries them
    # all, so "this story has not spent its setup budget" is a fact, not an absence.
    assert labels["qa.setup_rework"] == "0"


def test_a_state_with_no_loop_yet_reports_only_the_base_labels():
    """`start` runs before any loop exists, and must not invent counters for it."""
    assert _sealed(Qa).state_labels({}) == {"work_id": "04-tabs"}
    assert _sealed(Docs).state_labels({}) == {"work_id": "04-tabs"}


class _Recording(otel._NullTelemetry):
    """Records what the driver published, inert for every other signal.

    Subclasses the null adapter — as `workhorse/tests/_fakes.py` does — so a signal this
    test does not exercise stays a no-op rather than needing a stub.
    """

    def __init__(self) -> None:
        self.labels: list[dict[str, str]] = []

    def set_labels(self, labels: dict[str, str]) -> None:
        self.labels.append(dict(labels))


def test_labels_reach_telemetry_across_a_rework_loop(env):
    """The counter must climb on the spans, not just in the checkpoint.

    A label is stamped on every span opened while it is current, which is what lets a
    query group cost by attempt number. This drives a flow that reworks twice and asserts
    the driver published a distinct counter for each pass.
    """

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
