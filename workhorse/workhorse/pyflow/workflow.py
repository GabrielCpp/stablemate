"""The `Workflow` base class: a state machine whose states are its own methods.

Three tiers of state and no fourth — inputs (class fields, set once from `--param`),
`self.ctx` (written by `setup()` exactly once), and state parameters (one hop, and
they *are* the checkpoint). The rule the whole design rests on is **if a state writes
it, it is a parameter of the next state**, and the base class enforces the half of
that rule documentation could not: the instance freezes once `setup()` returns, so a
`self.x = …` that would survive a transition in memory and vanish on resume raises at
the assignment instead of at hour 30 of a run.

`self.call` / `self.agent` / `self.handoff` / `self.output` are seams, not
conveniences. Calling a node function directly would work and would be invisible;
going through the seam is what earns it a span, a recorded `output.json` — which
`self.output(...)` later reads — and a no-op under `--dry-run`.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Sequence
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

P = ParamSpec("P")
T = TypeVar("T")

#: Where a run starts when the checkpoint does not say otherwise.
START_STATE = "start"

#: Parameter kinds an injected input can be passed to by name. `*args`/`**kwargs` are
#: not among them: a target that only declares those has not asked for the input, and
#: filling it would be guessing.
_NAMEABLE = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)

#: Attribute `@state(aliases=[...])` stamps on a method. The decorator carries no
#: registry reference on purpose: it has to be usable in a class body that is defined
#: before the module-level `Registry` object exists.
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
    """Declare metadata for a state. Optional — a public method is already a state.

    Its only job today is `aliases=[...]`: the names this state used to have. A
    checkpoint naming a state that no longer exists fails loudly rather than starting
    over, and this is the one-line fix that lets the in-flight runs finish::

        @state(aliases=["qa_gate"])          # was qa_gate before 0.9
        def qa(self, story: str, attempt: int = 0) -> Continue | Done: ...
    """
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
    """Subclass this; your public methods are the states.

    Discovery is implicit — a public method that is not `setup`/`labels` and is not
    part of this base class is a state. A helper that is *not* a state therefore has
    to start with an underscore, which is the only thing this costs and is the same
    convention the rest of Python already uses for "not part of the surface".
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    #: The consuming repo's root — the one input every workflow shares, which is why it
    #: is declared on the parent rather than re-declared per workflow. The CLI defaults
    #: it to the launch directory; `--param repo_dir=…` overrides. Blank means "resolve
    #: by walking up from the cwd" (`scriptutil.find_repo_root`).
    #:
    #: It is a field and not an environment read because **a node may not read the
    #: environment** (`workflows/README.md`): a run's inputs have to be visible in its
    #: params, comparable between two runs, and overridable by a caller — which
    #: `AGENT_REPO_DIR` is none of. A state passes it on to the nodes that need it.
    repo_dir: str = ""

    #: Input fields the seams *fill in* — for a node (or a sub-workflow) that declares a
    #: parameter of the same name and was not passed one at the callsite.
    #:
    #: This is the same injection `logger` already gets, extended to the run's ambient
    #: inputs, and it exists because the alternative to it is the thing the environment
    #: was covering for: a value every second node needs, restated at ~200 callsites and
    #: at every `handoff` (which constructs a fresh sub-workflow and so propagates
    #: nothing). Restating it is what nobody did, which is why `AGENT_REPO_DIR` was read
    #: from inside the nodes instead.
    #:
    #: It is deliberately **not** "fill any parameter whose name matches a field": that
    #: would silently capture a node's `story`/`epic` argument from an input the state
    #: had chosen not to pass. A workflow lists what it means to make ambient, and the
    #: base lists the one field it declares itself. A callsite that passes the parameter
    #: always wins, and an input that is empty injects nothing — so a node's own default
    #: still applies.
    injects: ClassVar[tuple[str, ...]] = ("repo_dir",)

    #: Bound by the driver before the first state runs.
    _engine: Any = PrivateAttr(default=None)
    _ctx: Any = PrivateAttr(default=None)
    _frozen: bool = PrivateAttr(default=False)

    #: Registered at class-creation time, so an alias collision costs a test rather
    #: than a run. Per-subclass; `states` on the base itself stays empty.
    states: ClassVar[NameIndex[StateSpec]]
    start_state: ClassVar[str] = START_STATE
    #: Transitions this workflow may make before it is declared stuck. 0 = defer to the
    #: run's own budget (``RunConfig.max_transitions``); a class that sets it overrides
    #: the operator's setting, because a flow that legitimately needs 4000 hops knows
    #: that about itself and the operator does not.
    max_transitions: ClassVar[int] = 0

    # --- registration -------------------------------------------------------

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
                    continue  # an override; the subclass's definition already won
                aliases = tuple(getattr(value, STATE_ATTR, ()))
                index.register(name, StateSpec(name, value, aliases), aliases)
        cls.states = index

    @classmethod
    def state_names(cls) -> list[str]:
        """Live names only — what `dot` and `--dry-run` render."""
        return cls.states.live_names()

    @classmethod
    def resolve_state(cls, name: str) -> StateSpec:
        """The state `name` refers to, live or retired, or a loud failure.

        Never a cache miss and never a silent fresh start: a resume that finds no
        matching state has hit an undeclared rename, and saying so is what makes
        `aliases=[...]` a one-line fix rather than an archaeology exercise.
        """
        spec = cls.states.get(name)
        if spec is None:
            known = ", ".join(sorted(cls.states.live_names())) or "(none)"
            raise UnknownStateError(
                f"{cls.__name__} has no state {name!r}. Known states: {known}. If it "
                f"was renamed, declare @state(aliases=[{name!r}]) on the state that "
                "replaced it so runs checkpointed under the old name can resume."
            )
        return spec

    # --- hooks --------------------------------------------------------------

    def setup(self) -> Any:
        """Run once, before the first state, and only once per run.

        Whatever it returns becomes `self.ctx`. A resume **restores** `ctx` from the
        checkpoint rather than calling this again, which is what makes "checkpointed
        once, after setup" in the tier table true rather than aspirational.

        It exists for the residue — a value decided at the top of a run and used only
        at the bottom, which threading through seven uninterested states would be
        worse than the disease. It is not a place to stash progress: states cannot
        write it.
        """
        return None

    def labels(self) -> dict[str, str]:
        """The workflow's own telemetry dimensions, e.g. `{"work_id": self.story}`.

        The engine knows run, node, backend and model; what it cannot know is what
        the run is *working on*, because that vocabulary is the workflow's.

        It is re-read before every transition and sees whatever the instance can —
        inputs, `self.ctx`, `self.output(node)`. An override may **optionally** take
        one argument, the parameters the state about to run was bound with:

            def labels(self, params: Mapping[str, Any]) -> dict[str, str]:
                loop = params.get("loop")
                return {"attempt": str(loop.rework)} if loop else {}

        That is how a rework counter reaches telemetry. A bounded retry budget is
        almost always already a state parameter — it has to be, since state
        parameters are the checkpoint — so the count is right there at the moment
        the labels are read, and no state has to stash a copy of it on `self` for
        instrumentation to find. The engine passes the dict it already holds and
        never inspects it: what counts as a dimension stays the workflow's call.
        """
        return {}

    # --- run-scoped reads ---------------------------------------------------

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

    # --- seams --------------------------------------------------------------

    def call(
        self,
        node: Callable[Concatenate[Logger, P], T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        """Run a blueprint node and return its plain typed value.

        `Concatenate[Logger, P]` strips the injected logger for the type checker, so
        the node stays a plain function a test can call directly while the callsite
        here neither passes nor sees it. The node's *ambient* arguments — the fields
        named in `injects` — are filled the same way, and for the same reason.
        """
        return self._require_engine().call(node, args, self._fill(node, args, kwargs, skip=1))

    def agent(
        self,
        prompt: str,
        *,
        returns: type[T],
        args: dict[str, Any] | None = None,
        power: str | None = None,
        timeout: float | None = None,
        cwd: str | Path | None = None,
        add_dirs: Sequence[str | Path] | None = None,
    ) -> T:
        """Render `prompt`, run an agent turn, and validate the reply into `returns`.

        The one surviving `dict[str, Any]`: a prompt genuinely has no signature to
        check arguments against.

        `power` is the abstract tier ("low"/"medium"/"high") the operator's config maps
        to a concrete model per backend; `timeout` is this turn's wall-clock budget in
        seconds. `cwd` is the working directory the agent CLI is launched in — which is
        what decides whose CLAUDE.md, skills and git context the turn sees — and
        `add_dirs` are further directories it may read. All four default to None =
        whatever the engine defaults to, so a state that says nothing behaves exactly
        as before.

        Unlike the YAML node's fields these are real paths, not Jinja templates: a
        state computes the path in Python and passes it.

        `add_dirs` is a `Sequence`, not a `list`, because it is only read here: a
        `list[str]` — what a state that collects plain paths naturally holds — is not a
        `list[str | Path]`, since a mutable list is invariant in its element type.
        """
        return self._require_engine().agent(
            prompt,
            returns=returns,
            args=args or {},
            power=power,
            timeout=timeout,
            cwd=cwd,
            add_dirs=add_dirs,
        )

    def handoff(self, wf: Callable[P, Any], *args: P.args, **kwargs: P.kwargs) -> Any:
        """Drive another workflow to completion in a sub-scope; return its result.

        The result is the sub-workflow's `Done(...)` value rather than the instance —
        the instance is frozen and holds nothing a caller wants that the result does
        not carry. A `Workflow` subclass is a pydantic model, so the signature being
        checked against is its synthesised `__init__`.

        A sub-workflow is *constructed*, not derived, so nothing crosses this boundary
        that is not an argument. The `injects` fields cross it — a sub-flow declaring
        `repo_dir` works on the same checkout as its parent by definition, and having to
        say so at every handoff is exactly the omission that made the environment look
        necessary.
        """
        return self._require_engine().handoff(wf, args, self._fill(wf, args, kwargs))

    def output(self, node: Callable[..., T]) -> T:
        """The recorded output of a node that already ran, typed by its own return.

        A read, not a fourth tier — nothing is written. Parameters carry what the
        next state *branches on*; this carries what a later state merely consumes,
        so a survey manifest never has to be copied through four checkpoints a human
        is supposed to read.

        Resolves to the **latest** invocation (there is no earlier one: a re-entered
        node overwrites its `output.json`), and **raises** when the node has not run
        — the predecessor returned `""` for "never ran", "unreadable" and
        "legitimately empty" alike.
        """
        return self._require_engine().output(node)

    # --- ambient inputs -----------------------------------------------------

    def _fill(
        self,
        target: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        skip: int = 0,
    ) -> dict[str, Any]:
        """`kwargs` plus every `injects` field `target` declares and the callsite omitted.

        `skip` is how many leading parameters the seam itself supplies — 1 for a node
        (its logger), 0 for a sub-workflow's `__init__` — so that positional arguments
        line up with the right names and an argument already passed *positionally* is
        never also passed by keyword.

        Nothing here can fail a call: an unintrospectable target (a builtin, a C
        callable) simply gets the kwargs it was given.
        """
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
            # An empty input injects nothing: the target's own default is a real answer
            # ("walk up from the cwd"), and overwriting it with a blank would be a lie
            # about the callsite having said something.
            if value not in (None, ""):
                filled[name] = value
        return filled

    # --- freezing -----------------------------------------------------------

    def _bind(self, engine: Any) -> None:
        self._engine = engine

    def _seal(self, ctx: Any) -> None:
        """Install `ctx` and freeze the instance. Called once, after `setup()`."""
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


# The base class itself has no states; giving it an empty index keeps `Workflow.states`
# a real object rather than an AttributeError waiting for a generic caller.
Workflow.states = NameIndex("state", owner="Workflow")
