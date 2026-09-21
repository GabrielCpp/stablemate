"""The deterministic parts of the dev lane, and the budgets that bound it."""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from workhorse.pyflow import Await, Continue, Done

from workhorse_workflows.coder.shared import roles
from workhorse_workflows.coder.shared.conversation import backbone, spend_turn
from workhorse_workflows.coder.shared.dev import (
    declared_gates,
    read_plan_text,
    resolve_impl_context,
    select_next_layer,
)
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.resolution import RESOLVER_POWER, resolver_args
from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding
from workhorse_workflows.coder.shared.schemas.dev import (
    DevResult,
    DispatchEntry,
    FailureReport,
    ImplResult,
    Lap,
    OperatorGate,
    OperatorResolution,
    PlanResult,
)
from workhorse_workflows.coder.shared.story import workspace_dirs

if TYPE_CHECKING:
    from workhorse_workflows.coder.dev.flow import Dev

UNBOUNDED = float("inf")

MAX_FIX_LAPS = 3

MAX_SESSION_TURNS = 8

MAX_VALIDATE_REWORKS = 3

MAX_PLAN_BLOCKS = 3

HUMAN_MODES = frozenset({"human", "operator"})


def repair_chain(flow: Dev, worklist: str) -> str:
    """The session chain a plan-repair loop runs on, keyed per story and per worklist."""
    return f"plan-{worklist}:{flow.ctx.story_slug}"


def spend(flow: Dev, lap: Lap) -> Lap:
    """Count one turn onto the story conversation, recycling it when it is full."""
    turns = spend_turn(flow, backbone(flow), lap.session_turns, MAX_SESSION_TURNS)
    return lap.model_copy(update={"session_turns": turns})


def ends(flow: Dev, result: DevResult, session_turns: int = 0) -> Done:
    """End the flow, and every plan-repair chain it opened with it."""
    for worklist in ("block-repair", "path-repair"):
        flow.reset_session(repair_chain(flow, worklist))
    result.session_turns = session_turns
    return Done(result)


def current_layer(flow: Dev) -> DispatchEntry:
    """The service layer being implemented, off `select_next_layer`'s recorded output."""
    return flow.output(select_next_layer).layer


def escalate(
    flow: Dev,
    notes: str,
    number: int,
    result: OperatorResolution | None = None,
    block_kind: str = "plan",
    where: str = "the plan stage",
    findings: Sequence[Finding] = (),
) -> OperatorGate:
    """The gate body for a block in this lane — see `coder.shared.escalation`."""
    return escalation(
        flow,
        block_kind=block_kind,
        where=where,
        notes=notes,
        number=number,
        result=result,
        findings=findings,
    )


def resolver_turn(flow: Dev, block_kind: str, notes: str) -> OperatorResolution:
    """Investigate a block and either resolve it from the record or hand it on."""
    flow.logger.info("resolving the %s block", block_kind, extra={"activity": True})
    return flow.agent(
        "shared/prompts/resolve-operator.md",
        returns=OperatorResolution,
        power=RESOLVER_POWER,
        timeout=UNBOUNDED,
        add_dirs=workspace_dirs(flow),
        args=resolver_args(
            flow, block_kind=block_kind, notes=notes, docs_path=flow.docs_path
        ),
    )


def gate_plan(
    flow: Dev, result: object, notes: str, plan_blocks: int
) -> Continue | Await:
    """Hand a plan block to the resolver, or straight to a human."""
    if flow.operator_mode in HUMAN_MODES or plan_blocks >= MAX_PLAN_BLOCKS:
        gate = escalate(flow, notes, plan_blocks)
        return Await(
            context_path(flow),
            gate.body,
            flow.read_operator,
            notes=notes,
            plan_blocks=plan_blocks,
        )
    return Continue(result, flow.resolve_plan, notes=notes, plan_blocks=plan_blocks)


