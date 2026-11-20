"""Where an interaction leaves the person, as the surface shows it after the act. A `leads_to` the book states is
verified and a miss fails the step. An act that states none must leave the person on its screen, and one that does not
is noted, and the run lists it once at its end."""

from __future__ import annotations

from typing import Any, Callable, cast

from ostler.book.journey import StepResult
from ostler.book.outcome import Done, Refusal
from ostler.book.screen import Interaction, Screen
from ostler.book.surface import Surface


class Leaving:
    """The interactions of this run that left their screen with no `leads_to` stated. Class state, like `Landings`: a run
    is one process."""

    names: dict[str, None] = {}

    @classmethod
    def begin(cls) -> None:
        cls.names = {}

    @classmethod
    def line(cls) -> str:
        """The one line that names them, or nothing when none left."""
        if not cls.names:
            return ""
        return f"{len(cls.names)} interactions left their screen with no leads_to stated: {', '.join(cls.names)}"


def expected(interaction: Interaction[Any], result: StepResult) -> tuple[type[Screen] | None, bool]:
    """The screen the person is on once the step went through, and whether the book states it with `leads_to`. An act the
    model refused, or the app where the model does not carry the act, leaves the person where they were."""
    kind = type(interaction)
    refused = isinstance(result.model, Refusal) or (result.model is None and isinstance(result.app, Refusal))
    if kind.leads_to is not None and not refused:
        return kind.leads_to, True
    return kind.screen, False


def judge(step: object, result: StepResult, surface: Surface) -> None:
    """Checks where an interaction step left the person and adds what it finds to the step result."""
    if not isinstance(step, Interaction) or result.skipped or not result.ok:
        return
    if not (isinstance(result.app, (Done, Refusal)) and (result.model is None or isinstance(result.model, (Done, Refusal)))):
        return
    screen, stated = expected(cast("Interaction[Any]", step), result)
    if screen is None:
        return
    if stated:
        arrive = cast("Callable[[type[Screen]], bool | None] | None", getattr(surface, "arrive", None))
        if callable(arrive) and arrive(screen) is False:
            result.ok = False
            result.note = _added(result.note, f"the act did not land on {screen.__name__}: the book states it leads there")
        return
    on = cast("Callable[[type[Screen]], bool | None] | None", getattr(surface, "on", None))
    if callable(on) and on(screen) is False:
        Leaving.names[type(step).__name__] = None
        result.note = _added(result.note, f"the act left {screen.__name__} and the book states no leads_to")


def _added(note: str, more: str) -> str:
    return f"{note}; {more}" if note else more
