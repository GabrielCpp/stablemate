"""What `self.call` / `self.agent` / `self.handoff` / `self.output` actually do.

The seams exist so that a node gets three things a direct function call cannot: its
own event in `events.jsonl`, a recorded `output.json` that `self.output(...)` can read
back, and — the payoff — resolution through the run's node index rather than through
the function object the callsite happened to hold.

That last one is why `--dry-run` is not an `if` in here. A dry run is the same code
path with a substituted index (see `stub_nodes`), which is also what a test supplies
instead of patching module attributes. One mechanism, exercised by both.

This module deliberately does not import the driver. `handoff` needs to drive a
sub-workflow, so the driver hands itself in via `RunEnv.driver`; the dependency points
one way and the two modules stay importable in either order.
"""
from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from workhorse import otel, turnkey
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.context import WorkflowContext
from workhorse.manifest import ManifestContext
from workhorse.runner.spec import AgentNode, OutputSpec
from workhorse.pyflow.blueprint import NodeSpec, node_spec
from workhorse.pyflow.errors import NodeNotRunError, UnknownNodeError, WorkflowFailed
from workhorse.pyflow.names import NameIndex
from workhorse.pyflow.registry import registry_of
from workhorse.pyflow.workflow import Workflow
from workhorse.runner.clock import SYSTEM_CLOCK, Clock
from workhorse.runner.ladder import AgentRunner

logger = logging.getLogger("workhorse.engine")

#: Key a non-dict node result is stored under in `output.json`, so every recorded
#: output is a JSON object and `read_output` has one shape to hand back.
SCALAR_KEY = "value"


def jsonable(value: Any) -> Any:
    """Best-effort JSON projection. Never raises: a recorded artifact must not be
    able to fail the node that produced it."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return jsonable(dataclasses.asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _payload(value: Any) -> dict[str, Any]:
    projected = jsonable(value)
    return projected if isinstance(projected, dict) else {SCALAR_KEY: projected}


def _revive(payload: dict[str, Any], returns: Any) -> Any:
    """Turn a recorded `output.json` back into the node's declared return type."""
    if isinstance(returns, type) and issubclass(returns, BaseModel):
        return returns.model_validate(payload)
    if list(payload) == [SCALAR_KEY]:
        return payload[SCALAR_KEY]
    return payload


def _blank(returns: Any) -> Any:
    """A stand-in value for `--dry-run`, where no node actually runs.

    A model with required fields cannot be constructed blank; that is fine and
    deliberate — dry-run is a reachability and prompt-path check, and a state that
    branches on a real value will take whichever branch the blank produces.
    """
    if isinstance(returns, type) and issubclass(returns, BaseModel):
        try:
            return returns.model_construct()
        except Exception:  # noqa: BLE001 — a stand-in is never worth failing over
            return None
    return None


def _stubbed(spec: NodeSpec) -> NodeSpec:
    """The same node with its body replaced by its stand-in.

    Retries go to 0 along with it: a stand-in that raised would raise identically the
    second time, and a dry run waiting out a retry ladder is a dry run nobody runs.
    """
    stub = spec.stub or (lambda _logger, *a, **kw: _blank(spec.returns))
    return dataclasses.replace(spec, fn=stub, retries=0)


def _stand_in(dry_run: bool, declared: bool) -> dict[str, str]:
    """The event-log marker for a seam a dry run answered instead of running.

    `events.jsonl` is the durable record of a run, and under `--dry-run` the fact that
    a node was *entered* is only half of what the reader needs — the other half is
    whether a real stand-in answered it or the seam fell back to a blank model, which
    is what makes the branch it took arbitrary. Empty on a real run, so nothing is
    stamped where there is nothing to say.
    """
    if not dry_run:
        return {}
    return {"stub": "declared" if declared else "blank"}


def stub_nodes(index: NameIndex[NodeSpec]) -> NameIndex[NodeSpec]:
    """The `--dry-run` node index: every node replaced by its stand-in.

    Lives here rather than in `blueprint.py` because `_blank` does, and `blueprint.py`
    keeps its zero engine imports — a node library must be importable without the
    runner behind it.
    """
    return index.replacing({name: _stubbed(spec) for name, spec in index.items()})


