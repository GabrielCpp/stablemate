"""Implement one long plan as a chain of independently reviewed phases."""
from __future__ import annotations

from typing import Any, ClassVar

from workhorse.pyflow import Continue, Done, Workflow, WorkflowFailed

from workhorse_workflows.coder.implement_plan.flow import ImplementPlan
from workhorse_workflows.coder.implement_plan.schemas import PlanImplementationResult
from workhorse_workflows.coder.stage_plan.execution import (
    complete_stages,
    enter_stage,
    project_stage_progress,
    record_stage_outcome,
    verify_staged_candidate,
)
from workhorse_workflows.coder.stage_plan.inventory import (
    prepare_slices,
    snapshot_staged_plan,
)
from workhorse_workflows.coder.stage_plan.schemas import (
    PlanSlicing,
    PreparedSlices,
    StageOutcome,
    StagePlanContext,
    StagedSlice,
)
from workhorse_workflows.kit.telemetry import counter_labels


class StagePlan(Workflow):
    """Slice one plan into phases and run `implement-plan` over each in order.

    `implement-plan` reviews the whole plan against the whole candidate. On a plan whose
    phases share files, that review has to keep re-reading work it already approved and
    keeps finding the next phase's absence, which spends the fix-cycle budget on churn
    rather than defects. A phase is small enough that its review converges — and this
    flow is what keeps the phases honest: the slicing is proved to cover the source, the
    phases run in the plan's own order, and the source plan's repository-wide gate runs
    once at the end against the tree they built together.
    """

    plan_path: str

    injects: ClassVar[tuple[str, ...]] = ("repo_dir",)
    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("phase",)

    def setup(self) -> StagePlanContext:
        if not self.plan_path.strip():
            raise WorkflowFailed("stage-plan requires a plan_path")
        return self.call(snapshot_staged_plan, self.plan_path, str(self.run_dir))

    def labels(self) -> dict[str, str]:
        return {"work_id": self.ctx.plan_digest[:12], "mode": "stage-plan"}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "stage-plan", self.BUDGET_LABELS)

    def start(self) -> Continue:
        slicing = self.agent(
            "prompts/slice-implementation-plan.md",
            returns=PlanSlicing,
            power="extra-smart",
            cwd=self.ctx.repo_root,
            args={
                "plan_text": self.ctx.plan_text,
                "plan_digest": self.ctx.plan_digest,
                "repo_root": self.ctx.repo_root,
            },
        )
        return Continue(slicing, self.prepare, slicing=slicing)

    def prepare(self, slicing: PlanSlicing) -> Continue:
        prepared = self.call(prepare_slices, slicing, self.ctx)
        self.call(project_stage_progress, self.ctx, prepared, 0, [])
        return Continue(
            prepared,
            self.select,
            prepared=prepared,
            index=0,
            outcomes=[],
            expected_head=self.ctx.base_commit,
        )

    def select(
        self,
        prepared: PreparedSlices,
        index: int,
        outcomes: list[StageOutcome],
        expected_head: str,
    ) -> Continue:
        self.call(project_stage_progress, self.ctx, prepared, index, outcomes)
        if index >= len(prepared.slices):
            return Continue(
                prepared,
                self.final_gate,
                prepared=prepared,
                outcomes=outcomes,
                expected_head=expected_head,
            )
        staged = prepared.slices[index]
        self.call(enter_stage, self.ctx, staged, expected_head)
        return Continue(
            staged,
            self.stage,
            prepared=prepared,
            index=index,
            staged=staged,
            outcomes=outcomes,
            expected_head=expected_head,
        )

    def stage(
        self,
        prepared: PreparedSlices,
        index: int,
        staged: StagedSlice,
        outcomes: list[StageOutcome],
        expected_head: str,
    ) -> Continue:
        """Hand one phase to `implement-plan`, which owns every commit it produces."""
        result = self.handoff(ImplementPlan, plan_path=staged.path)
        return Continue(
            result,
            self.record,
            prepared=prepared,
            index=index,
            staged=staged,
            outcomes=outcomes,
            expected_head=expected_head,
            result=result,
        )

    def record(
        self,
        prepared: PreparedSlices,
        index: int,
        staged: StagedSlice,
        outcomes: list[StageOutcome],
        expected_head: str,
        result: PlanImplementationResult,
    ) -> Continue:
        """Archive the finished phase before the next handoff empties its scope."""
        outcome = self.call(
            record_stage_outcome,
            self.ctx,
            staged,
            result,
            str(self.run_dir / "implement_plan" / "_flow"),
            expected_head,
        )
        completed = [*outcomes, outcome]
        self.call(project_stage_progress, self.ctx, prepared, index + 1, completed)
        return Continue(
            outcome,
            self.select,
            prepared=prepared,
            index=index + 1,
            outcomes=completed,
            expected_head=outcome.final_commit,
        )

    def final_gate(
        self,
        prepared: PreparedSlices,
        outcomes: list[StageOutcome],
        expected_head: str,
    ) -> Done:
        """Run the source plan's own gate against everything the phases built."""
        self.call(verify_staged_candidate, self.ctx, prepared, outcomes, expected_head)
        return Done(
            self.call(complete_stages, self.ctx, prepared, outcomes, expected_head)
        )


__all__ = ["StagePlan"]
