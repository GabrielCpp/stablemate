"""Which journeys and cells call a set of named endpoints, interactions or outside happenings, found on the model alone."""

from __future__ import annotations

from datetime import date
from typing import Any

from ostler.book.arrange import Arrange
from ostler.book.inputs import plays
from ostler.book.service import Service


def touches(service: Service[Any], journey: Any, names: frozenset[str]) -> bool:
    """Whether the journey calls one of the named endpoints, or arranges one of the named outside happenings,
    found on the model alone. A journey the model cannot walk is kept, so a broken one is never left out."""
    model = service.new_model(date.today())
    try:
        for given in journey.given:
            if type(given.request).__name__ in names:
                return True
            model.perform(given.request)
        for step in journey().steps(model.today):
            if not plays(type(step)) and not isinstance(step, Arrange):
                continue
            if type(step).__name__ in names:
                return True
            if getattr(type(step), "carries", None) is not None:
                model.perform(step)
    except Exception:
        return True
    return False


def aims(service: Service[Any], axes: Any, scene: Any, name: str, names: frozenset[str]) -> bool:
    """Whether a declared cell calls one of the named endpoints, or is reached by one of the named outside
    happenings, found on the model alone. A cell the model cannot build is kept."""
    try:
        action = axes.actions[name](scene.arrange(service.new_model(axes.today)))
        if type(action).__name__ in names:
            return True
        outside = names & {o.__name__ for o in service.outside}
        return bool(outside) and any(type(step).__name__ in outside for step in scene.reached_by(axes.today))
    except Exception:
        return True
