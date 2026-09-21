"""What a task module declares, and the registry that collects it."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - the runner imports the registry, not the reverse
    from paddock.runner import Run

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
    seed: str
    config: str
    steps: tuple[Step, ...]
    score: ScoreFn | None
    module: str = ""
    doc: str = ""

    def describe(self) -> str:
        scored = "scored" if self.score else "unscored"
        return f"{self.name}  seed={self.seed}  {len(self.steps)} steps  {scored}"


@dataclass
class _Registry:
    """Module-scoped state, reset by the loader before each task module is imported."""

    name: str = ""
    seed: str = ""
    config: str = ""
    steps: list[Step] = field(default_factory=list)

    def reset(self) -> None:
        self.name = ""
        self.seed = ""
        self.config = ""
        self.steps = []

    def declared(self) -> bool:
        return bool(self.name)


REGISTRY = _Registry()


def task(*, name: str, seed: str, config: str) -> None:
    """Declare the module's one task: what it is called, what it starts from, how it runs."""
    if REGISTRY.declared():
        raise TaskError(f"task() was already called as {REGISTRY.name!r}; a module declares one task")
    if not name or not seed or not config:
        raise TaskError("task() needs a name, a seed and a config")
    if REGISTRY.steps:
        raise TaskError("task() must be called before any @step — it names what the steps run in")
    REGISTRY.name = name
    REGISTRY.seed = seed
    REGISTRY.config = config


def step(*, name: str = "") -> Callable[[StepFn], StepFn]:
    """Register a step."""

    def decorate(fn: StepFn) -> StepFn:
        given = getattr(fn, "__name__", "")
        if not REGISTRY.declared():
            raise TaskError(f"@step {given or fn!r} declared before task() — call task() first")
        step_name = name or given
        if not step_name:
            raise TaskError(f"@step {fn!r} has no name — pass @step(name=...)")
        if any(existing.name == step_name for existing in REGISTRY.steps):
            raise TaskError(f"step {step_name!r} is declared twice in this module")
        REGISTRY.steps.append(Step(name=step_name, fn=fn, doc=(fn.__doc__ or "").strip()))
        return fn

    return decorate


def collect(module_name: str, score: ScoreFn | None, doc: str = "") -> Task:
    """Freeze what the module declared into a `Task`."""
    if not REGISTRY.declared():
        raise TaskError(f"{module_name}: no task() call — the module declares no task")
    if not REGISTRY.steps:
        raise TaskError(f"{module_name}: task {REGISTRY.name!r} declares no steps")
    return Task(
        name=REGISTRY.name,
        seed=REGISTRY.seed,
        config=REGISTRY.config,
        steps=tuple(REGISTRY.steps),
        score=score,
        module=module_name,
        doc=doc,
    )


def step_names(steps: Sequence[Step]) -> tuple[str, ...]:
    return tuple(item.name for item in steps)
