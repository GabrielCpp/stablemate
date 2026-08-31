"""Standalone reconciliation of one epic's scope, journeys, seeds, and stories."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.author.epic_edit.nodes import (
    apply_edit_plan,
    select_affected_story,
    snapshot_epic,
    validate_applied_edit,
    validate_edit_plan,
    validate_epic_document,
)
from workhorse_workflows.author.main.nodes import (
    branch_author,
    check_story_grounding,
    commit_author,
    load_config,
    prune_bullet,
    record_attempt,
    validate_coverage,
    validate_story,
    verify_integrity,
)
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.schemas import (
    AppliedEpicEdit,
    AuditResult,
    CoverageReview,
    Defects,
    EditIntent,
    EpicEditPlan,
    EpicEditReview,
    EpicRewriteResult,
    EpicSnapshot,
    MockupResult,
    RunContext,
    StoryChoice,
    WriteStoryResult,
)
from workhorse_workflows.kit.telemetry import counter_labels

MAX_REWORKS = 3


class EpicEdit(Workflow):
    """Reconcile one epic after a direct scope change or a story-edit handoff."""

    epic: str = ""
    change: str = ""
    intent: EditIntent = EditIntent()
    force: bool = False
    operator_mode: str = "auto"
    branch_run_dir: str = ""

    def setup(self) -> RunContext:
        cfg = self.call(load_config, mode="epic-edit")
        branches = self.call(
            branch_author,
            self.branch_run_dir or str(self.run_dir),
            "epic-edit",
        )
        return RunContext(
            **cfg.model_dump(),
            base_branch=branches.base_branch,
            author_branch=branches.author_branch,
        )

    def labels(self) -> dict[str, str]:
        return {"work_id": self.epic or self.intent.epic, "epic": self.epic or self.intent.epic}

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("reworks",)

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "epic_edit", self.BUDGET_LABELS)

    def _abs(self, rel: str) -> Path:
        return Path(self.ctx.repo_root) / rel

    def _plan_args(
        self,
        intent: EditIntent,
        snapshot: EpicSnapshot,
        prior_plan: EpicEditPlan | None = None,
        findings: str = "",
    ) -> dict[str, object]:
        return {
            "intent": intent,
            "snapshot": snapshot,
            "prior_plan": prior_plan or EpicEditPlan(),
            "validation_findings": findings,
            "epic_dir": snapshot.epic_dir,
            "backlog": self.ctx.backlog_path,
            "features_dir": self.ctx.features_dir,
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
        return Continue(snapshot, self.plan_edit, intent=intent, snapshot=snapshot)

    def plan_edit(self, intent: EditIntent, snapshot: EpicSnapshot) -> Continue:
        plan = self.agent(
            "epic_edit/prompts/plan-epic-edit.md",
            returns=EpicEditPlan,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._plan_args(intent, snapshot),
        )
        return Continue(plan, self.validate_plan, intent=intent, snapshot=snapshot, plan=plan)

    def validate_plan(
        self,
        intent: EditIntent,
        snapshot: EpicSnapshot,
        plan: EpicEditPlan,
        reworks: int = 0,
    ) -> Continue | Await:
        report = self.call(validate_edit_plan, intent, snapshot, plan)
        if "[E_PLANNER_MUTATION]" in report.errors:
            raise WorkflowFailed(
                report.errors,
                failure_class="epic-edit-planner-mutation",
                artifacts={"epic_dir": str(snapshot.epic_dir)},
            )
        if report.ok:
            return Continue(
                report,
                self.review_plan,
                intent=intent,
                snapshot=snapshot,
                plan=plan,
                reworks=reworks,
            )
        if reworks >= MAX_REWORKS:
            context = paths.epic_context(snapshot.epic_dir)
            return Await(
                self._abs(context),
                report.errors,
                self.plan_edit,
                intent=intent,
                snapshot=snapshot,
            )
        return Continue(
            report,
            self.refine_plan,
            intent=intent,
            snapshot=snapshot,
            plan=plan,
            findings=report.errors,
            reworks=reworks,
        )

    def refine_plan(
        self,
        intent: EditIntent,
        snapshot: EpicSnapshot,
        plan: EpicEditPlan,
        findings: str,
        reworks: int = 0,
    ) -> Continue:
        revised = self.agent(
            "epic_edit/prompts/refine-epic-edit-plan.md",
            returns=EpicEditPlan,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._plan_args(
                intent,
                snapshot,
                prior_plan=plan,
                findings=findings,
            ),
        )
        return Continue(
            revised,
            self.validate_plan,
            intent=intent,
            snapshot=snapshot,
            plan=revised,
            reworks=reworks + 1,
        )

    def review_plan(
        self,
        intent: EditIntent,
        snapshot: EpicSnapshot,
        plan: EpicEditPlan,
        reworks: int = 0,
    ) -> Continue | Await:
        review = self.agent(
            "epic_edit/prompts/review-epic-edit-plan.md",
            returns=EpicEditReview,
            power="high",
            cwd=self.ctx.repo_root,
            args={"intent": intent, "snapshot": snapshot, "plan": plan},
        )
        if review.status == "approved":
            return Continue(review, self.apply_plan, intent=intent, snapshot=snapshot, plan=plan)
        if review.status == "needs_rework" and reworks < MAX_REWORKS:
            return Continue(
                review,
                self.refine_plan,
                intent=intent,
                snapshot=snapshot,
                plan=plan,
                findings=review.notes,
                reworks=reworks,
            )
        context = paths.epic_context(snapshot.epic_dir)
        return Await(
            self._abs(context),
            review.notes,
            self.plan_edit,
            intent=intent,
            snapshot=snapshot,
        )

    def apply_plan(
        self,
        intent: EditIntent,
        snapshot: EpicSnapshot,
        plan: EpicEditPlan,
    ) -> Continue:
        applied = self.call(apply_edit_plan, intent, snapshot, plan)
        report = self.call(validate_applied_edit, snapshot, plan, applied)
        if not report.ok:
            raise WorkflowFailed(
                f"epic edit application drifted from its plan:\n{report.errors}",
                failure_class="epic-edit-application-drift",
                artifacts={"epic_dir": str(snapshot.epic_dir)},
            )
        if applied.deleted:
            return Continue(applied, self.finish, intent=intent, applied=applied)
        return Continue(
            applied,
            self.rewrite_epic,
            intent=intent,
            snapshot=snapshot,
            plan=plan,
            applied=applied,
        )

    def rewrite_epic(
        self,
        intent: EditIntent,
        snapshot: EpicSnapshot,
        plan: EpicEditPlan,
        applied: AppliedEpicEdit,
        findings: str = "",
        reworks: int = 0,
    ) -> Continue | Await:
        result = self.agent(
            "epic_edit/prompts/rewrite-epic-edit.md",
            returns=EpicRewriteResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "intent": intent,
                "snapshot": snapshot,
                "plan": plan,
                "epic_dir": applied.epic_dir,
                "validation_findings": findings,
            },
        )
        report = self.call(validate_epic_document, applied.epic_dir)
        graph_report = self.call(validate_applied_edit, snapshot, plan, applied)
        if not graph_report.ok:
            raise WorkflowFailed(
                "epic prose rewrite changed the approved graph:\n" + graph_report.errors,
                failure_class="epic-edit-rewrite-graph-drift",
                artifacts={"epic_dir": str(applied.epic_dir)},
            )
        if result.status == "complete" and report.ok:
            return Continue(
                result,
                self.next_affected_story,
                intent=intent,
                applied=applied,
                index=0,
            )
        notes = result.notes if result.status == "blocked" else report.errors
        if reworks < MAX_REWORKS and result.status != "blocked":
            return Continue(
                report,
                self.rewrite_epic,
                intent=intent,
                snapshot=snapshot,
                plan=plan,
                applied=applied,
                findings=notes,
                reworks=reworks + 1,
            )
        return Await(
            self._abs(paths.epic_context(applied.epic_dir)),
            notes,
            self.rewrite_epic,
            intent=intent,
            snapshot=snapshot,
            plan=plan,
            applied=applied,
            findings=notes,
            reworks=0,
        )

    def next_affected_story(
        self,
        intent: EditIntent,
        applied: AppliedEpicEdit,
        index: int = 0,
    ) -> Continue:
        pick = self.call(
            select_affected_story,
            applied.epic,
            applied.affected_stories,
            index,
        )
        if not pick.has_story:
            return Continue(pick, self.check_coverage, intent=intent, applied=applied)
        return Continue(
            pick,
            self.design_mockup,
            intent=intent,
            applied=applied,
            pick=pick,
            index=index,
        )

    def design_mockup(
        self,
        intent: EditIntent,
        applied: AppliedEpicEdit,
        pick: StoryChoice,
        index: int,
    ) -> Continue:
        result = self.agent(
            "epic_edit/prompts/design-mockup.md",
            returns=MockupResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": applied.epic,
                "story_slug": pick.story_slug,
                "story_dir": pick.story_dir,
                "features_dir": self.ctx.features_dir,
                "epics_dir": self.ctx.epics_dir,
            },
        )
        return Continue(
            result,
            self.write_story,
            intent=intent,
            applied=applied,
            pick=pick,
            index=index,
            mockup=result.mockup,
        )

    def write_story(
        self,
        intent: EditIntent,
        applied: AppliedEpicEdit,
        pick: StoryChoice,
        index: int,
        mockup: str = "",
        reworks: int = 0,
    ) -> Continue | Await:
        result = self.agent(
            "epic_edit/prompts/write-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": applied.epic,
                "story_path": pick.story_path,
                "story_slug": pick.story_slug,
                "story_dir": pick.story_dir,
                "features_dir": self.ctx.features_dir,
                "mockup_path": mockup,
                "epic_edit": intent.change,
            },
        )
        if result.status == "blocked":
            return Await(
                self._abs(paths.story_context(pick.story_dir)),
                result.notes,
                self.write_story,
                intent=intent,
                applied=applied,
                pick=pick,
                index=index,
                mockup=mockup,
                reworks=reworks,
            )
        return Continue(
            result,
            self.check_story,
            intent=intent,
            applied=applied,
            pick=pick,
            index=index,
            mockup=mockup,
            reworks=reworks,
        )

    def check_story(
        self,
        intent: EditIntent,
        applied: AppliedEpicEdit,
        pick: StoryChoice,
        index: int,
        mockup: str = "",
        reworks: int = 0,
    ) -> Continue | Await:
        structure = self.call(validate_story, pick.story_dir)
        grounding = (
            self.call(
                check_story_grounding,
                pick.story_dir,
                applied.epic_dir,
                self.ctx.features_dir,
            )
            if structure.ok
            else Defects()
        )
        errors = structure.errors if not structure.ok else grounding.errors
        if errors:
            if reworks >= MAX_REWORKS:
                return Await(
                    self._abs(paths.story_context(pick.story_dir)),
                    errors,
                    self.write_story,
                    intent=intent,
                    applied=applied,
                    pick=pick,
                    index=index,
                    mockup=mockup,
                    reworks=0,
                )
            ledger = self.call(
                record_attempt,
                f"{pick.story_dir.rstrip('/')}/attempts.md",
                str(reworks),
                errors,
            )
            result = self.agent(
                "epic_edit/prompts/rework-story.md",
                returns=WriteStoryResult,
                power="high",
                cwd=self.ctx.repo_root,
                args={
                    "epic": applied.epic,
                    "story_path": pick.story_path,
                    "story_slug": pick.story_slug,
                    "story_dir": pick.story_dir,
                    "features_dir": self.ctx.features_dir,
                    "mockup_path": mockup,
                    "validation_errors": errors,
                    "prior_attempts": ledger.prior_attempts,
                    "operator_feedback": intent.change,
                },
            )
            return Continue(
                result,
                self.check_story,
                intent=intent,
                applied=applied,
                pick=pick,
                index=index,
                mockup=mockup,
                reworks=reworks + 1,
            )
        return Continue(
            grounding,
            self.audit_story,
            intent=intent,
            applied=applied,
            pick=pick,
            index=index,
            mockup=mockup,
            reworks=reworks,
        )

    def audit_story(
        self,
        intent: EditIntent,
        applied: AppliedEpicEdit,
        pick: StoryChoice,
        index: int,
        mockup: str = "",
        reworks: int = 0,
    ) -> Continue | Await:
        result = self.agent(
            "epic_edit/prompts/audit-story.md",
            returns=AuditResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": applied.epic,
                "story_path": pick.story_path,
                "story_slug": pick.story_slug,
                "story_dir": pick.story_dir,
                "features_dir": self.ctx.features_dir,
            },
        )
        if result.status != "passed":
            if reworks >= MAX_REWORKS:
                return Await(
                    self._abs(paths.story_context(pick.story_dir)),
                    result.notes,
                    self.write_story,
                    intent=intent,
                    applied=applied,
                    pick=pick,
                    index=index,
                    mockup=mockup,
                    reworks=0,
                )
            return Continue(
                result,
                self.rework_story,
                intent=intent,
                applied=applied,
                pick=pick,
                index=index,
                mockup=mockup,
                findings=result.notes,
                reworks=reworks,
            )
        return Continue(
            result,
            self.next_affected_story,
            intent=intent,
            applied=applied,
            index=index + 1,
        )

    def rework_story(
        self,
        intent: EditIntent,
        applied: AppliedEpicEdit,
        pick: StoryChoice,
        index: int,
        findings: str,
        mockup: str = "",
        reworks: int = 0,
    ) -> Continue:
        ledger = self.call(
            record_attempt,
            f"{pick.story_dir.rstrip('/')}/attempts.md",
            str(reworks),
            findings,
        )
        result = self.agent(
            "epic_edit/prompts/rework-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": applied.epic,
                "story_path": pick.story_path,
                "story_slug": pick.story_slug,
                "story_dir": pick.story_dir,
                "features_dir": self.ctx.features_dir,
                "mockup_path": mockup,
                "validation_errors": findings,
                "prior_attempts": ledger.prior_attempts,
                "operator_feedback": intent.change,
            },
        )
        return Continue(
            result,
            self.check_story,
            intent=intent,
            applied=applied,
            pick=pick,
            index=index,
            mockup=mockup,
            reworks=reworks + 1,
        )

    def check_coverage(self, intent: EditIntent, applied: AppliedEpicEdit) -> Continue:
        report = self.call(validate_coverage, applied.epic_dir)
        if not report.ok:
            raise WorkflowFailed(
                f"epic edit broke story coverage:\n{report.errors}",
                failure_class="epic-edit-coverage-broken",
                artifacts={"epic_dir": str(applied.epic_dir)},
            )
        review = self.agent(
            "epic_edit/prompts/review-coverage.md",
            returns=CoverageReview,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": applied.epic,
                "epic_dir": applied.epic_dir,
                "backlog": self.ctx.backlog_path,
            },
        )
        if review.status != "ok":
            raise WorkflowFailed(
                f"epic edit coverage review did not pass:\n{review.notes}",
                failure_class="epic-edit-coverage-review-failed",
                artifacts={"epic_dir": str(applied.epic_dir)},
            )
        return Continue(review, self.finish, intent=intent, applied=applied)

    def finish(self, intent: EditIntent, applied: AppliedEpicEdit) -> Done:
        report = self.call(verify_integrity, "")
        if not report.holds and not report.skipped:
            self.call(commit_author, "incomplete", applied.epic, intent.change)
            raise WorkflowFailed(
                f"epic edit broke graph integrity:\n{report.errors}",
                failure_class="epic-edit-graph-integrity-broken",
                artifacts={"epic_dir": str(applied.epic_dir)},
            )
        if intent.kind == "add-story" and intent.from_backlog:
            self.call(prune_bullet, intent.bullet_id, True)
        self.call(commit_author, "epic-edit", applied.epic, intent.change)
        return Done(applied)


__all__ = ["EpicEdit"]
