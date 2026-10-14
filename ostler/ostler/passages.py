"""A screen's passages and the joints a flow makes of them: the one reading `ostler doctor` and the walk compiler share."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ostler import accessible_names, locators as loc_mod, markdown, refs as refs_mod
from ostler.finding import Finding
from ostler.qa import journey_steps
from ostler.qa.compile_support import TEMPLATE_HOLE, bullet_value
from ostler.qa.obligation_frame import BookNode, book_nodes

_UNMATCHABLE_ROLES = frozenset({"generic", "none", "presentation"})


@dataclass(frozen=True, slots=True)
class Passage:
    """One passage as the context packet carries it: the state it leaves, the interactions it performs, the state it lands on and the requests it sends."""

    node: str
    start: str
    steps: tuple[str, ...]
    end: str
    requests: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Stop:
    """A state a walk stops at: the step it belongs to, and whether a step of the flow before it put the walk there."""

    state: str
    at: int
    acted: bool


@dataclass(frozen=True, slots=True)
class Trace:
    """What a flow's steps make of its passages: the stops, the stop a passage opens with, the stops already made, and the joints that do not meet."""

    stops: tuple[Stop, ...]
    opens: Mapping[int, str]
    repeated: frozenset[int]
    broken: tuple[tuple[int, str], ...]


def trace(steps: Sequence[tuple[str, str]], passages: Mapping[str, Passage]) -> Trace:
    """The stops a walk makes over *steps*, given as `(node type, node id)` pairs, and the joints that do not meet."""
    stops: list[Stop] = []
    opens: dict[int, str] = {}
    repeated: set[int] = set()
    broken: list[tuple[int, str]] = []
    current = ""
    landed = ""
    acted = False
    for at, (node_type, ref) in enumerate(steps):
        number = at + 1
        previous, landed = landed, ""
        if node_type == "state":
            if previous and ref != passages[previous].end:
                broken.append((number, joint_after(number, ref, previous, passages[previous].end)))
            elif previous:
                repeated.add(at)
            else:
                stops.append(Stop(ref, at, acted))
            current = ref
            continue
        if node_type == "passage" and ref in passages:
            passage = passages[ref]
            if current and current != passage.start:
                broken.append((number, joint_before(number, ref, passage.start, current)))
            elif not current:
                opens[at] = passage.start
                stops.append(Stop(passage.start, at, acted))
            stops.append(Stop(passage.end, at, True))
            current, landed = passage.end, ref
        elif node_type in ("interaction", "passage"):
            current = ""
        acted = True
    return Trace(tuple(stops), opens, frozenset(repeated), tuple(broken))


def joint_before(number: int, passage: str, start: str, current: str) -> str:
    """Why a passage does not join the state the walk is at."""
    return (f"step {number} links passage `{passage}`, which leaves `{start}`, but the walk is at "
            f"`{current}` there. Change the step to a passage that leaves `{current}`")


def joint_after(number: int, state: str, passage: str, end: str) -> str:
    """Why a stop does not meet the state the passage before it lands on."""
    return (f"step {number} stops at `{state}`, but the passage `{passage}` before it lands on "
            f"`{end}`. Change the stop to `{end}`")


def unarranged(number: int, state: str, missing: Sequence[str]) -> str:
    """Why a stop's condition is not one the flow arranges."""
    named = ", ".join(f"`{name}`" for name in missing)
    return (f"step {number} stops at `{state}`, which needs the fixture {named}, and the flow does not "
            f"arrange it. Add `- fixture:` linking {named} to the flow")


def _links(values: Sequence[str]) -> int:
    return sum(len(markdown.extract_refs(value).links) for value in values)


def _states(node: BookNode, key: str, book: Mapping[str, BookNode]) -> list[BookNode]:
    page = node.id.split("#", 1)[0]
    return [target for target in node.targets(key, book)
            if target.type == "state" and (key == "to" or target.id.split("#", 1)[0] == page)]


