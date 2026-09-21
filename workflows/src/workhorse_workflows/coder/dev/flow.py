"""Plan a story and implement it, one service layer at a time."""
from __future__ import annotations

from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow
from workhorse_workflows.coder.dev import nodes
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.shared.conversation import backbone
from workhorse_workflows.coder.shared.escalation import context_path
from workhorse_workflows.coder.shared.dev import (
    GATE_ORDER,
    branch_code_repos,
    changed_files,
    check_story_status,
    declared_markers,
    read_operator_context,
    record_plan,
    resolve_impl_context,
    run_gate,
    select_next_layer,
)
from workhorse_workflows.coder.shared.failure import from_findings, from_gate
from workhorse_workflows.coder.shared.resolution import answered
from workhorse_workflows.coder.shared.story import (
    guard_story_file,
    prepare_story,
    resolve_workspace_dirs,
    scrub_plan_mutations,
    snapshot_worktrees,
    stamp_specs,
    workspace_dirs,
)
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import (
    DevResult,
    FailureReport,
    FixResult,
    GateOutcome,
    Lap,
    PlanResult,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels


class Dev(Workflow):
    """Plan a story, gate the plan, then implement and repair it service by service."""

    story: str = ""
    docs_path: str = ""
    workspace_file: str = ""
    epic: str = ""
    operator_mode: str = "auto"
    target_env: str = "local"
    branch: str = ""

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths and the workspace to directories."""
        self.call(resolve_workspace_dirs, self.docs_path)
        story = self.call(prepare_story, self.docs_path, self.story, self.epic)
        guard_story_file(story)
        return story

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("plan_rework", "fix_lap", "plan_blocks")

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on."""
        return self.labels() | counter_labels(params, "dev", self.BUDGET_LABELS)

    def start(self) -> Continue | Await:
        """Author the plan, stamp what it wrote, and route on whether it is blocked."""
        self.logger.info("planning %s", self.ctx.story_slug, extra={"activity": True})
        snapshot = self.call(snapshot_worktrees, self.docs_path)
        turn = roles.turn(self, "plan-story", returns=PlanResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            session=backbone(self),
            add_dirs=workspace_dirs(self),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "markers": self.call(declared_markers).text,
            },
        )
        self.call(scrub_plan_mutations, snapshot.status)
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        if result.status == "blocked":
            return nodes.gate_plan(self, result, result.summary, 0)
        return Continue(
            result,
            self.validate_paths,
            notes=result.summary,
            plan=nodes.plan_arg(result),
        )

    def resolve_plan(self, notes: str, plan_blocks: int = 0) -> Continue | Await:
        """Resolve a plan block from what is already written down, or park for the operator."""
        result = nodes.resolver_turn(self, "plan", notes)
        if answered(self, result, "plan"):
            return Continue(
                result, self.read_operator, notes=notes, plan_blocks=plan_blocks + 1
            )
        gate = nodes.escalate(self, notes, plan_blocks, result)
        return Await(
            context_path(self),
            gate.body,
            self.read_operator,
            notes=notes,
            plan_blocks=plan_blocks + 1,
        )

    def read_operator(self, notes: str, plan_blocks: int = 0) -> Continue | Done:
        """Consume the answer and route on the scope the answerer chose."""
        answer = self.call(read_operator_context, self.ctx.story_path)
        if answer.scope == "epic":
            self.logger.info("operator scoped the fix to the epic — handing back to replan")
            return nodes.ends(self, DevResult(status="replan", operator_notes=answer.content))
        return Continue(
            answer,
            self.rework_plan,
            notes=notes,
            operator_context=answer.content,
            plan_blocks=plan_blocks,
        )

    def rework_plan(
        self, notes: str, operator_context: str, plan_blocks: int = 0
    ) -> Continue | Await:
        """Re-plan with the operator's answer in hand, and re-evaluate the same gate."""
        result = nodes.refine(
            self,
            "replan-with-answer",
            review_notes=notes,
            operator_context=operator_context,
            worklist="block-repair",
        )
        if result.status == "blocked":
            return nodes.gate_plan(self, result, result.summary, plan_blocks)
        self.reset_session(nodes.repair_chain(self, "block-repair"))
        return Continue(
            result,
            self.validate_paths,
            notes=result.summary,
            plan=nodes.plan_arg(result),
            plan_blocks=plan_blocks,
        )

    def validate_paths(
        self,
        notes: str,
        plan: dict | None = None,
        plan_rework: int = 0,
        plan_blocks: int = 0,
    ) -> Continue | Await:
        """Write the plan projection, and answer whether its service paths are real."""
        result = self.call(record_plan, plan, self.ctx.spec_dir)
        if result.status != "invalid":
            self.reset_session(nodes.repair_chain(self, "path-repair"))
            return Continue(result, self.dispatch)
        if plan_rework >= nodes.MAX_VALIDATE_REWORKS:
            return nodes.gate_plan(self, result, notes, plan_blocks)
        refined = nodes.refine(
            self,
            "repair-plan-paths",
            review_notes=f"Service path validation failed: {result.errors}",
            worklist="path-repair",
            power="low",
        )
        return Continue(
            refined,
            self.validate_paths,
            notes=refined.summary or notes,
            plan=nodes.plan_arg(refined),
            plan_rework=plan_rework + 1,
            plan_blocks=plan_blocks,
        )

    def dispatch(self) -> Continue:
        """Decode the approved plan against the workspace, and branch every code repo."""
        plan = self.output(record_plan).document
        impl = self.call(
            resolve_impl_context,
            self.ctx.spec_dir,
            self.target_env,
            self.docs_path,
            plan=plan,
        )
        self.logger.info("implementing %d service layer(s)", impl.dispatch_count)
        self.call(
            branch_code_repos,
            self.ctx.spec_dir,
            self.branch or self.story,
            self.docs_path,
            plan=plan,
        )
        return Continue(impl, self.layer)

    def layer(self, index: int = -1, lap: Lap = Lap()) -> Continue | Done:
        """Take the next service to implement, or finish."""
        pick = self.call(
            select_next_layer,
            self.ctx.spec_dir,
            index,
            plan=self.output(record_plan).document,
        )
        if not pick.has_layer:
            self.logger.info("every service layer implemented")
            return nodes.ends(self, DevResult(), lap.session_turns)
        self.logger.info(
            "implementing %s (%d/%d)", pick.layer.label, pick.index + 1, pick.dispatch_count
        )
        return Continue(pick, self.implement, index=pick.index, lap=lap)

    def implement(
        self,
        index: int,
        operator_context: str = "",
        impl_blocks: int = 0,
        lap: Lap = Lap(),
    ) -> Continue | Await:
        """Implement one service layer with the single `implement-plan.md` turn."""
        if not impl_blocks and not operator_context:
            self.reset_session(backbone(self))
            lap = lap.model_copy(update={"session_turns": 0})
        lap = nodes.spend(self, lap)
        result = nodes.implement_layer(self, operator_context)
        if result.blocked:
            return nodes.gate_impl(
                self, result, result.notes, index, "the implementation turn", impl_blocks, lap
            )
        return Continue(
            result, self.gates, index=index, lap=lap.model_copy(update={"fix_lap": 0, "digest": ""})
        )

    def gates(
        self, index: int, impl_blocks: int = 0, lap: Lap = Lap()
    ) -> Continue | Await:
        """Run this service's deterministic gates, and route on the first one that says no."""
        layer = nodes.current_layer(self)
        stamped = self.call(
            check_story_status,
            self.docs_path,
            self.ctx.story_slug,
            epic=self.ctx.story_epic,
            story_path=self.ctx.story_path,
        )
        if stamped.status == "dirty":
            return nodes.repair_or_escalate(
                self,
                from_findings(
                    "story status",
                    [
                        Finding(
                            target=self.ctx.story_path,
                            issue=(
                                f"the story's Status reads '{stamped.written}', which marks "
                                "it finished — story selection reads that line, so the story "
                                "is now invisible to every later loop and to QA"
                            ),
                            repair=(
                                "put the Status line back to the value it held before this "
                                "story's work — `git diff` on the story file shows it — and "
                                "record what was run as prose under `## Implementation "
                                "Status` instead. The workflow stamps the outcome itself, "
                                "and only from a QA run it performed"
                            ),
                        )
                    ],
                    layer.cwd,
                    lap.fix_lap,
                ),
                f"the story's Status was set to '{stamped.written}' before QA ran.",
                "the story status gate",
                index,
                impl_blocks,
                lap,
            )
        outcome = GateOutcome()
        for gate in GATE_ORDER:
            outcome = self.call(
                run_gate, layer.cwd, layer.service, gate, service_type=layer.type
            )
            if outcome.status == "dirty":
                break
        if outcome.status != "dirty":
            return Continue(outcome, self.layer, index=index, lap=lap)
        report = from_gate(outcome, layer.cwd, lap.fix_lap)
        failing = f"`{report.command}`" if report.command else f"the {outcome.gate} gate"
        return nodes.repair_or_escalate(
            self,
            report,
            f"{layer.service}: {failing} still fails after "
            f"{lap.fix_lap} repair lap(s).\n\n{report.output}",
            f"the {outcome.gate} gate",
            index,
            impl_blocks,
            lap,
        )

    def fix(
        self,
        index: int,
        lap: Lap,
        report: FailureReport = FailureReport(),
        impl_blocks: int = 0,
    ) -> Continue | Await:
        """Repair whatever the gate reported, then re-run the gates."""
        layer = nodes.current_layer(self)
        stalled = bool(lap.digest) and report.digest == lap.digest
        lap = nodes.spend(self, lap)
        turn = roles.turn(self, "dev-fix", returns=FixResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high" if stalled or lap.fix_lap >= 2 else "low",
            cwd=layer.cwd,
            add_dirs=workspace_dirs(self),
            args=turn.args | {
                "report": report.model_dump(),
                "changed_files": self.call(
                    changed_files, layer.cwd, self.ctx.story_slug, self.ctx.story_id
                ).paths,
                "service": layer.service,
                "epic": self.epic,
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
            },
            session=backbone(self),
        )
        if result.blocked:
            return nodes.gate_impl(
                self,
                result,
                result.notes
                or "the repair turn could not satisfy "
                + (f"`{report.command}`" if report.command else f"the {report.source} gate"),
                index,
                "the repair turn",
                impl_blocks,
                lap,
            )
        return Continue(
            result,
            self.gates,
            index=index,
            impl_blocks=impl_blocks,
            lap=lap.model_copy(
                update={"fix_lap": lap.fix_lap + 1, "digest": report.digest}
            ),
        )

    def resolve_impl(
        self, notes: str, index: int, where: str, impl_blocks: int = 0, lap: Lap = Lap()
    ) -> Continue | Await:
        """Resolve an implementation block from the record, or park for the operator."""
        result = nodes.resolver_turn(self, "implementation", notes)
        if answered(self, result, "implementation"):
            return Continue(
                result,
                self.read_operator_impl,
                index=index,
                impl_blocks=impl_blocks + 1,
                lap=lap,
            )
        gate = nodes.escalate(
            self, notes, impl_blocks, result, block_kind="implementation", where=where
        )
        return Await(
            context_path(self),
            gate.body,
            self.read_operator_impl,
            index=index,
            impl_blocks=impl_blocks + 1,
            lap=lap,
        )

    def read_operator_impl(
        self, index: int, impl_blocks: int = 0, lap: Lap = Lap()
    ) -> Continue | Done:
        """Consume the answer and re-enter the layer with it in hand."""
        answer = self.call(read_operator_context, self.ctx.story_path)
        if answer.scope == "epic":
            self.logger.info("operator scoped the fix to the epic — handing back to replan")
            return nodes.ends(self, DevResult(status="replan", operator_notes=answer.content))
        return Continue(
            answer,
            self.implement,
            index=index,
            operator_context=answer.content,
            impl_blocks=impl_blocks,
            lap=lap,
        )


__all__ = ["Dev"]
