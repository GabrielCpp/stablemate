"""Checkpointed execution of one independent-review issue worklist."""
from __future__ import annotations

from typing import Any, ClassVar

from workhorse.pyflow import Continue, Done, Workflow, WorkflowFailed

from workhorse_workflows.coder.implement_plan.execution import (
    check_agent_turn,
    commit_plan_task,
    decide_task_entry,
    publish_plan_task,
    retract_task_commit,
    verify_committed_task,
    verify_final_candidate,
    verify_plan_task,
)
from workhorse_workflows.coder.implement_plan.review import (
    complete_review_issues,
    project_review_progress,
)
from workhorse_workflows.coder.implement_plan.schemas import (
    ImplementationResult,
    PlanRunContext,
    PlanTask,
    PreparedPlan,
)
from workhorse_workflows.kit.telemetry import counter_labels


class ReviewIssues(Workflow):
    """Fix, verify, commit, and publish every issue in one semantic review."""

    run_context: PlanRunContext
    plan: PreparedPlan
    expected_head: str
    cycle: int

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("repair",)
    MAX_REPAIRS: ClassVar[int] = 2

    def setup(self) -> PlanRunContext:
        return self.run_context

    def labels(self) -> dict[str, str]:
        return {"work_id": self.ctx.plan_digest[:12], "mode": "plan-review-fixes"}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "plan-review", self.BUDGET_LABELS)

    def start(self) -> Continue:
        self.call(project_review_progress, self.ctx, self.plan, self.cycle, 0, [])
        return Continue(
            None,
            self.select,
            index=0,
            commits=[],
            expected_head=self.expected_head,
        )

    def select(self, index: int, commits: list[str], expected_head: str) -> Continue | Done:
        self.call(
            project_review_progress,
            self.ctx,
            self.plan,
            self.cycle,
            index,
            commits,
        )
        if index >= len(self.plan.tasks):
            return Done(
                self.call(complete_review_issues, self.ctx, self.plan, commits, expected_head)
            )
        issue = self.plan.tasks[index]
        decision = self.call(decide_task_entry, self.ctx, issue, expected_head)
        if decision.phase == "publish":
            return Continue(
                decision,
                self.verify_committed,
                index=index,
                issue=issue,
                commits=commits,
                expected_parent=expected_head,
                commit_sha=decision.commit_sha,
            )
        return Continue(
            decision,
            self.implement,
            index=index,
            issue=issue,
            commits=commits,
            expected_head=expected_head,
        )

    def implement(
        self,
        index: int,
        issue: PlanTask,
        commits: list[str],
        expected_head: str,
    ) -> Continue:
        result = self.agent(
            "prompts/fix-plan-review-issue.md",
            returns=ImplementationResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._issue_args(issue),
        )
        self.call(check_agent_turn, self.ctx, issue, expected_head)
        self._require_done(result, issue)
        return Continue(
            result,
            self.verify,
            index=index,
            issue=issue,
            commits=commits,
            expected_head=expected_head,
        )

    def verify(
        self,
        index: int,
        issue: PlanTask,
        commits: list[str],
        expected_head: str,
        repair: int = 0,
    ) -> Continue:
        result = self.call(verify_plan_task, self.ctx, issue, expected_head)
        if result.passed:
            return Continue(
                result,
                self.commit,
                index=index,
                issue=issue,
                commits=commits,
                expected_head=expected_head,
                repair=repair,
            )
        if repair >= self.MAX_REPAIRS:
            self.call(
                project_review_progress,
                self.ctx,
                self.plan,
                self.cycle,
                index,
                commits,
                issue.id,
            )
            raise WorkflowFailed(
                f"review issue {issue.id} did not pass after "
                f"{self.MAX_REPAIRS + 1} verification attempts"
            )
        return Continue(
            result,
            self.repair,
            index=index,
            issue=issue,
            commits=commits,
            expected_head=expected_head,
            repair=repair,
            findings=result.findings,
        )

    def repair(
        self,
        index: int,
        issue: PlanTask,
        commits: list[str],
        expected_head: str,
        repair: int,
        findings: str,
    ) -> Continue:
        args = self._issue_args(issue)
        args["findings"] = findings
        args["repair"] = repair + 1
        result = self.agent(
            "prompts/repair-plan-review-issue.md",
            returns=ImplementationResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=args,
        )
        self.call(check_agent_turn, self.ctx, issue, expected_head)
        self._require_done(result, issue)
        return Continue(
            result,
            self.verify,
            index=index,
            issue=issue,
            commits=commits,
            expected_head=expected_head,
            repair=repair + 1,
        )

    def commit(
        self,
        index: int,
        issue: PlanTask,
        commits: list[str],
        expected_head: str,
        repair: int = 0,
    ) -> Continue:
        result = self.call(commit_plan_task, self.ctx, issue, expected_head)
        return Continue(
            result,
            self.verify_committed,
            index=index,
            issue=issue,
            commits=commits,
            expected_parent=expected_head,
            commit_sha=result.commit_sha,
            repair=repair,
        )

    def verify_committed(
        self,
        index: int,
        issue: PlanTask,
        commits: list[str],
        expected_parent: str,
        commit_sha: str,
        repair: int = 0,
    ) -> Continue:
        """Verify the clean committed tree, spending the issue's repair budget on it.

        Same bargain as the parent flow: only the committed files reach the export, so a
        command that passed in the worktree and fails here has found something real, and
        the fix belongs in the issue rather than in a dead run. The counter comes through
        the commit so the two gates share one budget.
        """
        result = self.call(
            verify_committed_task,
            self.ctx,
            issue,
            expected_parent,
            commit_sha,
        )
        if not result.passed:
            if repair >= self.MAX_REPAIRS:
                self.call(
                    project_review_progress,
                    self.ctx,
                    self.plan,
                    self.cycle,
                    index,
                    commits,
                    issue.id,
                )
                raise WorkflowFailed(
                    f"review issue {issue.id} committed verification failed:\n{result.findings}"
                )
            self.call(retract_task_commit, self.ctx, issue, expected_parent, commit_sha)
            return Continue(
                result,
                self.repair,
                index=index,
                issue=issue,
                commits=commits,
                expected_head=expected_parent,
                repair=repair,
                findings=result.findings,
            )
        if index + 1 == len(self.plan.tasks):
            return Continue(
                result,
                self.final_candidate,
                index=index,
                issue=issue,
                commits=commits,
                expected_parent=expected_parent,
                commit_sha=commit_sha,
            )
        return Continue(
            result,
            self.publish,
            index=index,
            issue=issue,
            commits=commits,
            expected_parent=expected_parent,
            commit_sha=commit_sha,
        )

    def final_candidate(
        self,
        index: int,
        issue: PlanTask,
        commits: list[str],
        expected_parent: str,
        commit_sha: str,
    ) -> Continue:
        self.call(
            verify_final_candidate,
            self.ctx,
            self.plan,
            [*commits, commit_sha],
            commit_sha,
            expected_parent,
        )
        return Continue(
            None,
            self.publish,
            index=index,
            issue=issue,
            commits=commits,
            expected_parent=expected_parent,
            commit_sha=commit_sha,
        )

    def publish(
        self,
        index: int,
        issue: PlanTask,
        commits: list[str],
        expected_parent: str,
        commit_sha: str,
    ) -> Continue:
        result = self.call(
            publish_plan_task,
            self.ctx,
            issue,
            expected_parent,
            commit_sha,
        )
        completed = [*commits, result.commit_sha]
        self.call(
            project_review_progress,
            self.ctx,
            self.plan,
            self.cycle,
            index + 1,
            completed,
        )
        return Continue(
            result,
            self.select,
            index=index + 1,
            commits=completed,
            expected_head=result.commit_sha,
        )

    def _issue_args(self, issue: PlanTask) -> dict[str, Any]:
        return {
            "plan_text": self.ctx.plan_text,
            "plan_digest": self.ctx.plan_digest,
            "repo_root": self.ctx.repo_root,
            "issue": issue.model_dump(mode="json"),
        }

    @staticmethod
    def _require_done(result: ImplementationResult, issue: PlanTask) -> None:
        if result.status != "done":
            detail = result.notes.strip() or result.status or "no fix result"
            raise WorkflowFailed(f"review issue {issue.id} fix blocked: {detail}")


__all__ = ["ReviewIssues"]