"""`drive()` — the loop that turns a class of methods into a run."""
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
from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK, Clock

logger = logging.getLogger("workhorse.engine")

HEARTBEAT_S = 300.0


@dataclass
class Resume:
    """A checkpoint, read back."""

    state: str
    params: dict[str, Any]
    inputs: dict[str, Any] = field(default_factory=dict)
    ctx: Any = None
    flow: str | None = None
    waiting_on: str | None = None


def read_resume(checkpoint: Checkpoint) -> Resume:
    """Narrow a parsed `checkpoint.json` to what a resume needs."""
    if not isinstance(checkpoint, PyflowCheckpoint):
        raise WorkflowFailed(
            "this run directory holds a checkpoint from the YAML engine "
            f"(node '{checkpoint.current_id}'), not a Python state machine. "
            "Resume it with the workflow that wrote it, or start a new run.",
            failure_class="yaml-engine-checkpoint",
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
    """Validate a checkpoint's params against the state's own signature."""
    signature = inspect.signature(bound)
    unknown = sorted(set(params) - set(signature.parameters))
    if unknown:
        known = ", ".join(signature.parameters) or "(none)"
        raise WorkflowFailed(
            f"checkpoint gives state '{state}' the parameter(s) {', '.join(unknown)}, "
            f"which it does not have. Its parameters are: {known}.",
            failure_class="unknown-checkpoint-param",
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
                f"{annotation}: {exc}",
                failure_class="invalid-checkpoint-param",
            ) from exc

    missing = [
        name
        for name, parameter in signature.parameters.items()
        if parameter.default is inspect.Parameter.empty and name not in coerced
    ]
    if missing:
        raise WorkflowFailed(
            f"checkpoint does not give state '{state}' its required parameter(s): "
            f"{', '.join(missing)}",
            failure_class="missing-checkpoint-param",
        )
    return coerced


def _revive_ctx(wf: Workflow, raw: Any) -> Any:
    """Rebuild `self.ctx` from the checkpoint rather than re-running `setup()`."""
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
    """Whether the operator gate at `path` has actually been answered."""
    try:
        text = path.read_text()
    except OSError:
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
    kind: str = "operator",
) -> Request | None:
    """Block until the gate at `path` is answered, or a control request arrives."""
    log = log or logger
    waited = 0.0
    operator = kind == "operator"
    if operator:
        since = clock.now().isoformat()
        control.questions_with(lambda: _pending_gate(path, kind, since))
    try:
        while True:
            if answered(path):
                log.info("[workhorse] await  → %s answered; resuming", path)
                return None
            if deadline is not None and clock.now().timestamp() > deadline:
                raise WorkflowFailed(
                    f"run exceeded its wall-clock budget while waiting on {path}",
                    failure_class="await-deadline-exceeded",
                    artifacts={"gate": str(path)},
                )
            request = wait_until(
                lambda: answered(path),
                timeout=interval,
                clock=clock,
                channel=channel,
                tick=interval,
            )
            if request is not None:
                if request.action != control.ANSWER:
                    return request
                if operator:
                    _consume_answer(request, path, channel, log)
                else:
                    channel.reply(
                        {
                            "ok": False,
                            "error": "this run is not blocked on an operator gate "
                            "right now",
                        }
                    )
                continue
            waited += interval
            if waited % HEARTBEAT_S < interval:
                condition = (
                    "STATUS: ANSWERED in" if operator else "the job to finish in"
                )
                log.info(
                    "[workhorse] await  → still waiting for %s %s (%ds)",
                    condition,
                    path,
                    int(waited),
                )
    finally:
        if operator:
            control.questions_with(None)


def _pending_gate(path: Path, kind: str, since: str) -> list[dict[str, object]]:
    """What this run is blocked on, for the channel's `questions` verb."""
    if answered(path):
        return []
    return [{"path": str(path), "question": _wait_question(path), "kind": kind, "since": since}]


def _gate_question(path: Path) -> str:
    """Read the durable question, including any earlier exchanges on this gate."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _wait_question(path: Path) -> str:
    """The open question on `path`, bounded, for the readers this run tells.

    A gate accumulates every exchange it has ever held, so its whole text is the wrong
    payload for a wait span or a `questions` reply. Both carry the gate's path, so a
    reader that wants the history reads it from disk.
    """
    return gates.latest_question(_gate_question(path))


def _consume_answer(
    request: Request, path: Path, channel: ControlChannel, log: logging.Logger
) -> None:
    """One `answer` request, judged and — when it is this gate's — written to disk."""
    asked = str(path)
    if request.path and request.path != asked:
        channel.reply(
            {"ok": False, "error": f"this run is waiting on {asked}, not {request.path}"}
        )
        return
    if answered(path):
        channel.reply({"ok": False, "error": "already answered"})
        return
    try:
        text = path.read_text()
    except OSError:
        text = ""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(gates.apply_answer(text, request.body))
    except OSError as exc:
        channel.reply({"ok": False, "error": f"could not write the gate file: {exc}"})
        return
    channel.reply({"ok": True, "path": asked})
    log.info("[workhorse] await  → %s answered over the control socket", path)


def _park(path: Path, env: RunEnv, *, kind: str) -> None:
    """Block on `path` until answered, honouring control requests while parked."""
    while True:
        interrupted = wait_for_answer(
            path,
            interval=env.config.await_poll_s,
            clock=env.clock,
            channel=control.armed(),
            log=env.log,
            deadline=env.deadline,
            kind=kind,
        )
        if interrupted is None:
            return
        cut = reload.cut_by(interrupted)
        if cut is not None:
            env.log.info("[workhorse] reload → requested while parked on %s", path)
            raise reload.ReloadRequested(
                f"reload requested while parked on {path}",
                core=cut.core,
                cli=cut.cli,
            )