def passage_of(node: BookNode, book: Mapping[str, BookNode]) -> Passage | None:
    """The passage *node* declares, or `None` while its `from:`, `to:` or `steps:` do not name what a walk needs."""
    start, end = _states(node, "from", book), _states(node, "to", book)
    steps = node.targets("steps", book)
    if len(start) != 1 or len(end) != 1 or not steps or any(step.type != "interaction" for step in steps):
        return None
    return Passage(node.id, start[0].id, tuple(step.id for step in steps), end[0].id,
                   tuple(node.bullets.get("requests", ())))


def passages_of(book: Mapping[str, BookNode]) -> dict[str, Passage]:
    """Every well-formed passage of the book, by node id."""
    found = {node.id: passage_of(node, book) for node in book.values() if node.type == "passage"}
    return {node_id: passage for node_id, passage in found.items() if passage is not None}


def _shape(node: BookNode, key: str, problem: str, f: list[Finding], fix: str) -> None:
    f.append(Finding("error", "passage-shape", f"{node.id}: `{key}:` {problem}. {fix}",
                     path=node.id.split("#", 1)[0], line=node.line,
                     ref=refs_mod.bullet_ref(node.id, key), suggestion=fix))


def _check_ends(node: BookNode, book: Mapping[str, BookNode], f: list[Finding]) -> None:
    for key, where in (("from", "on this screen"), ("to", "")):
        values = node.bullets.get(key, ())
        linked = [edge for edge in node.edges if edge.via == key]
        fix = f"write `- {key}: [<title>](<screen page>#<state anchor>)` naming a state{' ' + where if where else ''}"
        if not _links(values):
            _shape(node, key, "links nothing", f, fix)
        elif any(not edge.to or edge.to not in book for edge in linked):
            continue
        else:
            found = _states(node, key, book)
            if len(found) != 1:
                named = "no state" + (f" {where}" if where else "") if not found else f"{len(found)} states"
                _shape(node, key, f"links {named}", f, fix)


def _check_steps(node: BookNode, book: Mapping[str, BookNode], f: list[Finding]) -> None:
    page = node.id.split("#", 1)[0]
    resolved = {edge.href: edge.to for edge in node.edges if edge.via == "steps" and edge.href}
    fix = "list one `- [<title>](#<interaction anchor>)` per interaction this screen declares"
    items = node.bullets.get("steps", ())
    if not items:
        _shape(node, "steps", "lists no interaction", f, fix)
    for item in items:
        links = markdown.extract_refs(item).links
        if not links:
            _shape(node, "steps", f"entry {item!r} links no interaction", f, fix)
        for _text, href in links:
            target = book.get(resolved.get(href, ""))
            if target is None:
                continue
            if target.type != "interaction" or target.id.split("#", 1)[0] != page:
                _shape(node, "steps", f"links `{target.id}`, which is no interaction on this screen", f, fix)


def _check_requests(node: BookNode, f: list[Finding]) -> None:
    for entry in node.bullets.get("requests", ()):
        method, _, path = (bullet_value(entry) or "").partition(" ")
        if not method.isalpha() or not path.strip().startswith("/"):
            _shape(node, "requests", f"entry {entry!r} is not `METHOD /path`", f,
                   "write `- GET /api/<path>` for each request the passage sends")


def _flow_fixtures(node: BookNode) -> set[str]:
    return {edge.to for edge in node.edges if edge.via == "fixture" and edge.to}


def _arranges_nothing(node: BookNode) -> bool:
    return any((bullet_value(value) or "").lower().startswith("none") for value in node.bullets.get("fixture", ()))


