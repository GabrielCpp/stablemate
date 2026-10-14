"""A screen settling: the requests it sends answer, its busy sign goes, and one declared state holds."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

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


def shown(page: Any, perceivable: Mapping[str, Any]) -> bool:
    """Whether the page shows a visible element with this role and accessible name, in the states the perceivable asks for."""
    options = {key: True for key in ROLE_STATES if perceivable.get(key)}
    role, name = str(perceivable["role"]), str(perceivable["name"])
    if role in ANNOUNCED_ROLES:
        found = page.get_by_role(role, **options).filter(has_text=name)
    else:
        found = page.get_by_role(role, name=name_pattern(name), **options)
    return any(found.nth(index).is_visible() for index in range(found.count()))


def holds(page: Any, perceivable: Mapping[str, Any]) -> bool:
    """Whether the page is as the perceivable says: shown, or, when it is `absent`, not shown."""
    return shown(page, perceivable) != bool(perceivable.get("absent"))


def _label(perceivable: Mapping[str, Any]) -> str:
    return f"{perceivable['role']} {perceivable['name']!r}"


def settle_screen(
    browser: Any,
    page: Any,
    node: str,
    *,
    since: int,
    requests: Sequence[tuple[str, str]],
    busy: Mapping[str, Any] | None,
    states: Mapping[str, Sequence[Mapping[str, Any]]],
    expect: str,
    ceiling_s: float,
    clock: Callable[[], float] = time.monotonic,
) -> Settled:
    """Wait for the requests to answer, then the busy sign to go, then a declared state to hold, all within one ceiling."""
    deadline = clock() + ceiling_s

    def tick() -> bool:
        left = deadline - clock()
        if left <= 0:
            return False
        page.wait_for_timeout(max(1, min(TICK_MS, int(left * 1000))))
        return True

    def timed_out(*pending: str) -> Settled:
        return Settled(False, f"{node}: still waiting after {ceiling_s:g}s, " + "; ".join(pending), None)

    waiting = list(requests)
    while True:
        waiting = [pair for pair in waiting if browser.exchange_state(*pair, since=since) != "answered"]
        if not waiting:
            break
        if not tick():
            unsent = [f"{method} {path}" for method, path in waiting
                      if browser.exchange_state(method, path, since=since) == "unsent"]
            unanswered = [f"{method} {path}" for method, path in waiting
                          if browser.exchange_state(method, path, since=since) == "sent"]
            reasons = []
            if unsent:
                reasons.append("requests never sent: " + ", ".join(unsent))
            if unanswered:
                reasons.append("requests sent and not answered: " + ", ".join(unanswered))
            return timed_out(*reasons)
    while busy is not None and shown(page, busy):
        if not tick():
            return timed_out(f"busy sign still shown: {_label(busy)}")
    while True:
        held = [name for name, perceivables in states.items() if all(holds(page, one) for one in perceivables)]
        if held:
            break
        if not tick():
            return timed_out("no declared state holds: " + ", ".join(states))
    if expect in held:
        return Settled(True, f"{node}: screen shows state {expect!r}", expect)
    return Settled(False, f"{node}: expected state {expect!r}, screen shows {held[0]!r}", held[0])
