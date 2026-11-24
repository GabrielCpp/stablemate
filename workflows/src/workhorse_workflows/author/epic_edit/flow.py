"""Standalone reconciliation of one epic's scope, journeys, seeds, and stories."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed, dry_run
from workhorse_workflows.author.epic_edit.nodes import (
    apply_edit_plan,
    read_register_listing,
    select_affected_story,
    snapshot_epic,
    validate_applied_edit,
    validate_edit_plan,
    validate_epic_document,
)
from workhorse_workflows.author.draft import DraftLoop
from workhorse_workflows.author.pm import PMReview
from workhorse_workflows.author.shared.nodes import (
    commit_author,
    load_config,
    promote_record,
    validate_coverage,
    verify_integrity,
)
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.story_author.nodes import check_mockup_needed
from workhorse_workflows.author.story_split.nodes import derive_story_services
from workhorse_workflows.author.shared.schemas import (
    AppliedEpicEdit,
    Edit,
    EditIntent,
    EpicEditPlan,
    EpicRewriteResult,
    MockupResult,
    RunContext,
    StoryChoice,
)
from workhorse_workflows.kit.telemetry import counter_labels

MAX_REWORKS = 3


@dry_run(epic="dry-run", change="dry run")
class EpicEdit(Workflow):
    """Reconcile one epic after a direct scope change or a story-edit handoff."""

    epic: str = ""
    change: str = ""
    intent: EditIntent = EditIntent()
    force: bool = False
    operator_mode: str = "auto"

    def setup(self) -> RunContext:
        cfg = self.call(load_config, mode="epic-edit")
        return RunContext(**cfg.model_dump())

    def labels(self) -> dict[str, str]:
        return {"work_id": self.epic or self.intent.epic, "epic": self.epic or self.intent.epic}

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("reworks",)

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "epic_edit", self.BUDGET_LABELS)

    def _gate(self) -> Path:
        return Path(self.ctx.repo_root) / paths.author_context(self.ctx.repo_root)

    def _plan_detail(self, edit: Edit) -> str:
        return (
            f"## Intent\n\n{edit.intent.model_dump_json(indent=2)}\n\n"
            f"## Baseline\n\n{edit.snapshot.model_dump_json(indent=2)}\n\n"
            f"## Statically valid plan\n\n{edit.plan.model_dump_json(indent=2)}"
        )

    def _plan_args(self, edit: Edit, prior_plan: EpicEditPlan | None = None, findings: str = "") -> dict[str, object]:
        return {
            "intent": edit.intent,
            "snapshot": edit.snapshot,
            "prior_plan": prior_plan or EpicEditPlan(),
            "validation_findings": findings,
            "epic_dir": edit.snapshot.epic_dir,
            "register_listing": self.call(read_register_listing).text,
        }

    def start(self) -> Continue:
        intent = self.intent
        if not intent.epic:
            if not self.epic.strip() or not self.change.strip():
                raise WorkflowFailed(
                    "epic-edit needs both 'epic' and 'change'",
                    failure_class="epic-edit-missing-params",
                )
            intent = EditIntent(kind="epic", epic=self.epic, change=self.change, force=self.force)
        snapshot = self.call(snapshot_epic, intent.epic)
        return Continue(snapshot, self.plan_edit, edit=Edit(intent=intent, snapshot=snapshot)).because(
            "baseline taken"
        )

    def plan_edit(self, edit: Edit) -> Continue:
        plan = self.agent(
            "epic_edit/prompts/plan-epic-edit.md",
            returns=EpicEditPlan,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._plan_args(edit),
        )
        return Continue(plan, self.validate_plan, edit=edit.model_copy(update={"plan": plan})).because("planned")

    def validate_plan(self, edit: Edit, reworks: int = 0) -> Continue | Await:
        report = self.call(validate_edit_plan, edit.intent, edit.snapshot, edit.plan)
        if "[E_PLANNER_MUTATION]" in report.errors:
            raise WorkflowFailed(
                report.errors,
                failure_class="epic-edit-planner-mutation",
                artifacts={"epic_dir": str(edit.snapshot.epic_dir)},
            )
        if report.ok:
            return Continue(report, self.review_plan, edit=edit, reworks=reworks).because("the plan is valid")
        if reworks >= MAX_REWORKS:
            return Await(self._gate(), report.errors, self.plan_edit, edit=edit).because("out of plan reworks")
        return Continue(report, self.refine_plan, edit=edit, findings=report.errors, reworks=reworks).because(
            "the plan has findings"
        )

    def refine_plan(self, edit: Edit, findings: str, reworks: int = 0) -> Continue:
        revised = self.agent(
            "epic_edit/prompts/refine-epic-edit-plan.md",
            returns=EpicEditPlan,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._plan_args(edit, prior_plan=edit.plan, findings=findings),
        )
        return Continue(
            revised, self.validate_plan, edit=edit.model_copy(update={"plan": revised}), reworks=reworks + 1
        ).because("refined")

    def review_plan(self, edit: Edit, reworks: int = 0) -> Continue | Await:
        review = self.handoff(
            PMReview,
            stage="epic-edit-plan",
            subject=edit.snapshot.epic_dir,
            epic=edit.intent.epic,
            detail=self._plan_detail(edit),
        )
        if review.passed:
            return Continue(review, self.apply_plan, edit=edit).because("the PM passed the plan")
        if reworks < MAX_REWORKS:
            return Continue(review, self.refine_plan, edit=edit, findings=review.notes, reworks=reworks).because(
                "the PM has findings"
            )
        return Await(self._gate(), review.notes, self.plan_edit, edit=edit).because("out of plan reworks")

    def apply_plan(self, edit: Edit) -> Continue:
        applied = self.call(apply_edit_plan, edit.intent, edit.snapshot, edit.plan)
        report = self.call(validate_applied_edit, edit.snapshot, edit.plan, applied)
        if not report.ok:
            raise WorkflowFailed(
                f"epic edit application drifted from its plan:\n{report.errors}",
                failure_class="epic-edit-application-drift",
                artifacts={"epic_dir": str(edit.snapshot.epic_dir)},
            )
        edit = edit.model_copy(update={"applied": applied})
        if applied.deleted:
            return Continue(applied, self.finish, edit=edit).because("the epic was deleted")
        return Continue(applied, self.rewrite_epic, edit=edit).because("plan applied")

    def rewrite_epic(self, edit: Edit, findings: str = "", reworks: int = 0) -> Continue | Await:
        applied = edit.applied
        result = self.agent(
            "epic_edit/prompts/rewrite-epic-edit.md",
            returns=EpicRewriteResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "intent": edit.intent,
                "snapshot": edit.snapshot,
                "plan": edit.plan,
                "epic_dir": applied.epic_dir,
                "validation_findings": findings,
            },
        )
        report = self.call(validate_epic_document, applied.epic_dir)
        graph_report = self.call(validate_applied_edit, edit.snapshot, edit.plan, applied)
        if not graph_report.ok:
            raise WorkflowFailed(
                "epic prose rewrite changed the approved graph:\n" + graph_report.errors,
                failure_class="epic-edit-rewrite-graph-drift",
                artifacts={"epic_dir": str(applied.epic_dir)},
            )
        if result.status == "complete" and report.ok:
            return Continue(result, self.next_affected_story, edit=edit, index=0).because("the epic reads right")
        notes = result.notes if result.status == "blocked" else report.errors
        if reworks < MAX_REWORKS and result.status != "blocked":
            return Continue(report, self.rewrite_epic, edit=edit, findings=notes, reworks=reworks + 1).because(
                "the epic has findings"
            )
        return Await(self._gate(), notes, self.rewrite_epic, edit=edit, findings=notes, reworks=0).because(
            "blocked or out of reworks"
        )

    def next_affected_story(self, edit: Edit, index: int = 0) -> Continue:
        applied = edit.applied
        if index == 0:
            self.call(derive_story_services, applied.epic)
        pick = self.call(select_affected_story, applied.epic, applied.affected_stories, index)
        if not pick.has_story:
            return Continue(pick, self.check_coverage, edit=edit).because("no story left")
        return Continue(pick, self.design_mockup, edit=edit, pick=pick, index=index).because("a story to rewrite")

    def design_mockup(self, edit: Edit, pick: StoryChoice, index: int) -> Continue:
        if not self.call(check_mockup_needed, pick.story_id).required:
            return Continue(None, self.draft_story, edit=edit, pick=pick, index=index).because("no mockup needed")
        result = self.agent(
            "epic_edit/prompts/design-mockup.md",
            returns=MockupResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": edit.applied.epic,
                "story_slug": pick.story_slug,
                "story_id": pick.story_id,
                "story_dir": pick.story_dir,
                "epics_dir": self.ctx.epics_dir,
                "milestone_mockups_dir": self.ctx.milestone_mockups_dir,
            },
        )
        if result.status == "failed" or not result.mockup:
            raise WorkflowFailed(
                f"no mockup for story '{pick.story_slug}', which changes a UI service: "
                f"{result.notes or 'the mockup turn produced no mockup file'}",
                failure_class="epic-edit-mockup-missing",
                artifacts={"story_dir": str(pick.story_dir)},
            )
        return Continue(
            result, self.draft_story, edit=edit, pick=pick, index=index, mockup=result.mockup
        ).because("mockup drawn")

    def _story_args(self, applied: AppliedEpicEdit, pick: StoryChoice, mockup: str) -> dict[str, str]:
        return {
            "epic": applied.epic,
            "story_path": pick.story_path,
            "story_slug": pick.story_slug,
            "story_id": pick.story_id,
            "story_dir": pick.story_dir,
            "mockup_path": mockup,
            "ledger": self.ctx.pm_ledger,
        }

    def draft_story(self, edit: Edit, pick: StoryChoice, index: int, mockup: str = "") -> Continue | Await:
        """Rewrite one story the edit touched until the PM passes it, and ask the operator when it stays blocked."""
        applied = edit.applied
        spent = self.handoff(
            DraftLoop,
            kind="edited-story",
            subject=pick.story_path,
            epic=applied.epic,
            epic_dir=applied.epic_dir,
            story_dir=pick.story_dir,
            args={
                **self._story_args(applied, pick, mockup),
                "epic_edit": edit.intent.change,
                "operator_feedback": edit.intent.change,
            },
            max_answers=0,
        )
        if spent.status == "blocked":
            return Await(
                self._gate(), spent.notes, self.draft_story, edit=edit, pick=pick, index=index, mockup=mockup
            ).because("the story stayed blocked")
        return Continue(spent, self.next_affected_story, edit=edit, index=index + 1).because(
            "the PM passed the story"
        )

    def check_coverage(self, edit: Edit) -> Continue:
        applied = edit.applied
        report = self.call(validate_coverage, applied.epic_dir)
        if not report.ok:
            raise WorkflowFailed(
                f"epic edit broke story coverage:\n{report.errors}",
                failure_class="epic-edit-coverage-broken",
                artifacts={"epic_dir": str(applied.epic_dir)},
            )
        review = self.handoff(
            PMReview,
            stage="story-split",
            subject=applied.epic_dir,
            epic=applied.epic,
        )
        if not review.passed:
            raise WorkflowFailed(
                f"epic edit coverage review did not pass:\n{review.notes}",
                failure_class="epic-edit-coverage-review-failed",
                artifacts={"epic_dir": str(applied.epic_dir)},
            )
        return Continue(review, self.finish, edit=edit).because("coverage holds")

    def finish(self, edit: Edit) -> Done:
        intent, applied = edit.intent, edit.applied
        report = self.call(verify_integrity, "")
        if not report.holds and not report.skipped:
            self.call(
                commit_author, "incomplete", applied.slug or applied.epic, intent.change,
                _edited_milestone(edit),
            )
            raise WorkflowFailed(
                f"epic edit broke graph integrity:\n{report.errors}",
                failure_class="epic-edit-graph-integrity-broken",
                artifacts={"epic_dir": str(applied.epic_dir)},
            )
        if intent.kind == "add-story" and intent.record_id:
            self.call(promote_record, intent.record_id, intent.epic)
        self.call(
            commit_author, "epic-edit", applied.slug or applied.epic, intent.change,
            _edited_milestone(edit),
        )
        return Done(applied).because("edit committed")


def _edited_milestone(edit: Edit) -> str:
    return next((m.path for m in edit.snapshot.milestones if m.path), "")


__all__ = ["EpicEdit"]
