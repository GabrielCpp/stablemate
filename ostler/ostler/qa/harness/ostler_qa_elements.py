"""The verifiers that observe a page: whether an element is shown and how many, takes an action, takes focus, how many were emitted, the title and the console."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sized
from dataclasses import dataclass
from urllib.parse import urlsplit

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
    """Whether the subject is shown, every spelling of its text when the check reads text, and how many are shown when it counts."""

    shown: bool
    readings: tuple[str, ...]
    count: int | None = None
    absent_at: str | None = None


COUNT_WAIT_S = 3.0


def _shown(element: object, args: Args) -> bool:
    if not getattr(element, "is_visible")():
        return False
    return "text" not in args or any(str_arg(args, "text") in each for each in _readings(element))


def _count_shown(observed: object, args: Args) -> VisibilityReading:
    """How many elements the locator matches are shown, once a screen that draws them late has had time to."""
    count = getattr(observed, "count", None)
    if not callable(count):
        raise TypeError(f"`visible(count=...)` counts the elements a locator matches, not {type(observed).__name__}")
    found = getattr(observed, "nth")
    deadline = time.monotonic() + COUNT_WAIT_S
    while True:
        matches = count()
        shown = sum(1 for index in range(matches if isinstance(matches, int) else 0) if _shown(found(index), args))
        if shown == args["count"] or time.monotonic() >= deadline:
            return VisibilityReading(shown=shown > 0, readings=(), count=shown)
        time.sleep(0.1)


def read_visibility(observed: object, args: Args) -> VisibilityReading:
    if "count" in args:
        return _count_shown(observed, args)
    is_visible = getattr(observed, "is_visible", None)
    if callable(is_visible):
        shown = bool(is_visible())
        if not shown and not _attached(observed):
            return VisibilityReading(shown=False, readings=(), absent_at=_page_path(observed))
        shown = shown or bool(is_visible())
        return VisibilityReading(shown=shown, readings=_readings(observed) if shown and "text" in args else ())
    readings = (str(observed),) if "text" in args and observed is not None else ()
    return VisibilityReading(shown=bool(observed), readings=readings)


def verify_visible(reading: VisibilityReading, args: Args) -> Verdict:
    if "count" in args:
        return verdict(reading.count == args["count"], {"shown": reading.count}, {"shown": args["count"]})
    if reading.absent_at is not None:
        expected = {"visible": True, "text": str_arg(args, "text")} if "text" in args else {"visible": True}
        return verdict(False, {"present": False, "at": reading.absent_at}, expected)
    if "text" not in args:
        return verdict(reading.shown, {"visible": reading.shown}, {"visible": True})
    text = reading.readings[0] if reading.readings else None
    contains = reading.shown and any(str_arg(args, "text") in each for each in reading.readings)
    return verdict(contains, {"visible": reading.shown, "text": text}, {"visible": True, "text": str_arg(args, "text")})


HIDE_WAIT_S = 3.0


def read_hidden(observed: object, args: Args) -> VisibilityReading:
    """Whether any element the locator matches is still shown, once a closing element has had time to leave."""
    count = getattr(observed, "count", None)
    if not callable(count):
        return read_visibility(observed, {})
    deadline = time.monotonic() + HIDE_WAIT_S
    while True:
        found = getattr(observed, "nth")
        matches = count()
        shown = any(found(index).is_visible() for index in range(matches if isinstance(matches, int) else 0))
        if not shown or time.monotonic() >= deadline:
            return VisibilityReading(shown=shown, readings=())
        time.sleep(0.1)


def verify_hidden(reading: VisibilityReading, args: Args) -> Verdict:
    return verdict(not reading.shown, {"visible": reading.shown}, {"visible": False})


ATTACH_WAIT_S = 5.0


def _attached(observed: object) -> bool:
    """Whether the locator matches an element, once a screen that renders it late has had time to."""
    count = getattr(observed, "count", None)
    if not callable(count):
        return True
    deadline = time.monotonic() + ATTACH_WAIT_S
    while not count():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


_ABSENT = {"present": False}


def _page_path(observed: object) -> str:
    """The address of the page a locator searched, or `""` when it carries none."""
    url = str(getattr(getattr(observed, "page", None), "url", "") or "")
    return urlsplit(url).path if url else ""


@dataclass(frozen=True)
class ControlReading:
    """Whether the control is on the page, and whether the product will let a user act on it."""

    enabled: bool
    present: bool = True

    def actual(self) -> dict[str, bool]:
        return {"actionable": self.enabled} if self.present else _ABSENT


def read_control(check: str) -> Callable[[object, Args], ControlReading]:
    def read(observed: object, args: Args) -> ControlReading:
        is_enabled = getattr(observed, "is_enabled", None)
        if not callable(is_enabled):
            raise TypeError(
                f"{check} observes whether a control accepts the action — pass the element "
                f"itself, not {type(observed).__name__}"
            )
        if not _attached(observed):
            return ControlReading(enabled=False, present=False)
        return ControlReading(enabled=bool(is_enabled()))

    return read


def verify_actionable(reading: ControlReading, args: Args) -> Verdict:
    return verdict(reading.present and reading.enabled, reading.actual(), {"actionable": True})


def verify_inert(reading: ControlReading, args: Args) -> Verdict:
    return verdict(reading.present and not reading.enabled, reading.actual(), {"actionable": False})


@dataclass(frozen=True)
class FocusReading:
    """Whether a real keypress reached the control, and whether the key `activates` names then clicked it, when it names one."""

    focused: bool
    activated: bool | None
    present: bool = True


def read_focus(observed: object, args: Args) -> FocusReading:
    """Reachable by a real keypress, and — when `activates` names one — responsive to it."""
    focus = getattr(observed, "focus", None)
    if not callable(focus):
        raise TypeError(
            f"focusable observes a control through real keyboard focus — pass the element "
            f"itself, not {type(observed).__name__}"
        )
    if not _attached(observed):
        return FocusReading(focused=False, activated=None, present=False)
    focus()
    evaluate = getattr(observed, "evaluate")
    focused = bool(evaluate("el => el === document.activeElement"))
    if "activates" not in args:
        return FocusReading(focused=focused, activated=None)
    if not focused:
        return FocusReading(focused=False, activated=False)
    page = getattr(observed, "page")
    held = getattr(observed, "element_handle")()
    expanded = held.evaluate(
        "el => { window.__ostlerActivated = false; "
        "el.addEventListener('click', () => { window.__ostlerActivated = true; }, {once: true}); "
        "return el.getAttribute('aria-expanded'); }"
    )
    page.keyboard.press(args["activates"])
    if bool(page.evaluate("() => window.__ostlerActivated === true")):
        return FocusReading(focused=True, activated=True)
    return FocusReading(focused=True, activated=expanded == "false" and _opened(held))


def _opened(held: object) -> bool:
    """Whether a control that opens a popup on the keypress itself, with no click, now reports it open. *held* is the element itself, because an open popup hides the control from a lookup by role."""
    return getattr(held, "evaluate")("el => el.isConnected && el.getAttribute('aria-expanded')") == "true"


def verify_focusable(reading: FocusReading, args: Args) -> Verdict:
    if not reading.present:
        return verdict(False, _ABSENT, {"focused": True, "activated": True} if "activates" in args else {"focused": True})
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


TITLE_WAIT_S = 3.0


def _title_matches(title: str, args: Args) -> bool:
    if "equals" in args:
        return title == str_arg(args, "equals")
    return re.search(str_arg(args, "matches"), title) is not None


@dataclass(frozen=True)
class TitleReading:
    """The document title, once a screen that sets it late has had time to."""

    title: str


def read_title(observed: object, args: Args) -> TitleReading:
    title = getattr(observed, "title", None)
    if isinstance(observed, str) or not callable(title):
        return TitleReading(title=str(observed))
    deadline = time.monotonic() + TITLE_WAIT_S
    while True:
        read = str(title())
        if _title_matches(read, args) or time.monotonic() >= deadline:
            return TitleReading(title=read)
        time.sleep(0.1)


def verify_title(reading: TitleReading, args: Args) -> Verdict:
    expected = {"equals": args["equals"]} if "equals" in args else {"matches": args["matches"]}
    return verdict(_title_matches(reading.title, args), reading.title, expected)


CONSOLE_LEVELS = {"warn": "warning"}


@dataclass(frozen=True)
class ConsoleReading:
    """The console messages the claim names, by their text."""

    texts: tuple[str, ...]


def read_console(observed: object, args: Args) -> ConsoleReading:
    if not isinstance(observed, list):
        raise TypeError(f"`console` reads a list of console messages, not {type(observed).__name__}")
    level = CONSOLE_LEVELS.get(str(args.get("level", "")), str(args.get("level", "")))
    texts: list[str] = []
    for entry in observed:
        text = str(entry.get("text", "")) if isinstance(entry, dict) else str(entry)
        kind = str(entry.get("type", "")) if isinstance(entry, dict) else ""
        if level and kind != level:
            continue
        if "text" in args and str_arg(args, "text") not in text:
            continue
        if "matches" in args and re.search(str_arg(args, "matches"), text) is None:
            continue
        texts.append(text)
    return ConsoleReading(texts=tuple(texts))


def verify_console(reading: ConsoleReading, args: Args) -> Verdict:
    found = len(reading.texts)
    if "count" in args:
        return verdict(found == args["count"], list(reading.texts), {"count": args["count"]})
    return verdict(found > 0, list(reading.texts), "at least one")
