"""What `self.call` / `self.agent` / `self.handoff` / `self.output` actually do.

The seams exist so that a node gets three things a direct function call cannot: its
own event in `events.jsonl`, a recorded `output.json` that `self.output(...)` can read
back, and a no-op under `--dry-run` that records the call instead of making it — which
is what lets a graph be enumerated without executing anything.

This module deliberately does not import the driver. `handoff` needs to drive a
sub-workflow, so the driver hands itself in via `RunEnv.driver`; the dependency points
one way and the two modules stay importable in either order.
"""
from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from workhorse.artifacts import ArtifactWriter
from workhorse.graph.context import WorkflowContext
from workhorse.graph.nodes import AgentNode, OutputSpec
from workhorse.pyflow.blueprint import NodeSpec, node_spec
from workhorse.pyflow.errors import NodeNotRunError, WorkflowFailed
from workhorse.runner import agent as agent_runner

logger = logging.getLogger("workhorse.engine")

#: Key a non-dict node result is stored under in `output.json`, so every recorded
#: output is a JSON object and `read_output` has one shape to hand back.
SCALAR_KEY = "value"


def _jsonable(value: Any) -> Any:
    """Best-effort JSON projection. Never raises: a recorded artifact must not be
    able to fail the node that produced it."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _payload(value: Any) -> dict[str, Any]:
    projected = _jsonable(value)
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


@dataclass
class RunEnv:
    """Everything a run needs that is not the workflow itself."""

    writer: ArtifactWriter
    workflow_dir: Path
    session_id_path: Path
    config: Any
    #: `drive` from the driver module, injected to keep the import one-directional.
    driver: Callable[..., Any] | None = None
    log: logging.Logger = field(default_factory=lambda: logger)
    #: Records calls instead of making them. `--dry-run` sets it.
    dry_run: bool = False
    #: Run-wide wall-clock ceiling (unix epoch), shared with any sub-flow so a
    #: handoff cannot outlive the run's budget. None = unbounded.
    deadline: float | None = None
    #: Rendered telemetry labels for the state currently running.
    labels: dict[str, str] = field(default_factory=dict)

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
        self, node: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        spec = node_spec(node)
        writer = self.env.writer
        rendered = _describe(spec, args, kwargs)
        writer.record_node(spec.name, "enter", blueprint=spec.blueprint)

        if self.env.dry_run:
            value = _blank(spec.returns)
            writer.write_step(spec.name, rendered, _payload(value), {}, next_node=None)
            self.env.log.info("[workhorse] call   → %s (dry-run)", spec.name)
            return value

        self.env.log.info("[workhorse] call   → %s", spec.name)
        value = self._invoke(spec, args, kwargs)
        writer.write_step(spec.name, rendered, _payload(value), {}, next_node=None)
        return value

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
        assert last is not None
        raise last

    # --- self.agent ---------------------------------------------------------

    def agent(self, prompt: str, *, returns: type, args: dict[str, Any]) -> Any:
        node_id = Path(prompt).stem or "agent"
        writer = self.env.writer
        writer.record_node(node_id, "enter", prompt=prompt)

        if self.env.dry_run:
            value = _blank(returns)
            writer.write_step(node_id, f"(dry-run) {prompt}", _payload(value), {})
            self.env.log.info("[workhorse] agent  → %s (dry-run)", node_id)
            return value

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
        )
        self.env.log.info("[workhorse] agent  → %s", node_id)
        config = self.env.config
        rendered, raw = agent_runner.run_agent(
            node,
            WorkflowContext(_jsonable(args)),
            self.env.workflow_dir,
            self.env.session_id_path,
            max_output_retries=config.resilience.max_output_retries,
            max_rephrase_attempts=config.resilience.max_rephrase_attempts,
            max_compact_attempts=config.resilience.max_compact_attempts,
            run_dir=writer.run_dir,
            backend=config.get_backend(),
            use_default_outputs=config.resilience.use_default_outputs,
            result_timeout=config.resilience.result_timeout_s,
        )
        writer.write_step(node_id, rendered, raw, {}, next_node=None)
        return _coerce(raw, returns, node_id)

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
        writer.record_node(node_id, "enter", flow=type(child).__name__)
        self.env.log.info("[workhorse] flow   → %s", node_id)
        sub_writer = writer.subscope(node_id, type(child).__name__)
        sub_env = dataclasses.replace(self.env, writer=sub_writer)
        result = self.env.driver(child, sub_env)
        writer.write_step(node_id, f"handoff → {type(child).__name__}", _payload(result), {})
        return result

    # --- self.output --------------------------------------------------------

    def output(self, node: Callable[..., Any]) -> Any:
        spec = node_spec(node)
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
    parts = [json.dumps(_jsonable(a)) for a in args]
    parts += [f"{k}={json.dumps(_jsonable(v))}" for k, v in kwargs.items()]
    return f"{spec.blueprint}.{spec.name}({', '.join(parts)})\n"


def _flow_id(wf: Callable[..., Any]) -> str:
    name = getattr(wf, "__name__", "flow")
    return "".join(f"_{c.lower()}" if c.isupper() else c for c in name).lstrip("_")


def _outputs_for(returns: type) -> list[OutputSpec]:
    """The keys the agent is asked for, taken from the model it must return.

    Declaring them is what gives the resilience ladder something to fall back to:
    after every reframe fails, the node emits these keys as nulls and the run moves on
    rather than crashing.
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


__all__ = ["Engine", "RunEnv"]