def _check_flow(flow: BookNode, book: Mapping[str, BookNode], passages: Mapping[str, Passage], f: list[Finding]) -> None:
    steps = [(step.node_type, step.ref) for step in journey_steps.journey_steps(flow, book)]
    walked = trace(steps, passages)
    path = flow.id.split("#", 1)[0]
    for _number, message in walked.broken:
        f.append(Finding("error", "broken-joint", f"{flow.id}: {message}", ref=refs_mod.bullet_ref(flow.id, "steps"),
                         path=path, line=flow.line))
    own = _flow_fixtures(flow)
    for stop in walked.stops:
        state = book.get(stop.state)
        if stop.acted or state is None or _arranges_nothing(state):
            continue
        missing = sorted({_fixture_name(edge.to) for edge in state.edges if edge.via == "fixture" and edge.to
                          and edge.to not in own})
        if missing:
            f.append(Finding("error", "unarranged-stop", f"{flow.id}: {unarranged(stop.at + 1, stop.state, missing)}",
                             ref=refs_mod.bullet_ref(flow.id, "steps"),
                         path=path, line=flow.line))


def _fixture_name(target: str) -> str:
    """The fixture's name: the stem of the page it lives in."""
    return target.split("#", 1)[0].rsplit("/", 1)[-1].removesuffix(".md")


def _unperceivable(component: BookNode) -> str:
    locator = loc_mod.locator_for(component)
    if locator.strategy == "scheme" or locator.strategy == "css":
        return f"it is found by `selector: {_selector(component)}`"
    if locator.strategy != "role" or locator.role in _UNMATCHABLE_ROLES:
        return "it declares no `role:`"
    if not locator.name:
        return "it declares no `name:`"
    raw = component.bullets.get("name", ("",))[0]
    if accessible_names.prose_mark(raw):
        return f"its `name:` describes the label with {accessible_names.prose_mark(raw)} instead of stating it"
    if TEMPLATE_HOLE.search(accessible_names.literal_name(locator.name)):
        return "its `name:` holds a template hole, so no one label names it"
    return ""


def _selector(component: BookNode) -> str:
    return bullet_value(next(iter(component.bullets.get("selector", ())), None)) or ""


def _perceived(book: Mapping[str, BookNode]) -> dict[str, list[str]]:
    users: dict[str, list[str]] = {}
    for node in book.values():
        if node.type == "state":
            owners = [(node, "shows", f"state `{node.id}` shows it")]
        elif node.type == "screen":
            owners = [(node, "busy", f"screen `{node.id}` shows it as its busy sign")]
        elif node.type == "passage":
            owners = [(step, "on", f"passage `{node.id}` acts on it") for step in node.targets("steps", book)]
        else:
            continue
        for owner, key, used in owners:
            for component in owner.targets(key, book):
                if component.type == "component":
                    users.setdefault(component.id, []).append(used)
    return users


def _check_perceivable(book: Mapping[str, BookNode], f: list[Finding]) -> None:
    for component_id, used in sorted(_perceived(book).items()):
        component = book[component_id]
        why = _unperceivable(component)
        if not why:
            continue
        f.append(Finding(
            "error", "unperceivable-element",
            f"{component_id}: {used[0]}, and {why}. A walk finds an element by its role and its "
            f"label as a person perceives it, and a style selector or a test id is not that. An "
            f"element with no label is an accessibility finding on the app. Declare `- role:` and a "
            f"literal `- name:` on the component, the label the page shows",
            path=component_id.split("#", 1)[0], line=component.line, ref=component_id,
            suggestion="- role: <the element's ARIA role>\n- name: <the label the page shows>"))


def check_passages(data: dict, f: list[Finding]) -> None:
    """Each passage names the states and interactions of its screen, each flow's passages join, each stop's condition is arranged, and every element a walk acts on or looks for is one a person perceives."""
    book = book_nodes({node["id"]: node for node in data["nodes"]})
    passages = passages_of(book)
    for node in book.values():
        if node.type == "passage":
            _check_ends(node, book, f)
            _check_steps(node, book, f)
            _check_requests(node, f)
        elif node.type == "flow":
            _check_flow(node, book, passages, f)
    _check_perceivable(book, f)
