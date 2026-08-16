"""`drive()` — the loop that turns a class of methods into a run.

It is `_step_loop` with a coarser node: checkpoint, run one state, read the transition
it returned, step. What changed is the unit. A YAML node is a step the engine composes;
a state is a step the *author* composes, with native control flow inside it, and the
only things that cross the persistence boundary are its name and its arguments.

Resume is coarse and there is no intra-state memo: resuming is calling that state again
with those parameters, and nothing inspects what the previous attempt got through. So
the checkpoint file is the whole of the resume state — there is no second, invisible
cache that can disagree with it — and state bodies must be idempotent rather than
merely deterministic.
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import TypeAdapter, ValidationError

from workhorse import control, gates, otel, reload
from workhorse.artifacts import ArtifactWriter
from workhorse.control import NULL_CHANNEL, ControlChannel, Request, wait_until
from workhorse.pyflow import activity as activity_log
from workhorse.pyflow.engine import Engine, RunEnv, jsonable
from workhorse.pyflow.errors import RunBudgetExceeded, WorkflowFailed
from workhorse.pyflow.transitions import Await, Continue, Done
from workhorse.pyflow.workflow import Workflow
from workhorse.records import Checkpoint, PyflowCheckpoint, parse_checkpoint
from workhorse.runner import ladder
from workhorse.runner.clock import SYSTEM_CLOCK, Clock

logger = logging.getLogger("workhorse.engine")

#: How often a still-waiting run says so, in seconds.
HEARTBEAT_S = 300.0


@dataclass
class Resume:
    """A checkpoint, read back."""

    state: str
    params: dict[str, Any]
    #: The workflow instance's own fields, as `model_dump(mode="json")` wrote them.
    #: A resume rebuilds the instance from these, not from `--params` — the run's
    #: inputs were fixed when it started and a later invocation must not change them.
    inputs: dict[str, Any] = field(default_factory=dict)
    ctx: Any = None
    #: `type(wf).__name__` of the flow that wrote it, so a bare `--resume-latest`
    #: re-enters that flow rather than the distribution's default one.
    flow: str | None = None
    waiting_on: str | None = None


def read_resume(checkpoint: Checkpoint) -> Resume:
    """Narrow a parsed `checkpoint.json` to what a resume needs.

    Refuses a YAML-engine checkpoint outright. The two engines share a runs directory
    and a `--resume-latest`, and a `current_id` is not a state name — resuming one from
    the other would either explode confusingly or, worse, match a name by coincidence.

    Everything else the old body checked — a present, non-empty `state`, `params` and
    `inputs` that are objects — the model checks on the way off disk, so what is left
    here is the one refusal that is a *policy* rather than a shape.
    """
    if not isinstance(checkpoint, PyflowCheckpoint):
        raise WorkflowFailed(
            "this run directory holds a checkpoint from the YAML engine "
            f"(node '{checkpoint.current_id}'), not a Python state machine. "
            "Resume it with the workflow that wrote it, or start a new run."
        )
    return Resume(
        state=checkpoint.state,
        params=checkpoint.params,
        inputs=checkpoint.inputs,
        ctx=checkpoint.ctx,
        flow=checkpoint.flow,
        waiting_on=checkpoint.waiting_on,
    )


def coerce_params(
    bound: Any, params: dict[str, Any], *, state: str
) -> dict[str, Any]:
    """Validate a checkpoint's params against the state's own signature.

    The third of the three moments arguments are checked — `ParamSpec` at author time,
    `signature.bind` at transition time, and this on the way back off disk. It is what
    pairs with the checkpoint being hand-editable: if a human is meant to edit it,
    something has to validate the edit. It also puts `"docs/epics"` back into a `Path`,
    which JSON cannot carry.
    """
    signature = inspect.signature(bound)
    unknown = sorted(set(params) - set(signature.parameters))
    if unknown:
        known = ", ".join(signature.parameters) or "(none)"
        raise WorkflowFailed(
            f"checkpoint gives state '{state}' the parameter(s) {', '.join(unknown)}, "
            f"which it does not have. Its parameters are: {known}."
        )
    try:
        hints = get_type_hints(bound)
    except Exception:  # noqa: BLE001 — an unresolvable annotation must not block a resume
        hints = {}

    coerced: dict[str, Any] = {}
    for name, value in params.items():
        annotation = hints.get(name)
        if annotation is None:
            coerced[name] = value
            continue
        try:
            coerced[name] = TypeAdapter(annotation).validate_python(value)
        except (ValidationError, TypeError) as exc:
            raise WorkflowFailed(
                f"checkpoint parameter '{name}' for state '{state}' is not a valid "
                f"{annotation}: {exc}"
            ) from exc

    missing = [
        name
        for name, parameter in signature.parameters.items()
        if parameter.default is inspect.Parameter.empty and name not in coerced
    ]
    if missing:
        raise WorkflowFailed(
            f"checkpoint does not give state '{state}' its required parameter(s): "
            f"{', '.join(missing)}"
        )
    return coerced


def _revive_ctx(wf: Workflow, raw: Any) -> Any:
    """Rebuild `self.ctx` from the checkpoint rather than re-running `setup()`.

    The tier table says `ctx` is written once, after setup. Calling `setup()` again on
    a resume would write it twice — and `setup()` is where a run decides things like
    its base branch, which must not be re-decided halfway through.
    """
    if raw is None:
        return None
    try:
        annotation = get_type_hints(type(wf).setup).get("return")
    except Exception:  # noqa: BLE001
        annotation = None
    if annotation is None:
        return raw
    try:
        return TypeAdapter(annotation).validate_python(raw)
    except (ValidationError, TypeError):
        return raw


def answered(path: Path) -> bool:
    """Whether the operator gate at `path` has actually been answered.

    The gate file carries its own state — `gates.format_operator_gate` writes
    `STATUS: AWAITING_OPERATOR`, groom's dashboard flips it to `ANSWERED`, and three
    workflows already read it — so *that* is the edge, not the file's mtime. Waiting on
    the mtime is what used to resume a run on an editor autosave, or on an operator
    saving half a thought: the answer was not written yet, but the file was touched.

    Anything other than an explicit `AWAITING_OPERATOR` counts as answered, including a
    file with no header at all. An operator who replaces the whole file with their answer
    has answered it, and `gates.status_of` deliberately reports "absent" rather than
    guessing, leaving that call here.
    """
    try:
        text = path.read_text()
    except OSError:
        # Not there yet: an `Await` with no questions can name a file the operator has
        # still to create, and a missing gate is unanswered rather than answered.
        return False
    return gates.status_of(text) != "AWAITING_OPERATOR"


def wait_for_answer(
    path: Path,
    *,
    interval: float,
    clock: Clock = SYSTEM_CLOCK,
    channel: ControlChannel = NULL_CHANNEL,
    log: logging.Logger | None = None,
    deadline: float | None = None,
) -> Request | None:
    """Block until the gate at `path` is answered, or a control request arrives.

    Two arms, and both are load-bearing. The re-read is *authoritative*: the answer is a
    file a human edits at leisure, possibly from a machine that can reach the run dir and
    nothing else, so a run has to resume on it whether or not anyone sends a message.
    The channel makes it *prompt*, and is what lets an operator reach a run that is
    otherwise going to sit here for days.

    A re-read rather than inotify, still: inotify is Linux-only — a runner that cannot
    wait for a human on macOS is not portable — and against a latency budget measured in
    days the two are indistinguishable.

    Returns the request that interrupted the wait, or None when the gate was answered.
    """
    log = log or logger
    waited = 0.0
    while True:
        if answered(path):
            log.info("[workhorse] await  → %s answered; resuming", path)
            return None
        if deadline is not None and clock.now().timestamp() > deadline:
            raise WorkflowFailed(
                f"run exceeded its wall-clock budget while waiting on {path}"
            )
        request = wait_until(
            lambda: answered(path),
            timeout=interval,
            clock=clock,
            channel=channel,
            tick=interval,
        )
        if request is not None:
            return request
        waited += interval
        if waited % HEARTBEAT_S < interval:
            # Names the condition, not just the file: an operator who edited the gate
            # without flipping its status is the one case this wait will not end on its
            # own, and this line is where they find that out.
            log.info(
                "[workhorse] await  → still waiting for STATUS: ANSWERED in %s (%ds)",
                path,
                int(waited),
            )


def _ask(path: Path, questions: str, log: logging.Logger) -> None:
    """Write the ask, so the operator has something to answer."""
    if questions:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(gates.format_operator_gate(questions))


def _resume_in_place(wf: Workflow, env: RunEnv) -> Resume | None:
    """A sub-flow's own checkpoint, read back because its parent is re-entering it.

    Only `handoff` asks for this, and only for the state a resume re-entered. Three
    things have to agree before the checkpoint is adopted, because the same file is
    also what a *finished* visit leaves behind: it has to be a pyflow checkpoint, it
    has to name this class, and its inputs have to be the ones this invocation was
    constructed with. The last is what keeps a loop that runs the same flow per story
    from resuming story A's checkpoint into story B.

    Every disagreement — including an unreadable file — starts the child clean rather
    than raising: a resume that cannot reuse the child's progress is slower, and one
    that cannot start at all is a dead unattended run.
    """
    path = env.run_dir / ArtifactWriter.CHECKPOINT_FILE
    try:
        checkpoint = parse_checkpoint(path.read_text())
    except (OSError, ValidationError) as exc:
        if path.exists():
            env.log.warning("[workhorse] ignoring unreadable sub-flow checkpoint: %s", exc)
        return None
    flow_name = type(wf).__name__
    if not isinstance(checkpoint, PyflowCheckpoint) or checkpoint.flow != flow_name:
        env.log.info("[workhorse] %s starts fresh: its checkpoint is another flow's", flow_name)
        return None
    if checkpoint.inputs != wf.model_dump(mode="json"):
        env.log.info(
            "[workhorse] %s starts fresh: its checkpoint belongs to a different "
            "invocation of the same flow",
            flow_name,
        )
        return None
    return read_resume(checkpoint)


def drive(
    wf: Workflow, env: RunEnv, resume: Resume | None = None, *, resume_in_place: bool = False
) -> Any:
    """Run `wf` to a `Done`, returning its result.

    `resume_in_place` is the sub-flow spelling of `resume`: the caller has no
    checkpoint in hand, only the knowledge that this flow is being re-entered after a
    kill, so the checkpoint is read from the scope the child writes into.
    """
    if env.driver is None:
        env.driver = drive
    wf._bind(Engine(env))

    if resume is None and resume_in_place:
        resume = _resume_in_place(wf, env)

    if resume is not None:
        wf._seal(_revive_ctx(wf, resume.ctx))
        state, params = resume.state, resume.params
        env.log.info("[workhorse] resume → state '%s'", state)
    else:
        wf._seal(wf.setup())
        state, params = wf.start_state, {}

    resuming = resume is not None
    inputs = wf.model_dump(mode="json")
    ctx_payload = _ctx_payload(wf)
    flow_name = type(wf).__name__
    budget = type(wf).max_transitions or env.config.max_transitions
    # One tracker per logger, so an activity a sub-flow sets survives the parent's
    # next transition instead of being published over by a second instance.
    activity = activity_log.install(env.log)

    for _ in range(budget):
        spec = type(wf).resolve_state(state)
        bound = getattr(wf, spec.name)
        kwargs = coerce_params(bound, params, state=spec.name)

        activity.rebase({**env.labels, **_labels(wf, env.log, kwargs)})
        # Commit the position *before* the budget check, not after. A `Continue`'s params
        # are only durable once some iteration checkpoints them, and this is that write —
        # so a check that raises first discards the transition that produced them, and the
        # resume replays the state it already ran with the arguments it had on entry. That
        # is not merely wasted work: the replayed state is handed *stale* arguments, so a
        # gate's findings vanish and the next turn is told there were none. (Seen for real:
        # a QA plan turn spent nine minutes, its validator emitted 24 diagnostics, the clock
        # ran out on the transition carrying them, and the resumed turn — told the loop was
        # clean — reported "no changes needed" and burned another pass.) Writing first costs
        # one checkpoint on the aborting iteration and keeps the module's own invariant:
        # state parameters *are* the checkpoint.
        state_seq = env.writer.write_state_checkpoint(
            spec.name, jsonable(params), inputs=inputs, flow=flow_name, ctx=ctx_payload
        )
        if env.deadline is not None and env.clock.now().timestamp() > env.deadline:
            raise RunBudgetExceeded(
                "run exceeded its WORKHORSE_MAX_RUNTIME_S wall-clock budget, counted "
                "from the run's original start. Raise the budget and resume."
            )
        # The boundary half of the reload. The stream loop cuts a turn that is burning
        # tokens; this catches every other moment — a request that arrived while a
        # script node ran, and the `--at-boundary` request the stream loop deliberately
        # ignores. It sits *after* the checkpoint above, so the state about to run is
        # already durable and the re-entry replays it having lost nothing. The request
        # carries what it asked for on the exception, because the request came off the
        # channel and there is nothing left on disk for the unwind to re-read.
        boundary = reload.boundary_requested()
        if boundary is not None and boundary.action == reload.SWITCH_PROFILE:
            # Applied here, in this process, rather than re-entering: the profile is
            # re-read and re-narrowed on every turn, so assigning the name is the whole
            # switch. `reload.boundary_requested` deliberately left it unanswered — this
            # is the frame that knows whether it could be applied, and a refusal
            # acknowledged as a success would leave a week-long run spending on the models
            # nobody chose.
            reply = ladder.switch_profile(env.agent_runner, boundary.profile)
            if reply.get("ok"):
                env.log.info(
                    "[workhorse] profile → '%s' from the next turn on", boundary.profile
                )
            else:
                env.log.warning("[workhorse] profile → refused: %s", reply.get("error"))
            control.answer(reply)
        elif boundary is not None:
            env.log.info("[workhorse] reload → requested; re-entering at '%s'", spec.name)
            raise reload.ReloadRequested(
                f"reload requested at the boundary before {spec.name}",
                core=boundary.core,
                cli=boundary.cli,
            )
        env.log.info("[workhorse] state  → %s", spec.name)
        # Armed for the resumed state only — see `RunEnv.resume_pending`. A state
        # further along the run is being entered for the first time, and a handoff it
        # makes is a fresh invocation whatever a stale child checkpoint says.
        env.resume_pending = resuming
        # The state's own span, and every node span its body leaves open, close in
        # this scope's `finally` — at the depth that opened them, carrying the error
        # on the innermost frame only. The reload path below restores the depth
        # itself, which leaves the scope a no-op there.
        with otel.scope():
            otel.state_start(spec.name, state_seq)
            try:
                outcome = bound(**kwargs)
            except reload.ReloadRequested:
                # Every `drive` frame closes its own scope on the way out, innermost first:
                # a handoff runs a nested `drive` inside this state's body, so the unwind
                # passes through one of these per level. `_end_execution` also sweeps
                # whatever this frame left open above it — the agent node's own span, which
                # never received the `done` event that normally ends it, because the turn
                # was cut. So a reload exports the same span tree a completed transition
                # does, minus the outcome attribute it never earned. That is the point: an
                # operator who reloads a broken flow must not pay for it in spans that never
                # leave the process, which is exactly what makes a reload read as a crash.
                #
                # They close marked, not bare: a node visit that ended here did not finish
                # its work, and a reader with only the two timestamps cannot tell that from
                # one that did. Unmarked, five reloads of a flow an operator is fixing are
                # five completed visits to the same node on the same labels — groom's churn
                # rule, i.e. the reload paging as the loop it exists to break.
                otel.state_end(spec.name, state_seq, None, cut="reload")
                raise
        resuming = env.resume_pending = False

        if not isinstance(outcome, (Continue, Done, Await)):
            raise WorkflowFailed(
                f"state '{spec.name}' returned {outcome!r} — a state must return "
                "Continue(...), Done(...) or Await(...), or raise WorkflowFailed"
            )
        next_state = outcome.state if isinstance(outcome, (Continue, Await)) else None
        otel.state_end(spec.name, state_seq, next_state)

        if isinstance(outcome, Done):
            env.writer.write_final_context({"result": _result_payload(outcome.result)})
            env.writer.finish("terminal")
            return outcome.result

        if isinstance(outcome, Await):
            _ask(outcome.path, outcome.questions, env.log)
            env.writer.write_state_checkpoint(
                outcome.state,
                jsonable(outcome.params),
                inputs=inputs,
                flow=flow_name,
                ctx=ctx_payload,
                waiting_on=str(outcome.path),
            )
            env.log.info("[workhorse] await  → blocked on %s", outcome.path)
            with otel.wait("operator", spec.name):
                wait_for_answer(
                    outcome.path,
                    interval=env.config.await_poll_s,
                    clock=env.clock,
                    log=env.log,
                    deadline=env.deadline,
                )
        state, params = outcome.state, outcome.params

    raise WorkflowFailed(
        f"transition budget exhausted after {budget} transitions (last state "
        f"'{state}'). Raise WORKHORSE_MAX_TRANSITIONS if the run is genuinely that "
        "long, or look for two states handing each other back and forth."
    )


def _labels(wf: Workflow, log: logging.Logger, params: dict[str, Any]) -> dict[str, str]:
    """The workflow's own telemetry dimensions. A label that throws costs one
    attribute and nothing else — never the run.

    `params` is what the state about to run was bound with, passed through so a
    workflow can report which attempt of a bounded budget this is. It is the
    workflow's data and the engine does not read it. `state_labels` defaults to
    `labels()`, so a workflow that needs neither pays nothing for either.
    """
    try:
        declared = wf.state_labels(params)
    except Exception as exc:  # noqa: BLE001 — instrumentation must not fail a run
        log.debug("[workhorse] labels() raised: %s", exc)
        return {}
    return {str(k): str(v) for k, v in (declared or {}).items() if v not in (None, "")}


def _ctx_payload(wf: Workflow) -> Any:
    ctx = wf.ctx
    if ctx is None:
        return None
    dump = getattr(ctx, "model_dump", None)
    return dump(mode="json") if callable(dump) else ctx


def _result_payload(result: Any) -> Any:
    dump = getattr(result, "model_dump", None)
    return dump(mode="json") if callable(dump) else result
