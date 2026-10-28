"""What a flow step that stops at a screen state waits for and checks, resolved the same way for a browser and a device."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ostler import accessible_names, passages as passages_mod
from ostler.passages import Passage
from ostler.qa.compile_journey import JourneyWalk
from ostler.qa.compile_support import MATCHABLE_ROLES
from ostler.qa.compile_support import TEMPLATE_HOLE
from ostler.qa.compile_support import bullet_value
from ostler.qa.compile_support import name_refusal
from ostler.qa.compile_support import on_node
from ostler.qa.compile_support import shown_on
from ostler.qa.book_index import BookIndex
from ostler.qa.obligation import CallRow
from ostler.qa.obligation import FlowStep
from ostler.qa.obligation import Locators
from ostler.qa.obligation import NO_LOCATORS
from ostler.qa.plan_source import Gap
from ostler.qa.plan_source import arrangement_of
from ostler.routes import route_pattern

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


def declared_pairs(entries: Sequence[str]) -> list[tuple[str, str]] | str:
    """The `(method, path)` pairs a `requests:` list declares, or why one cannot be read."""
    pairs: list[tuple[str, str]] = []
    for entry in entries:
        method, _, path = (bullet_value(entry) or "").partition(" ")
        path = path.strip()
        if not method.isalpha() or not path.startswith("/"):
            return f"`requests:` entry {entry!r} is not `METHOD /path`"
        pairs.append((method.upper(), path))
    return pairs


def request_pairs(locators: Locators) -> list[tuple[str, str]] | str:
    """The `(method, path)` pairs a screen's `requests:` declares, or why one cannot be read."""
    return declared_pairs(locators.requests)


def stop_state_ids(step: FlowStep, book: BookIndex) -> set[str]:
    """The ids of the state obligations whose node is the one *step* stops at."""
    return {state.id for state in book.states_by_screen.get(step.ref.split("#")[0], [])
            if state.node == step.ref}


@dataclass(frozen=True)
class Move:
    """One step of a walk once passages are expanded: the flow step it came from, the passage it ends, and whether it goes on from the move before."""
    index: int
    step: FlowStep
    passage: Passage | None = None
    continues: bool = False


def expand_steps(walk: JourneyWalk, gaps: list[Gap]) -> list[Move] | None:
    """The walk's steps with each passage expanded into its interactions and the stops around it, or `None` once a joint, a passage or a condition cannot be followed."""
    def refuse(reason: str) -> None:
        gaps.extend(Gap(oid, "uncompilable-claim", reason) for oid in walk.ids)

    book = walk.book
    for index, step in enumerate(walk.steps, start=1):
        if step.node_type == "passage" and not (step.ref in book.passages and book.passages[step.ref].start):
            refuse(f"step {index} links passage `{step.ref}`, which the packet does not carry well formed")
            return None
    traced = passages_mod.trace([(step.node_type, step.ref) for step in walk.steps], book.passages)
    if traced.broken:
        for _number, message in traced.broken:
            refuse(message)
        return None
    arranged = {row.name for row in arrangement_of(walk.obligations).rows}
    for stop in traced.stops:
        if stop.acted:
            continue
        for stop_state in book.states_by_screen.get(stop.state.split("#")[0], []):
            missing = sorted({row.name for row in stop_state.fixtures} - arranged)
            if stop_state.node == stop.state and missing and not stop_state.arranges_nothing:
                refuse(passages_mod.unarranged(stop.at + 1, stop.state, missing))
                return None
    moves: list[Move] = []
    for at, step in enumerate(walk.steps):
        if at in traced.repeated:
            continue
        if step.node_type != "passage":
            moves.append(Move(at + 1, step))
            continue
        passage = book.passages[step.ref]
        if at in traced.opens:
            moves.append(Move(at + 1, FlowStep(passage.start, "", "state", step.surface)))
        moves.extend(Move(at + 1, FlowStep(ref, "", "interaction", step.surface), None, number > 0)
                     for number, ref in enumerate(passage.steps))
        moves.append(Move(at + 1, FlowStep(passage.end, "", "state", step.surface), passage))
    return moves


def resolve_stop(
    index: int, step: FlowStep, walk: JourneyWalk, gaps: list[Gap], *, device: bool,
    passage: Passage | None = None, arrived: bool = True,
) -> ScreenStop | None:
    """What the step waits for and checks, or `None` once the stop cannot be compiled. A stop after *passage* waits for the passage's requests first. A stop the walk did not *arrive* at waits for none of its screen's own requests."""
    sent: list[tuple[str, str]] = []
    keep_own = arrived
    if passage is not None and not device:
        declared = declared_pairs(passage.requests)
        if isinstance(declared, str):
            gaps.extend(Gap(oid, "uncompilable-claim", f"step {index} stops at `{step.ref}`: {declared}")
                        for oid in walk.ids)
            return None
        sent = declared
        keep_own = passage.start.split("#")[0] != passage.end.split("#")[0]
    return resolve_state(step.ref, walk.book, walk.ids, gaps, device=device,
                         where=f"step {index} stops at `{step.ref}`", sent=sent, keep_own=keep_own)


def resolve_state(
    ref: str, book: BookIndex, ids: Sequence[str], gaps: list[Gap], *, device: bool, where: str,
    sent: Sequence[tuple[str, str]] = (), keep_own: bool = True,
) -> ScreenStop | None:
    """What settling on the state *ref* waits for and checks, or `None` once it cannot be compiled. *sent* are requests to wait for before the screen's own, which *keep_own* false leaves out."""
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
    return ScreenStop(ref, (*sent, *(requests if keep_own else ())), busy, states, fragment, covers, title)


def step_acts(step: FlowStep, walk: JourneyWalk) -> list[CallRow]:
    """The acts a journey replays for *step*: all of them, unless the step's claims were written for a fixture the journey does not arrange, whose visits and clicks elsewhere than the step's own screen reach the step as another user would."""
    acts = walk.book.acts_by_node.get(step.ref, [])
    claims = [*walk.book.claims_by_node.get(step.ref, []), *walk.book.setups_by_node.get(step.ref, [])]
    declared = {row.name for claim in claims for row in claim.fixtures}
    arranged = {row.name for row in arrangement_of(walk.obligations).rows}
    if not declared or declared & arranged:
        return acts
    page = step.ref.split("#")[0]
    own_route = route_pattern(walk.book.screen_routes.get(
        shown_on(page, walk.nav.routes, walk.book.fragment_hosts), ""))
    return [act for act in acts
            if (act.name != "visit" or (own_route is not None and own_route.fullmatch(
                act.text_arg("path").split("?")[0]) is not None))
            and all(target.node.split("#")[0] in ("", page) for target in act.locates.values())]
