"""The rework budgets, as span dimensions."""
from __future__ import annotations

from typing import ClassVar

from workhorse import otel
from workhorse.pyflow import Continue, Done, Workflow
from workhorse.pyflow.driver import drive
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.author.epic_edit.flow import EpicEdit
from workhorse_workflows.coder.shared.schemas.docs import (
    DocsLoop,
    DocsProgress,
    DocumentationFinding,
    DocumentationGate,
    DocumentationReview,
)
from workhorse_workflows.coder.shared.schemas.qa import (
    AssessmentRecord,
    AuditRecord,
    QaFlowResult,
    QaLoop,
)
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
        assessment=AssessmentRecord(disposition="repair_plan", failure_class="plan"),
    )
    labels = _sealed(Qa).state_labels({"loop": loop})
    assert labels["qa.assessment_disposition"] == "repair_plan"
    assert labels["qa.assessment_failure_class"] == "plan"
    assert "qa.audit_verdict" not in labels


def test_verdicts_are_forgotten_with_the_notes_they_summarise():
    """`cleared()` blanks each gate's findings before the plan is re-run."""
    loop = QaLoop(
        assessment=AssessmentRecord(
            disposition="repair_plan", notes="the plan does not test the story"
        ),
        audit=AuditRecord(verdict="refuted", refutation_class="plan-defect"),
        plan_rework=2,
        plan_validation_rework=1,
        docs_recheck_required=True,
    )
    cleared = loop.cleared()
    assert cleared.assessment.disposition == ""
    assert cleared.assessment.notes == ""
    assert cleared.audit.verdict == "" and cleared.audit.refutation_class == ""
    assert cleared.plan_rework == 2
    assert cleared.plan_rework_total == 3
    assert cleared.docs_recheck_required is True


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


def test_qa_reports_every_budget_on_its_loop():
    """The loop is a state parameter, so the counters are in hand with no state stashing a copy of them."""
    loop = QaLoop(plan_rework=2, plan_validation_rework=1, qa_rework=3)
    labels = _sealed(Qa).state_labels({"loop": loop})
    assert labels["work_id"] == "04-tabs"
    assert labels["qa.plan_rework"] == "2"
    assert labels["qa.plan_validation_rework"] == "1"
    assert labels["qa.plan_rework_total"] == "3"
    assert labels["qa.qa_rework"] == "3"
    assert labels["qa.setup_rework"] == "0"


def test_the_gate_verdict_is_forgotten_with_the_failures_it_summarises():
    """A passing gate clears the lane, verdict and baseline together."""
    progress = DocsProgress(gate_ids=["G:a.py::b"], gate_failures=1, gate_verdict="invalid")
    cleared = progress.after_gate(DocumentationGate(status="passed"))
    assert cleared.gate_ids == []
    assert cleared.gate_failures == 0
    assert cleared.gate_verdict == "passed"
    assert cleared.gate_progress_verdict == "cleared"


def test_only_a_revise_leaves_a_worklist_for_the_next_pass():
    """`approved` and `blocked` both end the flow, so neither leaves findings outstanding — even if the reviewer attached some to explain itself."""
    finding = DocumentationFinding(
        id="D1", kind="overclaim", target="docs/features/widget.md#links"
    )
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
    labels = _sealed(Docs).state_labels({"loop": DocsLoop(rework=2, progress=progress)})
    assert labels["work_id"] == "04-tabs"
    assert labels["docs.rework"] == "2"
    assert labels["docs.gate_verdict"] == "invalid"
    assert labels["docs.gate_failures"] == "2"
    assert labels["docs.gate_progress_verdict"] == "stalled"
    assert "docs.review_disposition" not in labels
    assert "docs.review_progress_verdict" not in labels


def test_every_docs_label_lands_in_a_groom_profile_bucket():
    """The test that keeps the feature from being vacuous."""
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
