"""The rework budgets, as span dimensions.

`kit/telemetry.py` is pure shaping over a state's bound parameters, so these are unit
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
from workhorse_workflows.author.epic_edit.flow import EpicEdit
from workhorse_workflows.coder.shared.schemas.docs import (
    DocsProgress,
    DocumentationFinding,
    DocumentationGate,
    DocumentationReview,
)
from workhorse_workflows.coder.shared.schemas.qa import QaFlowResult, QaLoop
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


def test_a_recorded_verdict_reaches_the_labels():
    loop = QaLoop(
        assessment_disposition="repair_plan",
        assessment_failure_class="plan",
    )
    labels = _sealed(Qa).state_labels({"loop": loop})
    assert labels["qa.assessment_disposition"] == "repair_plan"
    assert labels["qa.assessment_failure_class"] == "plan"
    # The audit has not run, so it says nothing rather than claiming a verdict.
    assert "qa.audit_verdict" not in labels


def test_verdicts_are_forgotten_with_the_notes_they_summarise():
    """`cleared()` blanks each gate's findings before the plan is re-run. A verdict left
    behind would let a span claim `revise` for a finding already forgotten — the two are
    the same statement in two forms."""
    loop = QaLoop(
        assessment_disposition="repair_plan",
        assessment_notes="the plan does not test the story",
        audit_verdict="refuted",
        audit_refutation_class="plan-defect",
        # A budget is not a finding: `cleared` must not reset the counters, or the loop
        # it bounds would never end.
        plan_rework=2,
        plan_validation_rework=1,
        docs_recheck_required=True,
    )
    cleared = loop.cleared()
    assert cleared.assessment_disposition == ""
    assert cleared.assessment_notes == ""
    assert cleared.audit_verdict == "" and cleared.audit_refutation_class == ""
    assert cleared.plan_rework == 2
    assert cleared.plan_rework_total == 3
    assert cleared.docs_recheck_required is True


def test_progress_verdict_names_what_a_pass_bought():
    """The six outcomes, as a table. The vocabulary is closed on purpose: it becomes a
    span-attribute value, and an open one turns a group-by into a list of singletons."""
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
    """`churned` is deliberately distinct from `stalled`, and this is the whole reason the
    helper compares identities rather than counts.

    The repair-pass contract requires the author to retain stable finding ids, so a
    changed id set is evidence the previous worklist *was* closed and new defects were
    found. That wants a larger budget. `stalled` — the same findings handed back a second
    time — wants a prompt repair instead. Collapsing them into one word erases the only
    distinction the label exists to draw.
    """
    assert progress_verdict(["D1", "D2"], ["D3", "D4"]) == "churned"
    assert progress_verdict(["D1", "D2"], ["D1", "D2"]) == "stalled"


def test_an_empty_baseline_is_a_first_pass_not_a_reduction():
    """A lane that has never failed carries no ids, and must not read as "had zero
    findings, now has two, therefore regressed"."""
    assert progress_verdict(None, ["G:a.py::b"]) == "first_pass"
    assert progress_verdict([], ["G:a.py::b"]) == "first_pass"


def _sealed(cls: type[Workflow], slug: str = "04-tabs") -> Workflow:
    """A flow with `ctx` in place, as the driver leaves it after `setup()`."""
    flow = cls()
    flow._seal(StoryPaths(story_slug=slug))
    return flow


def test_qa_reports_every_budget_on_its_loop():
    """The loop is a state parameter, so the counters are in hand with no state stashing
    a copy of them."""
    loop = QaLoop(plan_rework=2, plan_validation_rework=1, qa_rework=3)
    labels = _sealed(Qa).state_labels({"loop": loop})
    assert labels["work_id"] == "04-tabs"
    assert labels["qa.plan_rework"] == "2"
    assert labels["qa.plan_validation_rework"] == "1"
    assert labels["qa.plan_rework_total"] == "3"
    assert labels["qa.qa_rework"] == "3"
    # Every budget is reported, including the ones still at zero — the loop carries them
    # all, so "this story has not spent its setup budget" is a fact, not an absence.
    assert labels["qa.setup_rework"] == "0"


def test_the_gate_verdict_is_forgotten_with_the_failures_it_summarises():
    """A passing gate clears the lane, verdict and baseline together.

    The direct analogue of `test_verdicts_are_forgotten_with_the_notes_they_summarise`: a
    verdict left behind after its findings were closed would let a later span claim a
    failure that no longer exists, and would make the *next* failure read as `stalled`
    against a baseline that had already been satisfied.
    """
    progress = DocsProgress(gate_ids=["G:a.py::b"], gate_failures=1, gate_verdict="invalid")
    cleared = progress.after_gate(DocumentationGate(status="passed"))
    assert cleared.gate_ids == []
    assert cleared.gate_failures == 0
    assert cleared.gate_verdict == "passed"
    assert cleared.gate_progress_verdict == "cleared"


def test_only_a_revise_leaves_a_worklist_for_the_next_pass():
    """`approved` and `blocked` both end the flow, so neither leaves findings outstanding —
    even if the reviewer attached some to explain itself."""
    finding = DocumentationFinding(id="D1", target="docs/features/widget.md#links")
    revised = DocsProgress().after_review(
        DocumentationReview(status="revise", findings=[finding])
    )
    assert revised.review_ids == ["D1"] and revised.review_findings == 1
    approved = revised.after_review(
        DocumentationReview(status="approved", findings=[finding])
    )
    assert approved.review_ids == [] and approved.review_progress_verdict == "cleared"


def test_docs_reports_its_gates_and_whether_the_rework_bought_anything():
    progress = DocsProgress(
        gate_verdict="invalid",
        gate_failures=2,
        gate_progress_verdict="stalled",
    )
    labels = _sealed(Docs).state_labels({"rework": 2, "progress": progress})
    assert labels["work_id"] == "04-tabs"
    assert labels["docs.rework"] == "2"
    assert labels["docs.gate_verdict"] == "invalid"
    assert labels["docs.gate_failures"] == "2"
    assert labels["docs.gate_progress_verdict"] == "stalled"
    # The reviewer has not spoken, so it claims no verdict — and unlike the gate's counts,
    # a lane that never ran reports no zero either.
    assert "docs.review_disposition" not in labels
    assert "docs.review_progress_verdict" not in labels


def test_every_docs_label_lands_in_a_groom_profile_bucket():
    """The test that keeps the feature from being vacuous.

    `groom profile` renders exactly two kinds of span dimension and derives both from the
    attribute itself: a *verdict* group is named with one of the suffixes below, and an
    *attempt* group is a dotted name whose value is a canonical non-negative integer.
    Anything else — `docs.loop_productive="yes"`, say — is stored and rendered nowhere, and
    nothing would report the omission. `workflows` does not depend on `groom`, so the
    suffixes are duplicated here rather than imported; the source is
    `groom/groom/store.py::_VERDICT_SUFFIXES`, and this fails loudly if either side moves.
    """
    suffixes = ("_verdict", "_disposition", "_failure_class", "_refutation_class")
    for name in DocsProgress.VERDICT_LABELS:
        assert name.endswith(suffixes), name

    counts = counter_labels(
        DocsProgress(gate_failures=2, review_findings=0).model_dump(),
        "docs",
        DocsProgress.COUNT_LABELS,
    )
    assert set(counts) == {"docs.gate_failures", "docs.review_findings"}
    for name, value in counts.items():
        assert "." in name and not name.startswith("workhorse."), name
        assert value.isdigit() and str(int(value)) == value, (name, value)


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
