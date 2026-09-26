"""The `Workflow` base class: a state machine whose states are its own methods."""
from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Iterable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import Any, ClassVar, Concatenate, ParamSpec, TypeVar

from jinja2 import TemplateSyntaxError
from pydantic import BaseModel, ConfigDict, PrivateAttr

from workhorse.pyflow.errors import (
    UnknownStateError,
    WorkflowDefinitionError,
    WorkflowFrozenError,
)
from workhorse.pyflow.names import NameIndex
from workhorse.pyflow.transitions import Await, Continue, Done, Transition
from workhorse.runner.backends import AgentProfile
from workhorse.runner.usage import TurnUsage
from workhorse import references
from workhorse.runner import worktree_guard
from workhorse.worklist import WorkItem, WorkList

P = ParamSpec("P")
T = TypeVar("T")

START_STATE = "start"

_NAMEABLE = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)

STATE_ATTR = "__workhorse_state__"

LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class StateSpec:
    """What registration knows about a state method."""

    name: str
    fn: Callable[..., Any]
    aliases: tuple[str, ...] = ()


def state(
    fn: Callable[..., Any] | None = None, *, aliases: Iterable[str] = ()
) -> Any:
    """Declare metadata for a state."""
    alias_tuple = tuple(aliases)

    def decorate(target: Callable[..., Any]) -> Callable[..., Any]:
        setattr(target, STATE_ATTR, alias_tuple)
        return target

    return decorate if fn is None else decorate(fn)


def _is_state(name: str, value: Any) -> bool:
    if name.startswith("_"):
        return False
    return inspect.isfunction(value)


