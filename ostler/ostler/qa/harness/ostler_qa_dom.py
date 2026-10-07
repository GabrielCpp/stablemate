"""The verifiers that read the page's markup beyond what it draws: an element's attribute, and whether keyboard focus sits inside an element."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from ostler_qa_verdicts import Args, Verdict, str_arg, verdict

DOM_WAIT_S = 5.0

_ABSENT = {"present": False}

T = TypeVar("T")


def _elements(observed: object) -> Callable[[], list[object]]:
    """Every element the locator matches, read afresh on each call, or the one element a reader was handed."""
    count = getattr(observed, "count", None)
    if not callable(count):
        return lambda: [observed]
    found = getattr(observed, "nth")

    def matched() -> list[object]:
        matches = count()
        return [found(index) for index in range(matches if isinstance(matches, int) else 0)]

    return matched


def _settled(observed: object, read: Callable[[list[object]], T], done: Callable[[T], bool]) -> T | None:
    """What *read* makes of the matched elements once *done* holds of it, its last reading after `DOM_WAIT_S`, or `None` when nothing ever matched."""
    elements = _elements(observed)
    waits = callable(getattr(observed, "count", None))
    deadline = time.monotonic() + DOM_WAIT_S
    reading: T | None = None
    while True:
        matched = elements()
        if matched:
            reading = read(matched)
            if done(reading):
                return reading
        if not waits or time.monotonic() >= deadline:
            return reading
        time.sleep(0.1)


def _value_matches(value: str | None, args: Args) -> bool:
    if value is None:
        return False
    if "equals" in args:
        return value == str_arg(args, "equals")
    return re.search(str_arg(args, "matches"), value) is not None


@dataclass(frozen=True)
class AttributeReading:
    """The value each matched element carries for the attribute, `None` where one carries none, and whether anything matched."""

    values: tuple[str | None, ...]
    present: bool = True


def read_attribute(observed: object, args: Args) -> AttributeReading:
    name = str_arg(args, "name")

    def read(matched: list[object]) -> tuple[str | None, ...]:
        return tuple(getattr(element, "get_attribute")(name) for element in matched)

    values = _settled(observed, read, lambda values: any(_value_matches(value, args) for value in values))
    return AttributeReading(values=(), present=False) if values is None else AttributeReading(values=values)


def verify_attribute(reading: AttributeReading, args: Args) -> Verdict:
    wanted = {"equals": args["equals"]} if "equals" in args else {"matches": args["matches"]}
    expected = {str_arg(args, "name"): wanted}
    if not reading.present:
        return verdict(False, _ABSENT, expected)
    actual = reading.values[0] if len(reading.values) == 1 else list(reading.values)
    return verdict(any(_value_matches(value, args) for value in reading.values),
                   {str_arg(args, "name"): actual}, expected)


_FOCUS_JS = (
    "el => { const at = document.activeElement; "
    "const where = !at || at === document.body ? 'body' : "
    "at.tagName.toLowerCase() + (at.id ? '#' + at.id : '') + "
    "(at.getAttribute('aria-label') ? '[' + at.getAttribute('aria-label') + ']' : ''); "
    "return [el.contains(at), where]; }"
)


@dataclass(frozen=True)
class FocusedReading:
    """Whether keyboard focus sits on or inside a matched element, and where it sits."""

    inside: bool
    at: str
    present: bool = True


def read_focused(observed: object, args: Args) -> FocusedReading:
    def read(matched: list[object]) -> FocusedReading:
        at = ""
        for element in matched:
            inside, at = getattr(element, "evaluate")(_FOCUS_JS)
            if inside:
                return FocusedReading(inside=True, at=str(at))
        return FocusedReading(inside=False, at=str(at))

    reading = _settled(observed, read, lambda reading: reading.inside)
    return reading if reading is not None else FocusedReading(inside=False, at="", present=False)


def verify_focused(reading: FocusedReading, args: Args) -> Verdict:
    if not reading.present:
        return verdict(False, _ABSENT, {"focused": True})
    return verdict(reading.inside, {"focused": reading.inside, "at": reading.at}, {"focused": True})
