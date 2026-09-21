"""The `Workflow` base class: a state machine whose states are its own methods."""
from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import Any, ClassVar, Concatenate, ParamSpec, TypeVar

from pydantic import BaseModel, ConfigDict, PrivateAttr

from workhorse.pyflow.errors import (
    UnknownStateError,
    WorkflowDefinitionError,
    WorkflowFrozenError,
)
from workhorse.pyflow.names import NameIndex
from workhorse.runner import worktree_guard

P = ParamSpec("P")
T = TypeVar("T")

START_STATE = "start"

_NAMEABLE = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)

STATE_ATTR = "__workhorse_state__"


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
    ) -> T:
        """Render `prompt`, run an agent turn, and validate the reply into `returns`."""
        engine = self._require_engine()
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
            )

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