class Workflow(BaseModel):
    """Subclass this; your public methods are the states."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    repo_dir: str = ""

    library_dirs: tuple[str, ...] = ()

    injects: ClassVar[tuple[str, ...]] = ("repo_dir", "library_dirs")

    INFRA_NODES: ClassVar[frozenset[Any]] = frozenset()

    _engine: Any = PrivateAttr(default=None)
    _ctx: Any = PrivateAttr(default=None)
    _frozen: bool = PrivateAttr(default=False)

    states: ClassVar[NameIndex[StateSpec]]
    start_state: ClassVar[str] = START_STATE
    max_transitions: ClassVar[int] = 0
    REFUEL_ON: ClassVar[frozenset[str]] = frozenset()
    PROTECT_WORKTREE: ClassVar[bool] = False


    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        base_names = set(dir(Workflow))
        index: NameIndex[StateSpec] = NameIndex("state", owner=cls.__name__)
        for klass in reversed(cls.__mro__):
            if klass in (Workflow, BaseModel, object):
                continue
            for name, value in vars(klass).items():
                if name in base_names or not _is_state(name, value):
                    continue
                if name in index.live_names():
                    continue
                aliases = tuple(getattr(value, STATE_ATTR, ()))
                index.register(name, StateSpec(name, value, aliases), aliases)
        cls.states = index

    @classmethod
    def state_names(cls) -> list[str]:
        """Live names only — what `dot` and `--dry-run` render."""
        return cls.states.live_names()

    @classmethod
    def resolve_state(cls, name: str) -> StateSpec:
        """The state `name` refers to, live or retired, or a loud failure."""
        spec = cls.states.get(name)
        if spec is None:
            known = ", ".join(sorted(cls.states.live_names())) or "(none)"
            raise UnknownStateError(
                f"{cls.__name__} has no state {name!r}. Known states: {known}. If it "
                f"was renamed, declare @state(aliases=[{name!r}]) on the state that "
                "replaced it so runs checkpointed under the old name can resume."
            )
        return spec


    def setup(self) -> Any:
        """Run once, before the first state, and only once per run."""
        return None

    def labels(self) -> dict[str, str]:
        """The workflow's own telemetry dimensions, e.g."""
        return {}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, for dimensions that depend on the state's own arguments."""
        return self.labels()


    @property
    def ctx(self) -> Any:
        return self._ctx

    @property
    def logger(self) -> Logger:
        return self._require_engine().logger

    @property
    def run_dir(self) -> Path:
        return self._require_engine().run_dir

    @property
    def run_id(self) -> str:
        return self._require_engine().run_id


    def call(
        self,
        node: Callable[Concatenate[Logger, P], T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        """Run a blueprint node and return its plain typed value."""
        return self._require_engine().call(
            node,
            args,
            self._fill(node, args, kwargs, skip=1),
            span_kind="infra" if node in type(self).INFRA_NODES else "",
        )

    def agent(
        self,
        prompt: str,
        *,
        returns: type[T],
        args: dict[str, Any] | None = None,
        power: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        invoke_retries: int | None = None,
        cwd: str | Path | None = None,
        add_dirs: Sequence[str | Path] | None = None,
        session: str | None = None,
        profile: AgentProfile | None = None,
        label: str | None = None,
        accept: Callable[[T], object] | None = None,
    ) -> T:
        """Render `prompt`, run an agent turn, and validate the reply into `returns`.

        `prompt` is a template path under the workflow package. With `label`, it is the
        turn's own text instead, and the label is the node id the run directory, the
        span and the dry-run stand-in are all keyed by.

        `accept` is handed the validated reply before the turn ends. When it raises, the
        agent is asked again with the exception's message, as for a reply that did not parse.
        """
        engine = self._require_engine()
        if label is not None:
            self._check_inline(label, prompt)
        guard = (
            worktree_guard.guarding(engine.run_dir)
            if type(self).PROTECT_WORKTREE and not engine.worktree_dispatched
            else nullcontext()
        )
        with guard:
            return engine.agent(
                prompt,
                returns=returns,
                args=args or {},
                power=power,
                timeout=timeout,
                retries=retries,
                invoke_retries=invoke_retries,
                cwd=cwd,
                add_dirs=add_dirs,
                session=session,
                profile=profile,
                label=label,
                accept=accept,
            )

    @staticmethod
    def _check_inline(label: str, text: str) -> None:
        """Refuse an inline prompt the run directory, the diagram or the reference preflight could not account for."""
        if not LABEL_PATTERN.match(label):
            raise WorkflowDefinitionError(
                f"agent label {label!r} is not a node id — it names a run-directory "
                "subdirectory, a span and a stub key, so it must match "
                f"{LABEL_PATTERN.pattern}"
            )
        try:
            used = references.helpers_called(text)
        except TemplateSyntaxError as exc:
            raise WorkflowDefinitionError(
                f"the inline prompt labelled {label!r} is not valid Jinja: {exc}"
            ) from exc
        if used:
            raise WorkflowDefinitionError(
                f"the inline prompt labelled {label!r} calls "
                f"{', '.join(sorted(used))} — a manifest reference is resolved against "
                "the manifest and checked by a sweep over prompt files, which an "
                "inline body is not. Put this turn in a prompt file."
            )

    def pipeline(
        self,
        work: WorkList,
        kind: str,
        n: int,
        handler: Callable[[list[WorkItem]], Any],
        *,
        status: str = "done",
    ) -> Transition | None:
        """Hand the next `n` items of `kind` to `handler` and come back here for the next chunk, or `None` once the queue is drained.

        One chunk per state visit, so every chunk is a checkpoint a resume can land on.
        The loop carries this state's own parameters, so nothing is restated. A handler
        that returns a transition takes it instead, which is how a drain gates partway
        through. Claimed rows settle to `status` unless the handler already moved them,
        so a row it marked blocked keeps that verdict.
        """
        engine = self._require_engine()
        items = work.claim(n, kind=kind)
        if not items:
            return None
        outcome = handler(items)
        if isinstance(outcome, (Continue, Done, Await)):
            return outcome
        held = {
            it.id for it in work.items(kind) if it.status in work.scheme.active
        }
        work.settle([it.id for it in items if it.id in held], status, kind)
        return engine.revisit()

    def turn_usage(self, node: str) -> TurnUsage:
        """What the last turn of agent node `node` used, as its backend reported it. Empty when it reported nothing or has not run."""
        return self._require_engine().turn_usage(node)

    def seed_session(self, key: str, session_id: str) -> None:
        """Start chain `key` on a session id another turn — or another flow — minted."""
        self._require_engine().seed_session(key, session_id)

    def chain_session(self, key: str) -> str:
        """The session id chain `key` is on, or `""` before its first turn."""
        return self._require_engine().session_id(key)

    def reset_session(self, key: str) -> None:
        """End session chain `key`, so the next turn on it starts a fresh conversation."""
        self._require_engine().reset_session(key)

    def handoff(self, wf: Callable[P, Any], *args: P.args, **kwargs: P.kwargs) -> Any:
        """Drive another workflow to completion in a sub-scope; return its result."""
        return self._require_engine().handoff(wf, args, self._fill(wf, args, kwargs))

    def output(self, node: Callable[..., T]) -> T:
        """The recorded output of a node that already ran, typed by its own return."""
        return self._require_engine().output(node)


    def _fill(
        self,
        target: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        skip: int = 0,
    ) -> dict[str, Any]:
        """`kwargs` plus every `injects` field `target` declares and the callsite omitted."""
        injects = getattr(type(self), "injects", ())
        if not injects:
            return kwargs
        try:
            params = inspect.signature(target).parameters
        except (TypeError, ValueError):
            return kwargs
        positional = set(list(params)[skip : skip + len(args)])
        filled = dict(kwargs)
        fields = type(self).model_fields
        for name in injects:
            if name in filled or name in positional or name not in fields:
                continue
            param = params.get(name)
            if param is None or param.kind not in _NAMEABLE:
                continue
            value = getattr(self, name, None)
            if value not in (None, ""):
                filled[name] = value
        return filled


    def _bind(self, engine: Any) -> None:
        self._engine = engine

    def _seal(self, ctx: Any) -> None:
        """Install `ctx` and freeze the instance."""
        self._ctx = ctx
        self._frozen = True

    def _is_frozen(self) -> bool:
        private = getattr(self, "__pydantic_private__", None) or {}
        return bool(private.get("_frozen"))

    def _require_engine(self) -> Any:
        engine = (getattr(self, "__pydantic_private__", None) or {}).get("_engine")
        if engine is None:
            raise WorkflowDefinitionError(
                f"{type(self).__name__} is not bound to a run — `self.call`, "
                "`self.agent`, `self.handoff` and `self.output` only work inside a "
                "state the driver is running. To exercise one in a test, drive the "
                "workflow rather than instantiating it."
            )
        return engine

    def __setattr__(self, name: str, value: Any) -> None:
        if not name.startswith("_") and self._is_frozen():
            raise WorkflowFrozenError(
                f"cannot set {type(self).__name__}.{name} — the workflow instance is "
                "frozen once setup() returns. A value a state writes belongs in the "
                "transition (`Continue(result, self.next_state, "
                f"{name}=…)`), because that is what the checkpoint stores and what "
                "survives a resume."
            )
        super().__setattr__(name, value)


Workflow.states = NameIndex("state", owner="Workflow")
