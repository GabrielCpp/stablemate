"""A screen settling: the requests it sends answer, its busy sign goes, and one declared state holds."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ostler_qa_elements import name_pattern

ANNOUNCED_ROLES = frozenset({"alert", "status"})

TICK_MS = 50

ROLE_STATES = ("disabled", "checked", "expanded", "selected")


@dataclass(frozen=True)
class Settled:
    """How a settle ended: whether the expected state held, the sentence that says so, and the state that did."""

    passed: bool
    message: str
    held: str | None


class Reading(Protocol):
    """One look at a screen, which can tell whether a perceivable is shown."""

    def shown(self, perceivable: Mapping[str, Any]) -> bool: ...


class Screen(Protocol):
    """Where a settle looks: a page in a browser, or the view hierarchy of a device."""

    def read(self, within: float) -> Reading | None:
        """Take one look using at most *within* seconds, or `None` when it could not look in that time."""
        ...

    def pause(self, seconds: float) -> None: ...


def shown(page: Any, perceivable: Mapping[str, Any]) -> bool:
    """Whether the page shows a visible element with this role and accessible name, in the states the perceivable asks for."""
    options = {key: True for key in ROLE_STATES if perceivable.get(key)}
    role, name = str(perceivable["role"]), str(perceivable["name"])
    if role in ANNOUNCED_ROLES:
        found = page.get_by_role(role, **options).filter(has_text=name)
    else:
        found = page.get_by_role(role, name=name_pattern(name), **options)
    return any(found.nth(index).is_visible() for index in range(found.count()))


class PageReading:
    """The live page, queried as each perceivable asks."""

    def __init__(self, page: Any) -> None:
        self._page = page

    def shown(self, perceivable: Mapping[str, Any]) -> bool:
        return shown(self._page, perceivable)


class PageScreen:
    """A page in a browser, always readable."""

    def __init__(self, page: Any) -> None:
        self._page = page

    def read(self, within: float) -> Reading | None:
        return PageReading(self._page)

    def pause(self, seconds: float) -> None:
        self._page.wait_for_timeout(max(1, round(seconds * 1000)))


def holds(reading: Reading, perceivable: Mapping[str, Any]) -> bool:
    """Whether the screen is as the perceivable says: shown, or, when it is `absent`, not shown."""
    return reading.shown(perceivable) != bool(perceivable.get("absent"))


def _label(perceivable: Mapping[str, Any]) -> str:
    return f"{perceivable['role']} {perceivable['name']!r}"


def settle_screen(
    screen: Screen,
    exchanges: Any,
    node: str,
    *,
    since: int,
    requests: Sequence[tuple[str, str]],
    busy: Mapping[str, Any] | None,
    states: Mapping[str, Sequence[Mapping[str, Any]]],
    expect: str,
    ceiling_s: float,
    origins: Sequence[str] = (),
    clock: Callable[[], float] = time.monotonic,
) -> Settled:
    """Wait for the requests to answer, then the busy sign to go, then a declared state to hold, all within one ceiling. With *origins*, the settle then fails on a `fetch` or `xhr` request to one of them that *requests* do not declare."""
    deadline = clock() + ceiling_s

    def tick() -> bool:
        left = deadline - clock()
        if left <= 0:
            return False
        screen.pause(max(1, min(TICK_MS, int(left * 1000))) / 1000)
        return True

    def timed_out(*pending: str) -> Settled:
        return Settled(False, f"{node}: still waiting after {ceiling_s:g}s, " + "; ".join(pending), None)

    def look() -> Reading | None:
        return screen.read(max(0.001, deadline - clock()))

    waiting = list(requests)
    while waiting:
        waiting = [pair for pair in waiting if exchanges.exchange_state(*pair, since=since) != "answered"]
        if not waiting:
            break
        if not tick():
            unsent = [f"{method} {path}" for method, path in waiting
                      if exchanges.exchange_state(method, path, since=since) == "unsent"]
            unanswered = [f"{method} {path}" for method, path in waiting
                          if exchanges.exchange_state(method, path, since=since) == "sent"]
            reasons = []
            if unsent:
                reasons.append("requests never sent: " + ", ".join(unsent))
            if unanswered:
                reasons.append("requests sent and not answered: " + ", ".join(unanswered))
            return timed_out(*reasons)
    while busy is not None:
        reading = look()
        if reading is not None and not reading.shown(busy):
            break
        if not tick():
            if reading is None:
                return timed_out("the screen could not be read while the busy sign was awaited")
            return timed_out(f"busy sign still shown: {_label(busy)}")
    while True:
        reading = look()
        held = [] if reading is None else [
            name for name, perceivables in states.items() if all(holds(reading, one) for one in perceivables)
        ]
        if held:
            break
        if not tick():
            if reading is None:
                return timed_out("the screen could not be read while a declared state was awaited")
            return timed_out("no declared state holds: " + ", ".join(states))
    if origins:
        extra = exchanges.undeclared_since(requests, origins=origins, since=since)
        if extra:
            sent = ", ".join(f"{method} {path}" for method, path in extra)
            return Settled(False, f"{node}: requests no passage or screen declares: {sent}", held[0])
    if expect in held:
        return Settled(True, f"{node}: screen shows state {expect!r}", expect)
    return Settled(False, f"{node}: expected state {expect!r}, screen shows {held[0]!r}", held[0])
