"""What `self.call` / `self.agent` / `self.handoff` / `self.output` actually do."""
from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from workhorse import otel, sessions, turnkey
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.context import WorkflowContext
from workhorse.manifest import ManifestContext
from workhorse.runner.spec import AgentNode, OutputSpec
from workhorse.pyflow.blueprint import NodeSpec, node_spec
from workhorse.pyflow.errors import (
    AgentTimeout,
    AgentTurnFailed,
    NodeNotRunError,
    UnknownNodeError,
    WorkflowFailed,
)
from workhorse.pyflow.names import NameIndex
from workhorse.pyflow.registry import registry_of
from workhorse.pyflow.workflow import Workflow
from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK, Clock
from workhorse.runner.failure import BackendInvocationError
from workhorse.runner.ladder import AgentRunner

logger = logging.getLogger("workhorse.engine")

SCALAR_KEY = "value"


def jsonable(value: Any) -> Any:
    """Best-effort JSON projection."""
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
    """A stand-in value for `--dry-run`, where no node actually runs."""
    if isinstance(returns, type) and issubclass(returns, BaseModel):
        try:
            return returns.model_construct()
        except Exception:  # noqa: BLE001 — a stand-in is never worth failing over
            return None
    return None


def _stubbed(spec: NodeSpec) -> NodeSpec:
    """The same node with its body replaced by its stand-in."""
    stub = spec.stub or (lambda _logger, *a, **kw: _blank(spec.returns))
    return dataclasses.replace(spec, fn=stub, retries=0)


def _stand_in(dry_run: bool, declared: bool) -> dict[str, str]:
    """The event-log marker for a seam a dry run answered instead of running."""
    if not dry_run:
        return {}
    return {"stub": "declared" if declared else "blank"}


def stub_nodes(index: NameIndex[NodeSpec]) -> NameIndex[NodeSpec]:
    """The `--dry-run` node index: every node replaced by its stand-in."""
    return index.replacing({name: _stubbed(spec) for name, spec in index.items()})


