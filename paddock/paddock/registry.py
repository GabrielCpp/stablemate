"""What a task module declares, and the registry that collects it."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - the runner imports the registry, not the reverse
    from paddock.runner import Run

Input = str | float | int | bool | list[str]

StepFn = Callable[["Run"], None]
ScoreFn = Callable[["Run"], "Score"]


class TaskError(RuntimeError):
    """A task module that does not declare a runnable task."""


@dataclass(frozen=True, slots=True)
class Score:
    """What a task's own ruler measured."""

    headline: str
    detail: tuple[str, ...] = ()
    data: Mapping[str, Any] = field(default_factory=dict)

    caveats: tuple[str, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {"headline": self.headline, "detail": list(self.detail),
                "caveats": list(self.caveats), "data": dict(self.data)}

    def render(self) -> str:
        return "\n".join((self.headline, *self.detail))


@dataclass(frozen=True, slots=True)
class Step:
    name: str
    fn: StepFn
    doc: str = ""


@dataclass(frozen=True, slots=True)
class Task:
    """A fully declared task, as the loader hands it to the runner."""

    name: str
    config: Mapping[str, object]
    inputs: Mapping[str, Input]
    steps: tuple[Step, ...]
    score: ScoreFn | None
    module: str = ""
    doc: str = ""

    def describe(self) -> str:
        scored = "scored" if self.score else "unscored"
        return f"{self.name}  {len(self.steps)} steps  {scored}"


@dataclass
class _Draft:
    name: str
    config: Mapping[str, object]
    inputs: Mapping[str, Input]
    steps: list[Step] = field(default_factory=list)
    score: ScoreFn | None = None


@dataclass
class _Registry:
    """Module-scoped state, reset by the loader before each task module is imported."""

    drafts: list[_Draft] = field(default_factory=list)

    def reset(self) -> None:
        self.drafts = []

    def current(self, what: str) -> _Draft:
        if not self.drafts:
            raise TaskError(f"{what} declared before task() — call task() first")
        return self.drafts[-1]


REGISTRY = _Registry()


def task(
    *, name: str, config: Mapping[str, object] | None = None, inputs: Mapping[str, Input] | None = None
) -> None:
    """Open a task: its name, the config it lays over the benchmark's and the inputs its steps read."""
    if not name:
        raise TaskError("task() needs a name")
    if any(draft.name == name for draft in REGISTRY.drafts):
        raise TaskError(f"task {name!r} is declared twice in this module")
    REGISTRY.drafts.append(_Draft(name=name, config=dict(config or {}), inputs=dict(inputs or {})))


def step(*, name: str = "") -> Callable[[StepFn], StepFn]:
    """Register a step on the most recently opened task."""

    def decorate(fn: StepFn) -> StepFn:
        given = getattr(fn, "__name__", "")
        draft = REGISTRY.current(f"@step {given or fn!r}")
        step_name = name or given
        if not step_name:
            raise TaskError(f"@step {fn!r} has no name — pass @step(name=...)")
        if any(existing.name == step_name for existing in draft.steps):
            raise TaskError(f"step {step_name!r} is declared twice in task {draft.name!r}")
        draft.steps.append(Step(name=step_name, fn=fn, doc=(fn.__doc__ or "").strip()))
        return fn

    return decorate


def score() -> Callable[[ScoreFn], ScoreFn]:
    """Bind a score function to the most recently opened task."""

    def decorate(fn: ScoreFn) -> ScoreFn:
        draft = REGISTRY.current(f"@score {getattr(fn, '__name__', '') or fn!r}")
        if draft.score is not None:
            raise TaskError(f"task {draft.name!r} already has a score")
        draft.score = fn
        return fn

    return decorate


def collect(module_name: str, doc: str = "") -> tuple[Task, ...]:
    """Freeze what the module declared into its `Task`s."""
    if not REGISTRY.drafts:
        raise TaskError(f"{module_name}: no task() call — the module declares no task")
    for draft in REGISTRY.drafts:
        if not draft.steps:
            raise TaskError(f"{module_name}: task {draft.name!r} declares no steps")
    return tuple(
        Task(
            name=draft.name,
            config=draft.config,
            inputs=draft.inputs,
            steps=tuple(draft.steps),
            score=draft.score,
            module=module_name,
            doc=doc,
        )
        for draft in REGISTRY.drafts
    )


def step_names(steps: Sequence[Step]) -> tuple[str, ...]:
    return tuple(item.name for item in steps)