@dataclass
class RunEnv:
    """Everything a run needs that is not the workflow itself."""

    writer: ArtifactWriter
    workflow_dir: Path
    session_id_path: Path
    config: RunConfig
    #: `drive` from the driver module, injected to keep the import one-directional.
    driver: Callable[..., Any] | None = None
    log: logging.Logger = field(default_factory=lambda: logger)
    #: Records calls instead of making them. `--dry-run` sets it.
    dry_run: bool = False
    #: The passage of time — for the one place the driver waits (an `Await`'s poll)
    #: and, through `agent_runner` below, for the ladder's own waits. Injected rather
    #: than reached for, so a test that exercises a week-long wait costs microseconds
    #: with nothing patched. One run, one clock.
    clock: Clock = SYSTEM_CLOCK
    #: Run-wide wall-clock ceiling (unix epoch), shared with any sub-flow so a
    #: handoff cannot outlive the run's budget. None = unbounded.
    deadline: float | None = None
    #: Rendered telemetry labels for the state currently running.
    labels: dict[str, str] = field(default_factory=dict)
    #: The per-repo farrier context manifest, as the value that owns its own shape.
    #: It is the OUTER layer of every agent turn's render context: a state's own
    #: arguments override it, but it is always there so the farrier template helpers
    #: (`instruction_ref`/`isUsingInstruction`/`template.*`) resolve. The default is
    #: the manifest-free case — a real `ManifestContext` rather than an empty dict,
    #: so nothing here branches on absence and `as_context` stays the one place that
    #: knows which reserved keys a manifest projects onto a render context.
    manifest: ManifestContext = field(default_factory=ManifestContext)
    #: The run's node implementations, by registered name — `registry.nodes`, or a
    #: substituted copy of it. `self.call` reads the *name* off the function it was
    #: handed and the implementation from here, which is what makes a stand-in a
    #: substitution rather than a patch. None = trust the stamp on the function, the
    #: path a hand-built env (the engine's own tests) takes.
    nodes: NameIndex[NodeSpec] | None = None
    #: Canned agent replies for `--dry-run`, keyed by prompt stem. A value, or a
    #: callable taking the render args. Unlisted stems fall back to a blank model.
    agent_stubs: dict[str, Any] | None = None
    #: The recovery ladder this run drives agent turns through — the run's backend,
    #: resilience knobs and clock, bound together. Passing one substitutes it (a
    #: scripted runner, in a workflow author's test); leaving it None builds the real
    #: one from `config` in `__post_init__`, which is the only place it is built.
    agent_runner: AgentRunner | None = None
    #: True while the *resumed* state's own body is running, and false everywhere
    #: else. `handoff` consumes it to tell "we are re-entering the sub-flow this run
    #: was killed inside" from "this flow is being invoked again", which is the one
    #: distinction the presence of a child checkpoint cannot make. The driver owns
    #: both the setting and the clearing; nothing else writes it.
    resume_pending: bool = False

    def __post_init__(self) -> None:
        """Bind the run's ladder to the run's clock, once.

        The ladder used to be built in two places — eagerly by the CLI and lazily by
        the engine on first agent node — and *neither* passed `self.clock`, so the
        port injected here silently stopped at the driver's own `Await` and the ladder
        went on waiting on the real one. Building it here is what makes "one run, one
        clock" true rather than merely documented: there is a single construction site
        and it can see the field.
        """
        if self.agent_runner is None:
            self.agent_runner = AgentRunner.from_config(self.config, clock=self.clock)

    @property
    def run_dir(self) -> Path:
        return self.writer.run_dir

    @property
    def run_id(self) -> str:
        return self.writer.run_id