def repair_or_escalate(
    flow: Dev,
    report: FailureReport,
    notes: str,
    where: str,
    index: int,
    impl_blocks: int,
    lap: Lap,
) -> Continue | Await:
    """Route a gate that said no: another repair lap while the budget holds, else the operator."""
    if lap.fix_lap < MAX_FIX_LAPS:
        return Continue(
            report, flow.fix, index=index, impl_blocks=impl_blocks, lap=lap, report=report
        )
    return gate_impl(flow, report, notes, index, where, impl_blocks, lap)


def gate_impl(
    flow: Dev,
    result: CoderResult,
    notes: str,
    index: int,
    where: str,
    impl_blocks: int,
    lap: Lap,
) -> Continue | Await:
    """The same gate for the implementation half — a turn said it could not."""
    if flow.operator_mode in HUMAN_MODES or impl_blocks >= MAX_PLAN_BLOCKS:
        gate = escalate(
            flow,
            notes,
            impl_blocks,
            block_kind="implementation",
            where=where,
            findings=result.actionable,
        )
        return Await(
            context_path(flow),
            gate.body,
            flow.read_operator_impl,
            index=index,
            impl_blocks=impl_blocks,
            lap=lap,
        )
    return Continue(
        result,
        flow.resolve_impl,
        notes=notes,
        index=index,
        where=where,
        impl_blocks=impl_blocks,
        lap=lap,
    )


def refine(
    flow: Dev,
    role: str,
    *,
    review_notes: str,
    operator_context: str = "",
    worklist: str,
    power: str = "high",
) -> PlanResult:
    """One re-planning turn, for whichever of the two reasons the caller is here for."""
    turn = roles.turn(flow, role, returns=PlanResult)
    return flow.agent(
        turn.prompt,
        returns=turn.returns,
        power=power,
        add_dirs=workspace_dirs(flow),
        args=turn.args | {
            "story_slug": flow.ctx.story_slug,
            "story_id": flow.ctx.story_id or flow.ctx.story_slug,
            "epic": flow.epic,
            "story_path": flow.ctx.story_path,
            "spec_dir": flow.ctx.spec_dir,
            "review_notes": review_notes,
            "operator_context": operator_context,
        },
        session=repair_chain(flow, worklist),
    )


def plan_arg(result: PlanResult) -> dict:
    """The structural half of a plan turn's reply, as the transition carries it."""
    return result.model_dump(
        include={
            "services",
            "implementation_order",
            "shared_packages",
            "verification_setup",
            "fixtures",
        }
    )


def implement_layer(flow: Dev, operator_context: str) -> ImplResult:
    """The `implement-plan.md` turn for the current layer."""
    layer = current_layer(flow)
    impl = flow.output(resolve_impl_context)
    gates = flow.call(declared_gates, layer.cwd, layer.service, service_type=layer.type)
    turn = roles.turn(flow, "implement-plan", returns=ImplResult)
    return flow.agent(
        turn.prompt,
        returns=turn.returns,
        power="high",
        session=backbone(flow),
        cwd=layer.cwd,
        add_dirs=workspace_dirs(flow),
        args=turn.args | {
            "story_slug": flow.ctx.story_slug,
            "story_id": flow.ctx.story_id or flow.ctx.story_slug,
            "epic": flow.epic,
            "story_path": flow.ctx.story_path,
            "spec_dir": flow.ctx.spec_dir,
            "plan_file": layer.plan_file,
            "plan_text": read_plan_text(flow.ctx.spec_dir, layer.plan_file, flow.logger),
            "service_path": layer.service_path,
            "service_type": layer.type,
            "verification": layer.verification,
            "qa_run_plan": impl.qa_run_plan,
            "verification_setup": impl.verification_setup,
            "gates": gates.text,
            "operator_context": operator_context,
        },
    )


__all__ = [
    "HUMAN_MODES",
    "MAX_FIX_LAPS",
    "MAX_PLAN_BLOCKS",
    "MAX_SESSION_TURNS",
    "MAX_VALIDATE_REWORKS",
    "UNBOUNDED",
    "current_layer",
    "ends",
    "escalate",
    "gate_impl",
    "gate_plan",
    "implement_layer",
    "plan_arg",
    "refine",
    "repair_chain",
    "repair_or_escalate",
    "resolver_turn",
    "spend",
]
