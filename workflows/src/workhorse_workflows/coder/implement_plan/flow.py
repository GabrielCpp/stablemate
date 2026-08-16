"""A checkpoint-authoritative plan-to-commits worklist."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Continue, Done, Workflow, WorkflowFailed

from workhorse_workflows.coder.implement_plan.execution import (
    complete_plan,
    check_agent_turn,
    check_planning_turn,
    commit_plan_task,
    decide_task_entry,
    extend_task_paths,
    project_plan_progress,
    publish_plan_task,
    retract_task_commit,
    verify_final_candidate,
    verify_committed_task,
    verify_plan_task,
)
from workhorse_workflows.coder.implement_plan.inventory import (
    audit_plan_decomposition,
    prepare_plan,
    snapshot_plan,
)
from workhorse_workflows.coder.implement_plan.review import (
    check_review_turn,
    prepare_review_issues,
    project_review_approval,
    project_review_progress,
    validate_review_report,
)
from workhorse_workflows.coder.implement_plan.review_flow import ReviewIssues
from workhorse_workflows.coder.implement_plan.schemas import (
    ImplementationResult,
    PlanDecomposition,
    PlanRunContext,
    PlanReview,
    PlanTask,
    PreparedPlan,
)
from workhorse_workflows.coder.shared.red_gate import (
    REGRESSION_ONLY_MARKER,
    arm_red_gate,
    run_red_gate,
)
from workhorse_workflows.kit.telemetry import counter_labels


class ImplementPlan(Workflow):
    """Split one reviewed plan into dependency-ordered, verified, pushed commits."""

    plan_path: str

    injects: ClassVar[tuple[str, ...]] = ("repo_dir",)
    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("repair", "tests_rework", "decomposition_rework")
    MAX_REPAIRS: ClassVar[int] = 2
    MAX_TESTS_REWORKS: ClassVar[int] = 2
    MAX_DECOMPOSITION_REWORKS: ClassVar[int] = 2
    MAX_REVIEW_FIX_CYCLES: ClassVar[int] = 3

    def setup(self) -> PlanRunContext:
        if not self.plan_path.strip():
            raise WorkflowFailed("implement-plan requires a plan_path")
        return self.call(snapshot_plan, self.plan_path, str(self.run_dir))

    def labels(self) -> dict[str, str]:
        return {"work_id": self.ctx.plan_digest[:12], "mode": "implement-plan"}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "implement-plan", self.BUDGET_LABELS)

    def start(self) -> Continue:
        return Continue(None, self.decompose, findings="", decomposition_rework=0)

    def decompose(self, findings: str, decomposition_rework: int) -> Continue:
        """Propose the packet DAG; on rework, the rejection rides in as context."""
        decomposition = self.agent(
            "prompts/decompose-implementation-plan.md",
            returns=PlanDecomposition,
            power="smart",
            cwd=self.ctx.repo_root,
            args={
                "plan_text": self.ctx.plan_text,
                "plan_digest": self.ctx.plan_digest,
                "repo_root": self.ctx.repo_root,
                "findings": findings,
            },
        )
        return Continue(
            decomposition,
            self.prepare,
            decomposition=decomposition,
            decomposition_rework=decomposition_rework,
        )

    def prepare(
        self, decomposition: PlanDecomposition, decomposition_rework: int = 0
    ) -> Continue:
        """Admit the proposal as checkpoint authority, or spend one rework on it.

        The audit reports the same verdict `prepare_plan` would raise, so a proposal
        that is one packet away from valid is corrected rather than ending the run.
        Past the bound the validation raises as before: a subject over 72 characters
        would only be refused again by the commit-msg hook, so it must stay fatal.
        """
        self.call(check_planning_turn, self.ctx)
        findings = self.call(audit_plan_decomposition, decomposition, self.ctx)
        if findings and decomposition_rework < self.MAX_DECOMPOSITION_REWORKS:
            return Continue(
                findings,
                self.decompose,
                findings=findings,
                decomposition_rework=decomposition_rework + 1,
            )
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
                self.review,
                plan=plan,
                completed_commits=completed_commits,
                expected_head=expected_head,
                cycle=0,
                review_issue_count=0,
                review_commits=[],
                review_issue_ids=[],
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
        """Route the packet into the TDD split, or one classic turn for regression-only plans.

        The marker is read from the checkpointed plan snapshot, never from the file on
        disk — a plan edited mid-run must not flip the route between packets.
        """
        if REGRESSION_ONLY_MARKER in self.ctx.plan_text.lower():
            result = self._implement_classic(plan, task, expected_head)
            return Continue(
                result,
                self.verify,
                plan=plan,
                index=index,
                task=task,
                completed_commits=completed_commits,
                expected_head=expected_head,
            )
        arm = self.call(arm_red_gate, self.ctx.repo_root)
        return Continue(
            arm,
            self.implement_tests,
            plan=plan,
            index=index,
            task=task,
            completed_commits=completed_commits,
            expected_head=expected_head,
        )

    def implement_tests(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_head: str,
        tests_rework: int = 0,
        gate_feedback: str = "",
    ) -> Continue:
        """One tests-only turn for this packet; the red gate judges its diff next.

        Ownership is checked without require_changes: an empty diff is the gate's
        `no_tests` verdict to loop back as bounded rework, not a hard failure here.
        """
        arm = self.output(arm_red_gate)
        args = self._task_args(task)
        args["test_command"] = arm.test_command
        args["gate_feedback"] = gate_feedback
        result = self.agent(
            "prompts/implement-plan-task-tests.md",
            returns=ImplementationResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=args,
        )
        self.call(check_agent_turn, self.ctx, plan, task, expected_head, False)
        self._require_agent_done(result, task)
        return Continue(
            result,
            self.red_gate,
            plan=plan,
            index=index,
            task=task,
            completed_commits=completed_commits,
            expected_head=expected_head,
            tests_rework=tests_rework,
        )

    def red_gate(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_head: str,
        tests_rework: int = 0,
    ) -> Continue:
        """Deterministically judge the tests turn: pure test diff, meaningfully red.

        A rejected outcome loops back to the tests turn with the verdict, bounded by
        MAX_TESTS_REWORKS; past the bound the gate fails open, because the review's
        AC-coverage audit is the binding check and a stalled packet helps nobody.
        """
        arm = self.output(arm_red_gate)
        outcome = self.call(
            run_red_gate,
            self.ctx.repo_root,
            task.id,
            str(Path(self.ctx.worklist_path).parent),
            arm.baseline,
            arm.test_command,
            arm.signatures,
        )
        rejected = outcome.status in {"all_green", "impure", "no_tests"}
        if rejected and tests_rework < self.MAX_TESTS_REWORKS:
            return Continue(
                outcome,
                self.implement_tests,
                plan=plan,
                index=index,
                task=task,
                completed_commits=completed_commits,
                expected_head=expected_head,
                tests_rework=tests_rework + 1,
                gate_feedback=f"[{outcome.status}] {outcome.reason}",
            )
        if rejected:
            self.logger.warning(
                "red gate still %s after %d rework(s) — proceeding fail-open",
                outcome.status,
                tests_rework,
            )
        return Continue(
            outcome,
            self.implement_code,
            plan=plan,
            index=index,
            task=task,
            completed_commits=completed_commits,
            expected_head=expected_head,
        )

    def implement_code(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_head: str,
    ) -> Continue:
        """Make the packet's red suite pass; the gate's verdict rides along as context."""
        outcome = self.output(run_red_gate)
        args = self._task_args(task)
        args["red_status"] = outcome.status
        args["red_log_path"] = outcome.log_path
        result = self.agent(
            "prompts/implement-plan-task-code.md",
            returns=ImplementationResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=args,
        )
        self.call(check_agent_turn, self.ctx, plan, task, expected_head)
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

    def _implement_classic(
        self, plan: PreparedPlan, task: PlanTask, expected_head: str
    ) -> ImplementationResult:
        result = self.agent(
            "prompts/implement-plan-task.md",
            returns=ImplementationResult,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._task_args(task),
        )
        self.call(check_agent_turn, self.ctx, plan, task, expected_head)
        self._require_agent_done(result, task)
        return result

    def verify(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_head: str,
        repair: int = 0,
    ) -> Continue:
        result = self.call(verify_plan_task, self.ctx, plan, task, expected_head)
        if result.passed:
            return Continue(
                result,
                self.commit,
                plan=plan,
                index=index,
                task=task,
                completed_commits=completed_commits,
                expected_head=expected_head,
                repair=repair,
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
        export_repair: bool = False,
    ) -> Continue:
        """Hand the packet back to the agent, then re-assert its repository boundary.

        `export_repair` marks the arm reached from the committed-tree gate, and only that
        arm may widen the packet's declared paths — that gate's finding is routinely
        *about* the declaration, so refusing the widening there would refuse the correct
        fix. Every other repair keeps the packet exactly as scoped.
        """
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
        if export_repair:
            task = self.call(extend_task_paths, self.ctx, plan, index, task)
            # The widened packet rides on in the plan as well as in the state, so a resume
            # that re-enters `select` validates the commit against the paths it was
            # actually made from rather than the ones it was proposed with.
            plan = plan.model_copy(
                update={"tasks": [*plan.tasks[:index], task, *plan.tasks[index + 1 :]]}
            )
        self.call(check_agent_turn, self.ctx, plan, task, expected_head)
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
        repair: int = 0,
    ) -> Continue:
        result = self.call(commit_plan_task, self.ctx, plan, task, expected_head)
        return Continue(
            result,
            self.verify_committed,
            plan=plan,
            index=index,
            task=task,
            completed_commits=completed_commits,
            expected_parent=expected_head,
            commit_sha=result.commit_sha,
            repair=repair,
        )

    def verify_committed(
        self,
        plan: PreparedPlan,
        index: int,
        task: PlanTask,
        completed_commits: list[str],
        expected_parent: str,
        commit_sha: str,
        repair: int = 0,
    ) -> Continue:
        """Verify the exact clean tree that the next state may publish.

        This gate sees what the worktree cannot: only what was committed. A command that
        passed a moment ago and fails here has found a real defect in the packet, and
        until now that finding was terminal — the one gate in the loop with no second
        chance, positioned after the most expensive work in it. It spends the packet's
        repair budget instead, which is why the counter is threaded through the commit:
        a packet gets `MAX_REPAIRS` repair turns in total, not one allowance per gate,
        so the two cannot hand it back and forth forever.
        """
        result = self.call(
            verify_committed_task,
            self.ctx,
            task,
            expected_parent,
            commit_sha,
        )
        if not result.passed:
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
                    f"task {task.id} committed verification failed:\n{result.findings}"
                )
            self.call(retract_task_commit, self.ctx, task, expected_parent, commit_sha)
            return Continue(
                result,
                self.repair,
                plan=plan,
                index=index,
                task=task,
                completed_commits=completed_commits,
                expected_head=expected_parent,
                repair=repair,
                findings=result.findings,
                export_repair=True,
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
            expected_parent,
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

    def review(
        self,
        plan: PreparedPlan,
        completed_commits: list[str],
        expected_head: str,
        cycle: int,
        review_issue_count: int,
        review_commits: list[str],
        review_issue_ids: list[str],
    ) -> Continue:
        report = self.agent(
            "prompts/review-plan-implementation.md",
            returns=PlanReview,
            power="extra-smart",
            cwd=self.ctx.repo_root,
            args={
                "plan_text": self.ctx.plan_text,
                "plan_digest": self.ctx.plan_digest,
                "repo_root": self.ctx.repo_root,
                "base_commit": self.ctx.base_commit,
                "candidate_commit": expected_head,
                "prepared_plan": plan.model_dump(mode="json"),
                "review_cycle": cycle + 1,
            },
        )
        self.call(check_review_turn, self.ctx, expected_head)
        return Continue(
            report,
            self.route_review,
            plan=plan,
            completed_commits=completed_commits,
            expected_head=expected_head,
            cycle=cycle,
            review_issue_count=review_issue_count,
            review_commits=review_commits,
            review_issue_ids=review_issue_ids,
            report=report,
        )

    def route_review(
        self,
        plan: PreparedPlan,
        completed_commits: list[str],
        expected_head: str,
        cycle: int,
        review_issue_count: int,
        review_commits: list[str],
        review_issue_ids: list[str],
        report: PlanReview,
    ) -> Continue | Done:
        """Route one checkpointed review report into approval or its issue worklist."""
        self.call(validate_review_report, report)
        if report.status == "approved":
            self.call(
                verify_final_candidate,
                self.ctx,
                plan,
                completed_commits,
                expected_head,
                expected_head,
            )
            self.call(
                project_review_approval,
                self.ctx,
                cycle,
                report.summary,
                review_issue_ids,
                review_commits,
            )
            return Done(
                self.call(
                    complete_plan,
                    self.ctx,
                    plan,
                    completed_commits,
                    expected_head,
                    review_issue_count,
                    cycle + 1,
                    review_commits,
                    review_issue_ids,
                )
            )
        issues = self.call(prepare_review_issues, report, self.ctx, plan, cycle)
        if cycle >= self.MAX_REVIEW_FIX_CYCLES:
            self.call(
                project_review_progress,
                self.ctx,
                issues,
                cycle,
                0,
                [],
                issues.tasks[0].id,
            )
            raise WorkflowFailed(
                "implementation review did not converge after "
                f"{self.MAX_REVIEW_FIX_CYCLES} issue-fix cycles"
            )
        fixed = self.handoff(
            ReviewIssues,
            run_context=self.ctx,
            plan=issues,
            expected_head=expected_head,
            cycle=cycle,
        )
        if fixed.status != "fixed":
            raise WorkflowFailed(f"review issue worklist returned {fixed.status or 'no status'}")
        return Continue(
            fixed,
            self.review,
            plan=plan,
            completed_commits=completed_commits,
            expected_head=fixed.final_commit,
            cycle=cycle + 1,
            review_issue_count=review_issue_count + fixed.issue_count,
            review_commits=[*review_commits, *fixed.commits],
            review_issue_ids=[*review_issue_ids, *fixed.issue_ids],
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