class Engine:
    """The seams, bound to one run."""

    def __init__(self, env: RunEnv) -> None:
        self.env = env

    # --- what the workflow reads through properties -------------------------

    @property
    def logger(self) -> logging.Logger:
        return self.env.log

    @property
    def run_dir(self) -> Path:
        return self.env.run_dir

    @property
    def run_id(self) -> str:
        return self.env.run_id

    # --- self.call ----------------------------------------------------------

    def call(
        self,
        node: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        span_kind: str = "",
    ) -> Any:
        spec = self._resolve(node)
        writer = self.env.writer
        rendered = _describe(spec, args, kwargs)
        # The `enter` below opens this node's span and only `write_step` closes it. A
        # node that raises never reaches that line, so the scope opened *before* the
        # enter is what closes it — at the frame that opened it, carrying the error,
        # rather than leaving it for the end of the run to sweep.
        with otel.scope():
            writer.record_node(
                spec.name,
                "enter",
                blueprint=spec.blueprint,
                # The workflow's own classification of this node, forwarded rather than
                # inferred — see `Workflow.INFRA_NODES`. Absent when it has nothing to say.
                **({"span_kind": span_kind} if span_kind else {}),
                **_stand_in(self.env.dry_run, spec.stub is not None),
            )
            self.env.log.info(
                "[workhorse] call   → %s%s",
                spec.name,
                " (dry-run)" if self.env.dry_run else "",
            )
            value = self._invoke(spec, args, kwargs)
            writer.write_step(spec.name, rendered, _payload(value), {}, next_node=None)
            return value

    def _resolve(self, node: Callable[..., Any]) -> NodeSpec:
        """The spec this run will actually call for `node`.

        The function is read for its *name*; the run's index supplies the body. A name
        the index does not carry is an error rather than a fallback to the stamp —
        otherwise the seam would be advisory, holding or not depending on whether the
        node's blueprint had been registered, which is the bug it exists to remove.
        """
        spec = node_spec(node)
        index = self.env.nodes
        if index is None:
            # No index was supplied, so the stamp is the only registration there is.
            # A dry run still needs a stand-in; substitute one here rather than
            # branching further down.
            return _stubbed(spec) if self.env.dry_run else spec
        found = index.get(spec.name)
        if found is None:
            known = ", ".join(sorted(index.live_names())) or "(none)"
            raise UnknownNodeError(
                f"node '{spec.name}' (blueprint {spec.blueprint!r}) is not in this "
                f"run's node index, so calling it would bypass every seam that index "
                f"is for. Fold its blueprint in with add_blueprints(...). Registered "
                f"nodes: {known}."
            )
        return found

    def _invoke(
        self, spec: NodeSpec, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        """Call the node, re-calling it `retries` times if it raises.

        A node is a plain function, so the only recovery available here is to call it
        again; nothing about a `TypeError` from bad code improves on a second try, and
        that is exactly why `retries` defaults to 0 and is opt-in per node.
        """
        attempts = max(0, spec.retries) + 1
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return spec.fn(self.env.log, *args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — re-raised below, after the budget
                last = exc
                if attempt < attempts:
                    self.env.log.warning(
                        "[workhorse] node '%s' failed (attempt %d/%d): %s",
                        spec.name,
                        attempt,
                        attempts,
                        exc,
                    )
                    # The agent ladder's retries have been span events since it had
                    # spans; a node call's were console-and-log only, so a node that
                    # succeeded on its second attempt was indistinguishable in the
                    # trace from one that worked first time.
                    otel.turn_event(
                        "node_retry",
                        node=spec.name,
                        attempt=attempt,
                        error_class=type(exc).__name__,
                    )
        assert last is not None
        raise last

    # --- self.agent ---------------------------------------------------------

    def agent(
        self,
        prompt: str,
        *,
        returns: type,
        args: dict[str, Any],
        power: str | None = None,
        timeout: float | None = None,
        cwd: str | Path | None = None,
        add_dirs: Sequence[str | Path] | None = None,
    ) -> Any:
        node_id = Path(prompt).stem or "agent"
        writer = self.env.writer
        declared = node_id in (self.env.agent_stubs or {})
        # The `enter` below opens this node's span and only `write_step` closes it.
        # A turn that raises never reaches that line, so the scope opened *before*
        # the enter is what closes it — at the frame that opened it, carrying the
        # error, rather than leaving it for the end of the run to sweep.
        with otel.scope():
            writer.record_node(
                node_id, "enter", prompt=prompt, **_stand_in(self.env.dry_run, declared)
            )

            if self.env.dry_run:
                value = self._agent_stub(node_id, returns, args)
                writer.write_step(node_id, f"(dry-run) {prompt}", _payload(value), {})
                self.env.log.info("[workhorse] agent  → %s (dry-run)", node_id)
                return value

            # Left out entirely when the state said nothing, so the node model's own
            # defaults keep applying rather than being overwritten with None.
            budget: dict[str, Any] = {}
            if power is not None:
                budget["power"] = power
            if timeout is not None:
                budget["timeout"] = timeout
            # The runner Jinja-renders `cwd`/`add_dirs` — a literal path is a no-op render,
            # so real values pass through unchanged and the cwd de-dupe and `--add-dir`
            # flags come for free.
            if cwd is not None:
                budget["cwd"] = str(cwd)
            if add_dirs is not None:
                budget["add_dirs"] = [str(d) for d in add_dirs]
            node = AgentNode(
                type="agent",
                id=node_id,
                prompt=prompt,
                # The values are already real Python objects, so they go into the render
                # context directly rather than through `args:`, which is a dict of Jinja
                # template *strings* and would stringify an int or a Path on the way past.
                args={},
                outputs=_outputs_for(returns),
                next=None,
                **budget,
            )
            # Name this visit before anything writes about it. A node in a loop is
            # visited many times, and the prompt, the session map and the transcript are
            # written by three layers that cannot see each other — the key is what lets
            # a reader put lap 5's three files back together.
            turnkey.begin(
                self.env.session_id_path.parent if self.env.session_id_path else None,
                node_id,
            )
            self.env.log.info("[workhorse] agent  → %s", node_id)
            # Never None: `RunEnv.__post_init__` resolves the field, so the ladder this run
            # uses is the ladder this run was built with — not one this call constructs from
            # configuration it would have to re-read.
            runner = self.env.agent_runner
            if runner is None:  # pragma: no cover - see above; the field is always resolved
                raise WorkflowFailed("this run was built without an agent runner")
            rendered, raw = runner.run(
                node,
                # The manifest underneath, the state's arguments on top: a state that
                # binds `repo` means its own, not the manifest's.
                WorkflowContext({**self.env.manifest.as_context(), **jsonable(args)}),
                self.env.workflow_dir,
                self.env.session_id_path,
                run_dir=writer.run_dir,
            )
            writer.write_step(node_id, rendered, raw, {}, next_node=None)
            return _coerce(raw, returns, node_id)

    def _agent_stub(self, node_id: str, returns: type, args: dict[str, Any]) -> Any:
        """The reply a dry run uses for one prompt.

        Keyed by prompt *stem*, because that is what a workflow author names. A stem
        the registry said nothing about gets a blank model — honest about knowing
        nothing, and the reason an unstubbed dry run's branches are arbitrary.
        """
        reply = (self.env.agent_stubs or {}).get(node_id)
        if reply is None:
            return _blank(returns)
        if callable(reply):
            reply = reply(args)
        if isinstance(reply, dict):
            return _coerce(reply, returns, node_id)
        return reply

    # --- self.handoff -------------------------------------------------------

    def handoff(
        self, wf: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        if self.env.driver is None:
            raise WorkflowFailed(
                "handoff() needs a driver — this engine was built without one"
            )
        child = wf(*args, **kwargs)
        node_id = _flow_id(wf)
        writer = self.env.writer
        # The `enter` below opens this handoff's span. The child's own states close
        # their own spans; this scope closes the handoff frame itself when the
        # sub-flow raises through it, at the depth that opened it.
        with otel.scope():
            writer.record_node(node_id, "enter", flow=type(child).__name__)
            self.env.log.info("[workhorse] flow   → %s", node_id)
            # A resume re-enters the state that was running when the run was killed — and
            # if that state is a handoff, the sub-flow it was inside is where the run
            # actually was. Started fresh, the child replays from its own `start`, which
            # for a long sub-flow (the coder's QA flow: context, plan, review, then a
            # half-hour suite) throws away hours of finished agent turns on every restart.
            # The token is one-shot and set only for the resumed state's own body, so an
            # ordinary re-entry — a loop calling the same flow a second time — still
            # starts the child clean, which is what `subscope`'s `resume` contract asks for.
            resuming = self.env.resume_pending
            self.env.resume_pending = False
            sub_writer = writer.subscope(node_id, type(child).__name__, resume=resuming)
            sub_env = dataclasses.replace(
                self.env, writer=sub_writer, **_sub_scope(type(child), self.env)
            )
            result = self.env.driver(child, sub_env, resume_in_place=resuming)
            writer.write_step(node_id, f"handoff → {type(child).__name__}", _payload(result), {})
            return result

    # --- self.output --------------------------------------------------------

    def output(self, node: Callable[..., Any]) -> Any:
        # Through the index, like `call`, so an overridden node's `dir_names` and
        # `returns` are the ones the run recorded under.
        spec = self._resolve(node)
        for name in spec.dir_names:
            payload = self.env.writer.read_output(name)
            if payload is not None:
                return _revive(payload, spec.returns)
        raise NodeNotRunError(
            f"node '{spec.name}' has no recorded output in {self.env.run_dir} — it has "
            "not run in this run (or ran in a different flow scope). self.output() "
            "reads what self.call() recorded; call the node first, or thread the value "
            "through the transition."
        )


def _describe(spec: NodeSpec, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """The `prompt.md` a node call leaves behind: what was called, with what.

    A script node's artifact was its command line; this is the equivalent, and it is
    what makes a run directory readable without the source beside it.
    """
    parts = [json.dumps(jsonable(a)) for a in args]
    parts += [f"{k}={json.dumps(jsonable(v))}" for k, v in kwargs.items()]
    return f"{spec.blueprint}.{spec.name}({', '.join(parts)})\n"


def _sub_scope(cls: type[Workflow], env: RunEnv) -> dict[str, Any]:
    """What a handed-off flow gets that its caller does not: its own registry's world.

    A sub-flow is a different program. It resolves the registry that claimed its class
    and runs with that registry's prompt directory, node index and stand-ins — so a
    sub-flow shipped in another distribution renders its own `prompts/` instead of
    looking for them under its caller's package, and a node the parent substituted is
    not silently substituted for the child as well.

    An unclaimed class (declared beside its parent, never registered separately)
    inherits, which is what keeps the common case ceremony-free.
    """
    registry = registry_of(cls)
    if registry is None or registry.nodes is env.nodes:
        return {}
    return {
        "workflow_dir": registry.directory(),
        "nodes": stub_nodes(registry.nodes) if env.dry_run else registry.nodes,
        "agent_stubs": registry.agent_stubs if env.dry_run else None,
    }


def _flow_id(wf: Callable[..., Any]) -> str:
    name = getattr(wf, "__name__", "flow")
    return "".join(f"_{c.lower()}" if c.isupper() else c for c in name).lstrip("_")


def _outputs_for(returns: type) -> list[OutputSpec]:
    """The keys the agent is asked for, taken from the model it must return.

    Declaring them is what the resilience ladder reframes against — it is how a reply
    that missed a key gets asked again for that key by name. There is no fallback below
    the last reframe: a node that never answered has no answer to emit, so the ladder
    stops the run (see `runner/spec.py::OutputSpec`).
    """
    fields = getattr(returns, "model_fields", None)
    if not fields:
        return [OutputSpec(key=SCALAR_KEY)]
    return [OutputSpec(key=name) for name in fields]


def _coerce(raw: dict[str, Any], returns: type, node_id: str) -> Any:
    if isinstance(returns, type) and issubclass(returns, BaseModel):
        try:
            return returns.model_validate(raw)
        except Exception as exc:
            raise WorkflowFailed(
                f"agent node '{node_id}' returned something that is not a "
                f"{returns.__name__}: {exc}"
            ) from exc
    if list(raw) == [SCALAR_KEY]:
        return raw[SCALAR_KEY]
    return raw


__all__ = ["Engine", "RunEnv", "stub_nodes"]