def _ask(path: Path, questions: str, log: logging.Logger) -> None:
    """Write the ask, so the operator has something to answer."""
    if not questions:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = path.read_text()
    except OSError:
        existing = ""
    if existing.strip():
        path.write_text(gates.append_operator_gate(existing, questions))
    else:
        path.write_text(gates.format_operator_gate(questions))


def _resume_in_place(wf: Workflow, env: RunEnv) -> Resume | None:
    """A sub-flow's own checkpoint, read back because its parent is re-entering it."""
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
    """Run `wf` to a `Done`, returning its result."""
    if env.driver is None:
        env.driver = drive
    wf._bind(Engine(env))

    if resume is None and resume_in_place:
        resume = _resume_in_place(wf, env)

    if resume is not None:
        wf._seal(_revive_ctx(wf, resume.ctx))
        state, params = resume.state, resume.params
        env.log.info("[workhorse] resume → state '%s'", state)
        if resume.waiting_on is not None:
            gate = Path(resume.waiting_on)
            try:
                parked = gates.status_of(gate.read_text()) == "AWAITING_OPERATOR"
            except OSError:
                parked = False
            if parked:
                env.log.info("[workhorse] resume → still parked on %s", gate)
                with otel.wait("operator", state, str(gate), _wait_question(gate)):
                    _park(gate, env, kind="operator")
    else:
        wf._seal(wf.setup())
        state, params = wf.start_state, {}

    resuming = resume is not None
    why = ""
    inputs = wf.model_dump(mode="json")
    ctx_payload = _ctx_payload(wf)
    flow_name = type(wf).__name__
    budget = type(wf).max_transitions or env.config.max_transitions
    refuel_on = type(wf).REFUEL_ON
    remaining, refuel_token = budget, None
    activity = activity_log.install(env.log)

    while True:
        token = _refuel_token(refuel_on, params)
        if token is not None and token != refuel_token:
            if refuel_token is not None:
                env.log.debug("[workhorse] refuel → %s (%s)", token, state)
                otel.gas_refuel(state)
            refuel_token, remaining = token, budget
        if remaining <= 0:
            break
        remaining -= 1
        spec = type(wf).resolve_state(state)
        bound = getattr(wf, spec.name)
        kwargs = coerce_params(bound, params, state=spec.name)

        activity.rebase({**env.labels, **_labels(wf, env.log, kwargs)})
        state_seq = env.writer.write_state_checkpoint(
            spec.name, jsonable(params), inputs=inputs, flow=flow_name, ctx=ctx_payload
        )
        if env.deadline is not None and env.clock.now().timestamp() > env.deadline:
            raise RunBudgetExceeded(
                "run exceeded its WORKHORSE_MAX_RUNTIME_S wall-clock budget, counted "
                "from the run's original start. Raise the budget and resume."
            )
        boundary = reload.boundary_requested()
        if boundary is not None and boundary.action == reload.SWITCH_PROFILE:
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
        env.log.info("[workhorse] state  → %s%s", spec.name, _because(why))
        env.resume_pending = resuming
        with otel.scope():
            otel.state_start(spec.name, state_seq)
            try:
                outcome = bound(**kwargs)
            except reload.ReloadRequested:
                otel.state_end(spec.name, state_seq, None, cut="reload")
                raise
        resuming = env.resume_pending = False

        if not isinstance(outcome, (Continue, Done, Await)):
            raise WorkflowFailed(
                f"state '{spec.name}' returned {outcome!r} — a state must return "
                "Continue(...), Done(...) or Await(...), or raise WorkflowFailed",
                failure_class="invalid-state-return",
            )
        next_state = outcome.state if isinstance(outcome, (Continue, Await)) else None
        otel.state_end(spec.name, state_seq, next_state)

        if isinstance(outcome, Done):
            env.log.info("[workhorse] done   ← %s%s", spec.name, _because(outcome.reason))
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
            verb = "blocked on" if outcome.kind == "operator" else "waiting on"
            env.log.info(
                "[workhorse] await  → %s %s%s", verb, outcome.path, _because(outcome.reason)
            )
            with otel.wait(
                outcome.kind,
                spec.name,
                str(outcome.path),
                _wait_question(outcome.path) if outcome.kind == "operator" else "",
            ):
                _park(outcome.path, env, kind=outcome.kind)
        state, params, why = outcome.state, outcome.params, outcome.reason

    spent = (
        f"{budget} transitions without forward progress "
        f"(the last one this run recorded was {refuel_token})"
        if refuel_on
        else f"{budget} transitions"
    )
    raise WorkflowFailed(
        f"transition budget exhausted after {spent} (last state "
        f"'{state}'). Raise WORKHORSE_MAX_TRANSITIONS if the run is genuinely that "
        "long, or look for two states handing each other back and forth.",
        failure_class="transition-budget-exhausted",
    )


def _refuel_token(keys: frozenset[str], params: dict[str, Any]) -> str | None:
    """The value of `keys` in `params`, as one comparable string — or `None`."""
    if not keys:
        return None
    seen = {k: params[k] for k in sorted(keys) if k in params}
    if not seen:
        return None
    return repr(jsonable(seen))


def _labels(wf: Workflow, log: logging.Logger, params: dict[str, Any]) -> dict[str, str]:
    """The workflow's own telemetry dimensions."""
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


def _because(reason: str) -> str:
    """The ` — <reason>` tail a log line carries when the transition said why."""
    return f" — {reason}" if reason else ""


def _result_payload(result: Any) -> Any:
    dump = getattr(result, "model_dump", None)
    return dump(mode="json") if callable(dump) else result
