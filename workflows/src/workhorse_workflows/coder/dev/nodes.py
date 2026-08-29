"""The deterministic parts of the dev lane, and the budgets that bound it.

A state in `flow.py` is a state-machine jump: it decides where the run goes next and
says so with `Continue`, `Await` or `Done`. Everything it needs on the way — the
conversation keys, the two agent turns that have more than one call site, the operator
gate's routing, the arguments assembled from a recorded output — is here, as module
functions taking the workflow handle. That is `shared/escalation.py::escalation`'s shape,
and it is what keeps a state readable as a graph edge rather than as a page of setup.

The budgets are constants rather than workflow fields because none of them is a knob
anybody turns per run: a field is a value the operator can set with `--param`, and an
operator who lowers the repair budget has not made the run cheaper, only made it park
sooner. What *is* a field is a frozen run input — which story, which docs root, which
branch.
"""
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

#: `timeout: infinity` — the resolver stands in for a human and must not be cut off
#: mid-resolution. A finite number of seconds here caps it.
UNBOUNDED = float("inf")

#: Repair laps a service layer gets across **all** its gates before the block goes to the
#: operator. One budget rather than one per gate: three failing gates repaired twice each
#: is six turns on one layer, and what the budget protects against is the lap, not the
#: linter.
MAX_FIX_LAPS = 3

#: How many turns the story's conversation carries before it is recycled. A conversation
#: that has read the whole service is what makes lap two cheap, and — several layers and
#: several laps later — it is also what makes every later turn re-read a context nobody
#: has needed since. `changed_files` re-seeds the fresh one. 0 never recycles.
MAX_SESSION_TURNS = 8

#: Path-validation rework passes before the block goes to the operator.
MAX_VALIDATE_REWORKS = 3

#: Trips through an operator gate that get a resolver turn before every further block goes
#: straight to a human — not a cap on how many times a stage may block; there isn't one.
#: See AGENTS.md: every lane caps the resolver, never the block.
MAX_PLAN_BLOCKS = 3

#: The operator modes that skip the resolver entirely and park for a person.
HUMAN_MODES = frozenset({"human", "operator"})


def repair_chain(flow: Dev, worklist: str) -> str:
    """The session chain a plan-repair loop runs on, keyed per story and per worklist.

    Per story because two stories planned by one run are two different plans against two
    different diffs; per worklist because the loops that re-plan are asking for unrelated
    things. Sharing one key across them would hand the path-repair pass the operator's
    answer to a block it was never told about — stale context each loop's arguments
    deliberately withhold.
    """
    return f"plan-{worklist}:{flow.ctx.story_slug}"


def spend(flow: Dev, lap: Lap) -> Lap:
    """Count one turn onto the story conversation, recycling it when it is full."""
    turns = spend_turn(flow, backbone(flow), lap.session_turns, MAX_SESSION_TURNS)
    return lap.model_copy(update={"session_turns": turns})


def ends(flow: Dev, result: DevResult, session_turns: int = 0) -> Done:
    """End the flow, and every plan-repair chain it opened with it.

    A chain outliving its flow is what makes a re-run of the same story resume a
    conversation about a plan that has since been rewritten. The backbone is the
    exception: it is left open for the lanes after this one, which find it under the same
    story-derived key. `result.session_turns` carries how much of the recycle budget that
    conversation has already spent, so the review lane's apply turns continue the count.
    """
    for worklist in ("block-repair", "path-repair"):
        flow.reset_session(repair_chain(flow, worklist))
    result.session_turns = session_turns
    return Done(result)


def current_layer(flow: Dev) -> DispatchEntry:
    """The service layer being implemented, off `select_next_layer`'s recorded output.

    Read back rather than threaded through the implement/gate/fix states: it is an
    eleven-field record those states merely *consume*, and nothing between here and the
    next `layer` call can change which layer is current.
    """
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
    """The gate body for a block in this lane — see `coder.shared.escalation`.

    `block_kind` and `where` are parameters rather than the constants they were, because
    the plan stage is not the only thing in this flow that can block: any node reporting
    it cannot finish escalates through here, and the operator's first question is which
    one did.
    """
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
    """Investigate a block and either resolve it from the record or hand it on.

    Smart, and unbounded: it is standing in for the person who would otherwise be woken,
    with full tool access, on the highest-stakes decision in the flow. The two call sites
    differ only in which stage blocked.
    """
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
    """Hand a plan block to the resolver, or straight to a human.

    There is no dead end: a block always reaches a human eventually, either through the
    resolver or directly once `MAX_PLAN_BLOCKS` resolver turns are spent — never a
    terminal failure. `result` is unused on the human arm, and threaded through so the
    resolver arm can still `Continue` it into `resolve_plan`.
    """
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
    """Route a gate that said no: another repair lap while the budget holds, else the operator.

    Every gate in this lane converges here, so a gate added later — a command, a shape check
    on something the run parses — inherits the budget and the escalation without restating
    either, and `fix` keeps having one entry point.

    The budget bounds the *lap*, never the story: a spent budget hands the failing gate to
    the resolver and, failing that, to a human, exactly as a blocked implement turn does.
    See AGENTS.md, "a workflow never gives up".
    """
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
    """The same gate for the implementation half — a turn said it could not.

    An implementation turn reporting `blocked` used to be discarded, so the layer went on
    to lint a change nobody had written and the run reported success several stages later.
    A gate whose repair budget is spent, and a repair turn that reports it cannot repair,
    arrive here too: a spent budget is a block, not a failure, so it parks for someone who
    can decide it rather than ending the run.

    There is no fix-demand arm here even when the turn carried findings. The evidence test
    in `CoderResult.actionable` decides *who* a block is routed to, and an implement
    turn's owner is itself: routing its own findings back to the same prompt is precisely
    the lap it just declared futile.
    """
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
    """One re-planning turn, for whichever of the two reasons the caller is here for.

    The flow knows why it is dispatching, so it names the prompt rather than describing
    both arrivals to the agent and asking it to sniff which one this is:
    `repair-plan-paths` is a string edit against a validator's complaint,
    `replan-with-answer` is real planning around a decision the plan could not make. That
    is also why `power` differs, and why `worklist` does — the loops lap on unrelated
    things, so each resumes its own conversation and neither inherits the other's.
    """
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
    """The structural half of a plan turn's reply, as the transition carries it.

    `status` and `summary` are the turn's report on itself and say nothing about what was
    planned; the rest is the plan. Splitting them here keeps a checkpoint's transition
    arguments to the value the next state actually needs.
    """
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
    """The `implement-plan.md` turn for the current layer.

    The result is returned rather than discarded, which is the whole of this lane's
    root-cause bug: a turn that reported it could not implement the plan was thrown away,
    and the layer proceeded to lint an unwritten change.
    """
    layer = current_layer(flow)
    impl = flow.output(resolve_impl_context)
    gates = flow.call(declared_gates, layer.cwd, layer.service, service_type=layer.type)
    turn = roles.turn(flow, "implement-plan", returns=ImplResult)
    return flow.agent(
        turn.prompt,
        returns=turn.returns,
        # high: writes the production change, across whatever the plan touches.
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
