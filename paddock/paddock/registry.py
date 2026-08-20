"""What a task module declares, and the registry that collects it.

Mirrors `ostler_qa`: a task module makes module-level declaration calls and decorates
functions, and importing it is what builds the record. The rules are the same ones, for
the same reason — a wrong key in Python raises with a line number:

* exactly one `task()` call per module, and it comes before the steps;
* `@step()` functions run in declaration order, and a duplicate name is an error rather
  than a silent overwrite;
* `score` is picked up by name from the module, and is optional.

Validation is fail-closed at import: a module that declares nothing, or declares twice,
raises rather than producing an empty task the runner would happily execute to no effect.
"""

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
    """What a task's own ruler measured. Serialized as `score.json` beside the result.

    `headline` is the one line a human reads; `detail` is the lines under it; `data` is
    the machine-readable body — the per-row verdicts a later comparison needs, which a
    printed line cannot carry.
    """

    headline: str
    detail: tuple[str, ...] = ()
    data: Mapping[str, Any] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {"headline": self.headline, "detail": list(self.detail), "data": dict(self.data)}

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
    """Declare the module's one task: what it is called, what it starts from, how it runs.

    `config` is a repo-relative path to a full stablemate config TOML. A task swaps models
    by swapping that file — the config carries the `[power.*]` / `[profiles.*]` tables,
    which is why the harness has no model vocabulary of its own.
    """
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
    """Register a step. Steps run in declaration order, each taking the `Run` handle.

    Steps are functions, not schema entries, precisely so the setup that is *not* a
    workflow invocation — overwriting a defect variant, bringing a compose stack up,
    materializing a per-trial tree — needs no escape hatch to exist.
    """

    def decorate(fn: StepFn) -> StepFn:
        # `StepFn` is a Callable, and not every callable carries a `__name__` — a step
        # written as a partial or a callable object is legal and just has to be named.
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
    """Freeze what the module declared into a `Task`. Called by the loader after import."""
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
