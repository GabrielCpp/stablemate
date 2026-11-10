"""The axes of a lifecycle matrix: one record, the scenes it can be in, and the
actions that reach it there. Each scene names the condition that tells a reader
the record is in it and the steps that bring a fresh service there, so an agent
can arrange it on the model or on the live surface when a scenario nobody
scripted needs it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Generic, Iterable, TypeVar

from ostler.book.model import Model

S = TypeVar("S", bound=Model)


@dataclass(frozen=True)
class Scene:
    name: str
    when: str
    reached_by: Callable[[date], Iterable[object]]
    """The steps from a fresh service, as a tuple, or as a generator where a
    step is built from what the step before it was answered."""

    def arrange(self, model: S) -> S:
        for step in self.reached_by(model.today):
            model.apply(step)
        return model

    def describe(self, today: date) -> str:
        steps = tuple(self.reached_by(today))
        path = "; ".join(str(step) for step in steps) if steps else "a fresh service, nothing done"
        return f"- **{self.name}**: {self.when}. Reached by: {path}."


@dataclass(frozen=True)
class Impossible:
    """What an action gives in a scene where it cannot be taken, and why: the
    pair the matrix reports as impossible and the run does not play."""

    why: str


@dataclass(frozen=True)
class Axes(Generic[S]):
    """`state_of` reads the scene one entity of the record is in; `entities`
    lists the record's entities on a model, and is left out where the record is
    the app itself."""

    record: str
    today: date
    scenes: tuple[Scene, ...]
    actions: dict[str, Callable[[S], object]]
    told_apart: Callable[[S], str]
    state_of: Callable[[S, object], str] | None = None
    entities: Callable[[S], Iterable[object]] | None = None
    standing: Callable[[S, object], str] | None = None

    def states(self, model: S) -> tuple[str, ...]:
        """The scene each entity of the record is in, read off the model, sorted.
        A record with no `entities` is the model itself, one entity."""
        if self.state_of is None:
            raise KeyError(f"the matrix {self.record!r} declares no state_of")
        found = self.entities(model) if self.entities is not None else (model,)
        return tuple(sorted(self.state_of(model, entity) for entity in found))

    def marks(self, model: S) -> tuple[str, ...]:
        """The scene each entity is in, with the standing the record declares
        beside the scene when it declares one, sorted."""
        if self.state_of is None:
            raise KeyError(f"the matrix {self.record!r} declares no state_of")
        found = self.entities(model) if self.entities is not None else (model,)
        if self.standing is None:
            return tuple(sorted(self.state_of(model, entity) for entity in found))
        return tuple(sorted(f"{self.state_of(model, entity)}, {self.standing(model, entity)}" for entity in found))

    def scene(self, name: str) -> Scene:
        for scene in self.scenes:
            if scene.name == name:
                return scene
        raise KeyError(f"no scene named {name!r}; the scenes are " + ", ".join(s.name for s in self.scenes))