@dataclass
class RunEnv:
    """Everything a run needs that is not the workflow itself."""

    writer: ArtifactWriter
    workflow_dir: Path
    session_id_path: Path
    config: RunConfig
    driver: Callable[..., Any] | None = None
    log: logging.Logger = field(default_factory=lambda: logger)
    dry_run: bool = False
    clock: Clock = SYSTEM_CLOCK
    deadline: float | None = None
    labels: dict[str, str] = field(default_factory=dict)
    manifest: ManifestContext = field(default_factory=ManifestContext)
    nodes: NameIndex[NodeSpec] | None = None
    agent_stubs: dict[str, Any] | None = None
    agent_runner: AgentRunner | None = None
    resume_pending: bool = False
    worktree_dispatched: bool = False

    def __post_init__(self) -> None:
        """Bind the run's ladder to the run's clock, once."""
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


    @property
    def logger(self) -> logging.Logger:
        return self.env.log

    @property
    def run_dir(self) -> Path:
        return self.env.run_dir

    @property
    def run_id(self) -> str:
        return self.env.run_id

    @property
    def worktree_dispatched(self) -> bool:
        return self.env.worktree_dispatched


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
        with otel.scope():
            writer.record_node(
                spec.name,
                "enter",
                blueprint=spec.blueprint,
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
        """The spec this run will actually call for `node`."""
        spec = node_spec(node)
        index = self.env.nodes
        if index is None:
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
        """Call the node, re-calling it `retries` times if it raises."""
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
                    otel.turn_event(
                        "node_retry",
                        node=spec.name,
                        attempt=attempt,
                        error_class=type(exc).__name__,
                    )
        assert last is not None
        raise last


    def agent(
        self,
        prompt: str,
        *,
        returns: type,
        args: dict[str, Any],
        power: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        invoke_retries: int | None = None,
        cwd: str | Path | None = None,
        add_dirs: Sequence[str | Path] | None = None,
        session: str | None = None,
    ) -> Any:
        node_id = Path(prompt).stem or "agent"
        writer = self.env.writer
        declared = node_id in (self.env.agent_stubs or {})
        session_path = self.env.session_id_path
        resumed = ""
        if session and session_path is not None:
            session_path = sessions.chain_path(session_path.parent, session)
            if session_path.exists():
                resumed = session_path.read_text(encoding="utf-8").strip()
        with otel.scope():
            writer.record_node(
                node_id,
                "enter",
                prompt=prompt,
                repository_cwd=str(cwd) if cwd is not None else "",
                repository_add_dirs=[str(path) for path in add_dirs or ()],
                **({"chain": session, "resumed_session": resumed} if session else {}),
                **_stand_in(self.env.dry_run, declared),
            )

            if self.env.dry_run:
                value = self._agent_stub(node_id, returns, args)
                writer.write_step(node_id, f"(dry-run) {prompt}", _payload(value), {})
                self.env.log.info("[workhorse] agent  → %s (dry-run)", node_id)
                return value

            budget: dict[str, Any] = {}
            if power is not None:
                budget["power"] = power
            if timeout is not None:
                budget["timeout"] = timeout
            if retries is not None:
                budget["retries"] = retries
            if invoke_retries is not None:
                budget["invoke_retries"] = invoke_retries
            if cwd is not None:
                budget["cwd"] = str(cwd)
            if add_dirs is not None:
                budget["add_dirs"] = [str(d) for d in add_dirs]
            node = AgentNode(
                type="agent",
                id=node_id,
                prompt=prompt,
                args={},
                outputs=_outputs_for(returns),
                next=None,
                **budget,
            )
            turnkey.begin(
                self.env.session_id_path.parent if self.env.session_id_path else None,
                node_id,
                chain=session or "",
            )
            self.env.log.info(
                "[workhorse] agent  → %s%s", node_id, f" (chain {session})" if session else ""
            )
            runner = self.env.agent_runner
            if runner is None:  # pragma: no cover - see above; the field is always resolved
                raise WorkflowFailed("this run was built without an agent runner")
            try:
                rendered, raw = runner.run(
                    node,
                    WorkflowContext(
                        {**self.env.manifest.as_context(), **jsonable(args)}
                    ),
                    self.env.workflow_dir,
                    session_path,
                    resume_session=bool(session),
                    session_chain=session or "",
                    run_dir=writer.run_dir,
                    validate=(
                        returns.model_validate
                        if isinstance(returns, type) and issubclass(returns, BaseModel)
                        else None
                    ),
                )
            except BackendInvocationError as exc:
                if exc.timed_out:
                    raise AgentTimeout(str(exc), transient=exc.transient) from exc
                raise AgentTurnFailed(str(exc), transient=exc.transient, overflow=exc.overflow) from exc
            writer.write_step(node_id, rendered, raw, {}, next_node=None)
            return _coerce(raw, returns, node_id)

    def session_id(self, key: str) -> str:
        """The session id chain ``key`` is on, or ``""`` before its first turn."""
        if not key or self.env.session_id_path is None:
            return ""
        return sessions.read_chain(self.env.session_id_path.parent, key)

    def seed_session(self, key: str, session_id: str) -> None:
        """Start chain ``key`` on an id someone else's turn minted."""
        if not key or not session_id.strip() or self.env.session_id_path is None:
            return
        path = sessions.chain_path(self.env.session_id_path.parent, key)
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(session_id.strip(), encoding="utf-8")
        self.env.log.info("[workhorse] chain %s: seeded", key)

    def reset_session(self, key: str) -> None:
        """End chain ``key``: the next turn on it opens a fresh conversation."""
        if not key or self.env.session_id_path is None:
            return
        path = sessions.chain_path(self.env.session_id_path.parent, key)
        try:
            path.unlink()
        except FileNotFoundError:
            return
        self.env.log.info("[workhorse] chain %s: reset", key)

    def _agent_stub(self, node_id: str, returns: type, args: dict[str, Any]) -> Any:
        """The reply a dry run uses for one prompt."""
        reply = (self.env.agent_stubs or {}).get(node_id)
        if reply is None:
            return _blank(returns)
        if callable(reply):
            reply = reply(args)
        if isinstance(reply, dict):
            return _coerce(reply, returns, node_id)
        return reply


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
        with otel.scope():
            writer.record_node(node_id, "enter", flow=type(child).__name__)
            self.env.log.info("[workhorse] flow   → %s", node_id)
            resuming = self.env.resume_pending
            self.env.resume_pending = False
            sub_writer = writer.subscope(node_id, type(child).__name__, resume=resuming)
            sub_env = dataclasses.replace(
                self.env, writer=sub_writer, **_sub_scope(type(child), self.env)
            )
            result = self.env.driver(child, sub_env, resume_in_place=resuming)
            writer.write_step(node_id, f"handoff → {type(child).__name__}", _payload(result), {})
            return result


    def output(self, node: Callable[..., Any]) -> Any:
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
    """The `prompt.md` a node call leaves behind: what was called, with what."""
    parts = [json.dumps(jsonable(a)) for a in args]
    parts += [f"{k}={json.dumps(jsonable(v))}" for k, v in kwargs.items()]
    return f"{spec.blueprint}.{spec.name}({', '.join(parts)})\n"


def _sub_scope(cls: type[Workflow], env: RunEnv) -> dict[str, Any]:
    """What a handed-off flow gets that its caller does not: its own registry's world."""
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
    """The keys the agent is asked for, taken from the model it must return."""
    fields = getattr(returns, "model_fields", None)
    if not fields:
        return [OutputSpec(key=SCALAR_KEY)]
    return [
        OutputSpec(key=name, required=bool(getattr(info, "is_required", lambda: True)()))
        for name, info in fields.items()
    ]


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
