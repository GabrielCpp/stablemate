"""The state table played on the live service: each scene of each record is
arranged with the steps that reach it, each action the model builds there is
taken, and the model and the app are compared. A cell that passes and leaves
the model's state as it was hands its arrangement to the next cell of the
scene, so the reads of one scene are taken on one arrangement."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable

from ostler.book.backstage import CannotArrange
from ostler.book.model import Defect, Model
from ostler.book.runner import attempt
from ostler.book.state import Impossible
from ostler.book.surface import Surface


@dataclass
class CellRun:
    record: str
    scene: str
    action: str
    ok: bool
    note: str = ""
    outcome: str = ""
    why: str = ""
    known: Defect[Any, Any] | None = None
    skipped: str = ""

    @property
    def text(self) -> str:
        return f"{self.record}:{self.scene} x {self.action}"

    @property
    def verdict(self) -> str:
        return "SKIP" if self.skipped else "IMPOSSIBLE" if self.why else "PASS" if self.ok else "FAIL"


@dataclass
class Played:
    """What the cells met, in the shape the defect report reads."""

    cells: list[CellRun] = field(default_factory=list)
    arrangements: int = 0
    journey: Any = field(default_factory=lambda: SimpleNamespace(title=lambda: "the state table"))

    @property
    def defects(self) -> list[Defect[Any, Any]]:
        return [c.known for c in self.cells if c.known is not None]

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.cells)

    @property
    def count(self) -> int:
        return sum(1 for c in self.cells if not c.why and not c.skipped)


def play(matrices: tuple[Any, ...], surface: Surface, fresh: Callable[[], Model],
         keep: Callable[[Any, Any, str], bool] = lambda axes, scene, name: True) -> Played:
    played = Played()
    for axes in matrices:
        for scene in axes.scenes:
            world: Model | None = None
            for name, build in axes.actions.items():
                if keep(axes, scene, name):
                    if world is None:
                        played.arrangements += 1
                    cell, world = one(axes, scene, name, build, surface, fresh, world)
                    played.cells.append(cell)
    return played


def one(axes: Any, scene: Any, name: str, build: Callable[[Model], object], surface: Surface,
        fresh: Callable[[], Model], world: Model | None = None) -> tuple[CellRun, Model | None]:
    """Plays one cell, on `world` when the cell before left the scene arranged.
    Hands back the cell and the arrangement, or None once the cell changed it."""
    cell = CellRun(axes.record, scene.name, name, True)
    model = world
    if model is None:
        try:
            model = fresh()
        except CannotArrange as cannot:
            cell.skipped = cannot.reason
            return cell, None
        for step in scene.reached_by(model.today):
            arranged = attempt(step, model, surface)
            if arranged.skipped:
                cell.skipped = arranged.skipped
                return cell, None
            if not arranged.ok:
                cell.ok, cell.note = False, f"the scene cannot be arranged: {arranged.text}: {arranged.note}"
                return cell, None
    try:
        action = build(model)
    except Exception as crash:
        cell.ok, cell.note = False, f"the action cannot be built: {type(crash).__name__}: {crash}"
        return cell, None
    if isinstance(action, Impossible):
        cell.why = action.why
        return cell, model
    if action is None:
        cell.ok, cell.note = False, "the action is None where the pair is impossible: give Impossible(why)"
        return cell, None
    before = model.key()
    taken = attempt(action, model, surface)
    if taken.skipped:
        cell.skipped = taken.skipped
        return cell, None
    cell.ok, cell.note, cell.known = taken.ok, taken.note, taken.known
    cell.outcome = f"{taken.model} / {taken.app}"
    return cell, model if taken.ok and taken.known is None and model.key() == before else None
