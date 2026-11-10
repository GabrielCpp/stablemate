"""The lifecycle matrix, computed from the model rather than written by hand:
for each scene of a record and each action, what the model does, told as the
primitives its reducer produced. Above the table, each scene says how a reader
knows the record is in it and how to get there, so any cell can be walked on
the live service with the walk command. The same cells draw the state graph."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from ostler.book.domain import Change, Transaction
from ostler.book.model import Model
from ostler.book.outcome import Flawed, Refusal
from ostler.book.status import Status
from ostler.book.state import Axes, Impossible


@dataclass(frozen=True)
class Cell:
    """What one action does to the record in one scene."""

    scene: str
    action: str
    kind: str
    target: str = ""
    changes: tuple[Change, ...] = ()
    status: Status | None = None
    message: str = ""
    why: str = ""

    @property
    def owned_by_nobody(self) -> bool:
        return self.action.startswith("on:")

    def brief(self) -> str:
        if self.kind in ("refuse", "defect"):
            return f"{self.kind} {self.status} {self.message}"
        if self.kind == "transition":
            return f"→ {self.target}" + "".join(f" · {c.brief()}" for c in self.changes)
        return self.kind

    def __str__(self) -> str:
        if self.kind in ("refuse", "defect"):
            return f"{self.kind} {self.status} {self.message}"
        if self.kind == "transition":
            return f"→ {self.target}" + "".join(f" · {c}" for c in self.changes)
        return self.kind


def cell(scene: str, name: str, model: Model, action: object, told_apart: Callable[[Model], str]) -> Cell:
    outcome = model.perform(action)
    if isinstance(outcome, Flawed):
        return Cell(scene, name, "defect", status=outcome.defect.status, message=outcome.defect.message)
    if isinstance(outcome, Refusal):
        return Cell(scene, name, "refuse", status=outcome.status, message=outcome.message)
    log = getattr(model, "log", None)
    reduced = log[-1].result if log else None
    if isinstance(reduced, Transaction) and not reduced.changes:
        return Cell(scene, name, "no-op")
    changes: tuple[Change, ...] = ()
    if isinstance(reduced, Transaction):
        changes = reduced.changes
    elif isinstance(reduced, Change):
        changes = (reduced,)
    return Cell(scene, name, "transition", target=told_apart(model), changes=changes)


def cells(new_model: Callable[[date], Model], axes: Axes[Any]) -> list[Cell]:
    found: list[Cell] = []
    for scene in axes.scenes:
        for name, build in axes.actions.items():
            model = scene.arrange(new_model(axes.today))
            action = build(model)
            if action is None or isinstance(action, Impossible):
                found.append(Cell(scene.name, name, "impossible", why=getattr(action, "why", "")))
            else:
                found.append(cell(scene.name, name, model, action, axes.told_apart))
    return found


def matrix(new_model: Callable[[date], Model], axes: Axes[Any]) -> str:
    lines = [f"## {axes.record}", "", f"Computed on the model with today = {axes.today.isoformat()}.", "", "### Scenes", ""]
    lines += [scene.describe(axes.today) for scene in axes.scenes]
    lines += ["", "### What each action does in each scene", ""]
    lines.append(f"| {axes.record} ↓ / action → | " + " | ".join(axes.actions) + " |")
    lines.append("|" + "---|" * (len(axes.actions) + 1))
    by_scene: dict[str, list[Cell]] = {}
    for c in cells(new_model, axes):
        by_scene.setdefault(c.scene, []).append(c)
    for scene in axes.scenes:
        lines.append(f"| {scene.name} | " + " | ".join(str(c) for c in by_scene[scene.name]) + " |")
    return "\n".join(lines)
