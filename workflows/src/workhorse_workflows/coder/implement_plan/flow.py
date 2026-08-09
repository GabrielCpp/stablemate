"""A checkpoint-authoritative plan-to-commits worklist."""
from __future__ import annotations

from typing import Any, ClassVar

from workhorse.pyflow import Continue, Done, Workflow, WorkflowFailed

from workhorse_workflows.coder.implement_plan.execution import (
    complete_plan,
    check_agent_turn,
    check_planning_turn,
    commit_plan_task,
    decide_task_entry,
    project_plan_progress,
    publish_plan_task,
    verify_final_candidate,
    verify_committed_task,
    verify_plan_task,
)
from workhorse_workflows.coder.implement_plan.inventory import prepare_plan, snapshot_plan
from workhorse_workflows.coder.implement_plan.schemas import (
    ImplementationResult,
    PlanDecomposition,
    PlanRunContext,
    PlanTask,
    PreparedPlan,
)
from workhorse_workflows.kit.telemetry import counter_labels


class ImplementPlan(Workflow):
    """Split one reviewed plan into dependency-ordered, verified, pushed commits."""

    plan_path: str

    injects: ClassVar[tuple[str, ...]] = ("repo_dir",)
    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("repair",)
    MAX_REPAIRS: ClassVar[int] = 2

    def setup(self) -> PlanRunContext:
        if not self.plan_path.strip():
            raise WorkflowFailed("implement-plan requires a plan_path")
        return self.call(snapshot_plan, self.plan_path, str(self.run_dir))

    def labels(self) -> dict[str, str]:
        return {"work_id": self.ctx.plan_digest[:12], "mode": "implement-plan"}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "implement-plan", self.BUDGET_LABELS)

    def start(self) -> Continue:
        decomposition = self.agent(
            "prompts/decompose-implementation-plan.md",
            returns=PlanDecomposition,
            power="smart",
            cwd=self.ctx.repo_root,
            args={
                "plan_text": self.ctx.plan_text,
                "plan_digest": self.ctx.plan_digest,
                "repo_root": self.ctx.repo_root,
            },
        )
        return Continue(decomposition, self.prepare, decomposition=decomposition)

    def prepare(self, decomposition: PlanDecomposition) -> Continue:
        self.call(check_planning_turn, self.ctx)
        plan = self.call(prepare_plan, decomposition, self.ctx)
        self.call(project_plan_progress, self.ctx, plan, 0, [])
        return Continue(
            plan,
            self.select,
            plan=plan,
            index=0,
            completed_commits=[],
            expected_head=self.ctx.base_commit,
        )

    def select(
        self,
        plan: PreparedPlan,
        index: int,
        completed_commits: list[str],
        expected_head: str,
    ) -> Continue:
        self.call(project_plan_progress, self.ctx, plan, index, completed_commits)
        if index >= len(plan.tasks):
            return Continue(
                plan,
                self.final_gate,
                plan=plan,
                completed_commits=completed_commits,
                expected_head=expected_head,
            )
        task = plan.tasks[index]
        decision = self.call(decide_task_entry, self.ctx, task, expected_head)
        if decision.phase == "publish":
            return Continue(
                decision,
                self.verify_committed,
                plan=plan,
                index=index,
                task=task,
                completed_commits=completed_commits,
                expected_parent=expected_head,
                commit_sha=decision.commit_sha,
            )
        return Continue(
            decision,
            self.implement,
            plan=plan,
            index=index,
            task=task,
            completed_commits=completed_commits,
            expected_head=expected_head,
        )

    def implement(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_head: str,
    ) -> Continue:
        result = self.agent(
            "prompts/implement-plan-task.md",
            returns=ImplementationResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._task_args(task),
        )
        self.call(check_agent_turn, self.ctx, task, expected_head)
        self._require_agent_done(result, task)
        return Continue(
            result,
            self.verify,
            plan=plan,
            index=index,
            task=task,
            completed_commits=completed_commits,
            expected_head=expected_head,
        )

    def verify(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_head: str,
        repair: int = 0,
    ) -> Continue:
        result = self.call(verify_plan_task, self.ctx, task, expected_head)
        if result.passed:
            return Continue(
                result,
                self.commit,
                plan=plan,
                index=index,
                task=task,
                completed_commits=completed_commits,
                expected_head=expected_head,
            )
        if repair >= self.MAX_REPAIRS:
            self.call(
                project_plan_progress,
                self.ctx,
                plan,
                index,
                completed_commits,
                task.id,
            )
            raise WorkflowFailed(
                f"task {task.id} did not pass after {self.MAX_REPAIRS + 1} verification attempts"
            )
        return Continue(
            result,
            self.repair,
            plan=plan,
            index=index,
            task=task,
            completed_commits=completed_commits,
            expected_head=expected_head,
            repair=repair,
            findings=result.findings,
        )

    def repair(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_head: str,
        repair: int,
        findings: str,
    ) -> Continue:
        args = self._task_args(task)
        args["findings"] = findings
        args["repair"] = repair + 1
        result = self.agent(
            "prompts/repair-plan-task.md",
            returns=ImplementationResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=args,
        )
        self.call(check_agent_turn, self.ctx, task, expected_head)
        self._require_agent_done(result, task)
        return Continue(
            result,
            self.verify,
            plan=plan,
            index=index,
            task=task,
            completed_commits=completed_commits,
            expected_head=expected_head,
            repair=repair + 1,
        )

    def commit(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_head: str,
    ) -> Continue:
        result = self.call(commit_plan_task, self.ctx, task, expected_head)
        return Continue(
            result,
            self.verify_committed,
            plan=plan,
            index=index,
            task=task,
            completed_commits=completed_commits,
            expected_parent=expected_head,
            commit_sha=result.commit_sha,
        )

    def verify_committed(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_parent: str,
        commit_sha: str,
    ) -> Continue:
        """Verify the exact clean tree that the next state may publish."""
        result = self.call(
            verify_committed_task,
            self.ctx,
            task,
            expected_parent,
            commit_sha,
        )
        if index + 1 == len(plan.tasks):
            return Continue(
                result,
                self.final_candidate,
                plan=plan,
                index=index,
                task=task,
                completed_commits=completed_commits,
                expected_parent=expected_parent,
                commit_sha=commit_sha,
            )
        return Continue(
            result,
            self.publish,
            plan=plan,
            index=index,
            task=task,
            completed_commits=completed_commits,
            expected_parent=expected_parent,
            commit_sha=commit_sha,
        )

    def final_candidate(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_parent: str,
        commit_sha: str,
    ) -> Continue:
        """Gate the fully committed candidate before its last packet reaches origin."""
        self.call(
            verify_final_candidate,
            self.ctx,
            plan,
            [*completed_commits, commit_sha],
            commit_sha,
        )
        return Continue(
            None,
            self.publish,
            plan=plan,
            index=index,
            task=task,
            completed_commits=completed_commits,
            expected_parent=expected_parent,
            commit_sha=commit_sha,
        )

    def publish(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_parent: str,
        commit_sha: str,
    ) -> Continue:
        result = self.call(
            publish_plan_task,
            self.ctx,
            task,
            expected_parent,
            commit_sha,
        )
        completed = [*completed_commits, result.commit_sha]
        self.call(project_plan_progress, self.ctx, plan, index + 1, completed)
        return Continue(
            result,
            self.select,
            plan=plan,
            index=index + 1,
            completed_commits=completed,
            expected_head=result.commit_sha,
        )

    def final_gate(
        self,
        plan: PreparedPlan,
        completed_commits: list[str],
        expected_head: str,
    ) -> Done:
        return Done(
            self.call(
                complete_plan,
                self.ctx,
                plan,
                completed_commits,
                expected_head,
            )
        )

    def _task_args(self, task: PlanTask) -> dict[str, Any]:
        return {
            "plan_text": self.ctx.plan_text,
            "plan_digest": self.ctx.plan_digest,
            "repo_root": self.ctx.repo_root,
            "task": task.model_dump(mode="json"),
        }

    @staticmethod
    def _require_agent_done(result: ImplementationResult, task: PlanTask) -> None:
        if result.status != "done":
            detail = result.notes.strip() or result.status or "no implementation result"
            raise WorkflowFailed(f"task {task.id} implementation blocked: {detail}")


__all__ = ["ImplementPlan"]