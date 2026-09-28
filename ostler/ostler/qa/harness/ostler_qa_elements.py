"""The verifiers that observe page elements: whether one is shown, takes an action, takes focus, and how many were emitted."""

from __future__ import annotations

from collections.abc import Callable, Sized
from dataclasses import dataclass

from ostler_qa_verdicts import Args, Verdict, str_arg, verdict


def _readings(observed: object) -> tuple[str, ...]:
    """Every spelling of an element's text the page can offer, rendered first."""
    readings: list[str] = []
    for reader in ("inner_text", "text_content"):
        read = getattr(observed, reader, None)
        if read is None:
            continue
        value = read()
        if value is not None and str(value) not in readings:
            readings.append(str(value))
    return tuple(readings)


@dataclass(frozen=True)
class VisibilityReading:
    """Whether the subject is shown, and every spelling of its text when the check reads text."""

    shown: bool
    readings: tuple[str, ...]


def read_visibility(observed: object, args: Args) -> VisibilityReading:
    is_visible = getattr(observed, "is_visible", None)
    if callable(is_visible):
        shown = bool(is_visible())
        return VisibilityReading(shown=shown, readings=_readings(observed) if shown and "text" in args else ())
    readings = (str(observed),) if "text" in args and observed is not None else ()
    return VisibilityReading(shown=bool(observed), readings=readings)


def verify_visible(reading: VisibilityReading, args: Args) -> Verdict:
    if "text" not in args:
        return verdict(reading.shown, {"visible": reading.shown}, {"visible": True})
    text = reading.readings[0] if reading.readings else None
    contains = reading.shown and any(str_arg(args, "text") in each for each in reading.readings)
    return verdict(contains, {"visible": reading.shown, "text": text}, {"visible": True, "text": str_arg(args, "text")})


@dataclass(frozen=True)
class ControlReading:
    """Whether the product will let a user act on this control."""

    enabled: bool


def read_control(check: str) -> Callable[[object, Args], ControlReading]:
    def read(observed: object, args: Args) -> ControlReading:
        is_enabled = getattr(observed, "is_enabled", None)
        if not callable(is_enabled):
            raise TypeError(
                f"{check} observes whether a control accepts the action — pass the element "
                f"itself, not {type(observed).__name__}"
            )
        return ControlReading(enabled=bool(is_enabled()))

    return read


def verify_actionable(reading: ControlReading, args: Args) -> Verdict:
    return verdict(reading.enabled, {"actionable": reading.enabled}, {"actionable": True})


def verify_inert(reading: ControlReading, args: Args) -> Verdict:
    return verdict(not reading.enabled, {"actionable": reading.enabled}, {"actionable": False})


@dataclass(frozen=True)
class FocusReading:
    """Whether a real keypress reached the control, and whether the key `activates` names then clicked it, when it names one."""

    focused: bool
    activated: bool | None


def read_focus(observed: object, args: Args) -> FocusReading:
    """Reachable by a real keypress, and — when `activates` names one — responsive to it."""
    focus = getattr(observed, "focus", None)
    if not callable(focus):
        raise TypeError(
            f"focusable observes a control through real keyboard focus — pass the element "
            f"itself, not {type(observed).__name__}"
        )
    focus()
    evaluate = getattr(observed, "evaluate")
    focused = bool(evaluate("el => el === document.activeElement"))
    if "activates" not in args:
        return FocusReading(focused=focused, activated=None)
    if not focused:
        return FocusReading(focused=False, activated=False)
    evaluate(
        "el => { el.__ostlerActivated = false; "
        "el.addEventListener('click', () => { el.__ostlerActivated = true; }, {once: true}); }"
    )
    getattr(observed, "page").keyboard.press(args["activates"])
    return FocusReading(focused=True, activated=bool(evaluate("el => el.__ostlerActivated === true")))


def verify_focusable(reading: FocusReading, args: Args) -> Verdict:
    if reading.activated is None:
        return verdict(reading.focused, {"focused": reading.focused}, {"focused": True})
    return verdict(
        reading.focused and reading.activated,
        {"focused": reading.focused, "activated": reading.activated},
        {"focused": True, "activated": True},
    )


@dataclass(frozen=True)
class SizeReading:
    """How many things were emitted."""

    size: int


def read_size(observed: object, args: Args) -> SizeReading:
    if not isinstance(observed, Sized):
        raise TypeError(f"object of type '{type(observed).__name__}' has no len()")
    return SizeReading(size=len(observed))


def verify_emitted(reading: SizeReading, args: Args) -> Verdict:
    if "count" in args:
        return verdict(reading.size == args["count"], reading.size, args["count"])
    return verdict(reading.size > 0, reading.size, "at least one")
