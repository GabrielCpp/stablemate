"""What a flow step that stops at a screen state waits for and checks, resolved the same way for a browser and a device."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ostler import accessible_names
from ostler.qa.compile_journey import JourneyWalk
from ostler.qa.compile_support import MATCHABLE_ROLES
from ostler.qa.compile_support import TEMPLATE_HOLE
from ostler.qa.compile_support import bullet_value
from ostler.qa.compile_support import name_refusal
from ostler.qa.compile_support import on_node
from ostler.qa.book_index import BookIndex
from ostler.qa.obligation import FlowStep
from ostler.qa.obligation import Locators
from ostler.qa.obligation import NO_LOCATORS
from ostler.qa.plan_source import Gap

_STATE_MODIFIERS = frozenset({"absent", "disabled", "checked", "expanded", "selected"})

_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")


@dataclass(frozen=True)
class ScreenStop:
    """What a stop waits for and checks: the screen's requests, busy sign and states, and the state the step names."""
    node: str
    requests: tuple[tuple[str, str], ...]
    busy: dict[str, object] | None
    states: dict[str, list[dict[str, object]]]
    expect: str
    covers: tuple[str, ...]
    title: str


def perceivable(entry: str, page: str, book: BookIndex) -> dict[str, object] | str:
    """The role, accessible name and state modifiers one `shows:` or `busy:` entry addresses, or why it addresses nothing."""
    node = on_node(page, entry)
    if not node:
        return f"{entry!r} links no component"
    locators = book.locators_by_node.get(node, NO_LOCATORS)
    role = bullet_value(next(iter(locators.role), None))
    raw_name = next(iter(locators.name), None)
    name = bullet_value(raw_name)
    if not role or not name or not raw_name or MATCHABLE_ROLES is None or role not in MATCHABLE_ROLES:
        return f"`{node}` is found by no role and accessible name{name_refusal(locators)}"
    literal = accessible_names.literal_name(name)
    if accessible_names.prose_mark(raw_name) or TEMPLATE_HOLE.search(literal):
        return f"`{node}` is found by no role and accessible name{name_refusal(locators)}"
    modifiers = _MARKDOWN_LINK.sub("", entry).split()
    unknown = [word for word in modifiers if word not in _STATE_MODIFIERS]
    if unknown:
        return f"{entry!r} carries {', '.join(unknown)}, which is no state modifier"
    return {"role": role, "name": literal, **dict.fromkeys(modifiers, True)}


def request_pairs(locators: Locators) -> list[tuple[str, str]] | str:
    """The `(method, path)` pairs a screen's `requests:` declares, or why one cannot be read."""
    pairs: list[tuple[str, str]] = []
    for entry in locators.requests:
        method, _, path = (bullet_value(entry) or "").partition(" ")
        path = path.strip()
        if not method.isalpha() or not path.startswith("/"):
            return f"`requests:` entry {entry!r} is not `METHOD /path`"
        pairs.append((method.upper(), path))
    return pairs


def stop_state_ids(step: FlowStep, book: BookIndex) -> set[str]:
    """The ids of the state obligations whose node is the one *step* stops at."""
    return {state.id for state in book.states_by_screen.get(step.ref.split("#")[0], [])
            if state.node == step.ref}


def resolve_stop(
    index: int, step: FlowStep, walk: JourneyWalk, gaps: list[Gap], *, device: bool,
) -> ScreenStop | None:
    """What the step waits for and checks, or `None` once the stop cannot be compiled."""
    return resolve_state(step.ref, walk.book, walk.ids, gaps, device=device,
                         where=f"step {index} stops at `{step.ref}`")


def resolve_state(
    ref: str, book: BookIndex, ids: Sequence[str], gaps: list[Gap], *, device: bool, where: str,
) -> ScreenStop | None:
    """What settling on the state *ref* waits for and checks, or `None` once it cannot be compiled."""
    page, _, fragment = ref.partition("#")

    def refuse(reason: str) -> None:
        gaps.extend(Gap(oid, "uncompilable-claim", f"{where}: {reason}") for oid in ids)

    def unreadable(entry: str, found: dict[str, object]) -> bool:
        if device and found.get("expanded"):
            refuse(f"`{on_node(page, entry)}` is checked for `expanded`, which a device's view hierarchy does not report")
            return True
        return False

    if page not in book.locators_by_node:
        refuse(f"the packet carries no obligation for its screen `{page}`, so the requests it waits for are unknown")
        return None
    screen = book.locators_by_node[page]
    requests = request_pairs(screen)
    if isinstance(requests, str):
        refuse(requests)
        return None
    busy: dict[str, object] | None = None
    if screen.busy:
        sign = perceivable(screen.busy[0], page, book)
        if isinstance(sign, str):
            refuse(sign)
            return None
        if unreadable(screen.busy[0], sign):
            return None
        busy = sign
    siblings = book.states_by_screen.get(page, [])
    states: dict[str, list[dict[str, object]]] = {}
    for state in siblings:
        perceivables: list[dict[str, object]] = []
        for entry in state.locators.shows:
            found = perceivable(entry, page, book)
            if isinstance(found, str):
                refuse(found)
                return None
            if unreadable(entry, found):
                return None
            perceivables.append(found)
        if not perceivables:
            refuse(f"state `{state.node}` shows nothing, so no screen could be told from it")
            return None
        states[state.node.split("#", 1)[1]] = perceivables
    covers = tuple(state.id for state in siblings if state.node == ref)
    if fragment not in states or not covers:
        refuse("the packet carries no obligation for this state")
        return None
    title = next(state.requirement for state in siblings if state.node == ref).partition(": ")[0]
    return ScreenStop(ref, tuple(requests), busy, states, fragment, covers, title)
