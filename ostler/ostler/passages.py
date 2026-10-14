"""A screen's passages and the joints a flow makes of them: the one reading `ostler doctor` and the walk compiler share."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ostler import accessible_names, locators as loc_mod, markdown, refs as refs_mod
from ostler.finding import Finding
from ostler.qa import captures as captures_mod, fixture_provides, journey_steps, references
from ostler.qa.compile_support import ARRIVAL_TRIGGERS, PATH_VARIABLE, TEMPLATE_HOLE, bullet_value, trigger_name
from ostler.qa.obligation_frame import BookNode, book_nodes

_UNMATCHABLE_ROLES = frozenset({"generic", "none", "presentation"})
_RUN_STEP_TYPES = {"server": ("endpoint", "invocation"), "cli": ("command", "invocation")}


@dataclass(frozen=True, slots=True)
class Passage:
    """One passage as the context packet carries it: the state it leaves, the interactions it performs, the state it lands on and the requests it sends. A passage on a server or command-line page leaves and lands on no state and performs endpoints, commands or invocations."""

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
        if node_type == "passage" and ref in passages and passages[ref].start:
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


def _host_type(node: BookNode, book: Mapping[str, BookNode]) -> str:
    host = book.get(node.id.split("#", 1)[0])
    return host.type if host is not None else ""


def passage_of(node: BookNode, book: Mapping[str, BookNode]) -> Passage | None:
    """The passage *node* declares, or `None` while its `from:`, `to:` or `steps:` do not name what a walk needs."""
    steps = node.targets("steps", book)
    run_types = _RUN_STEP_TYPES.get(_host_type(node, book))
    if run_types is not None:
        if not steps or any(step.type not in run_types for step in steps):
            return None
        return Passage(node.id, "", tuple(step.id for step in steps), "", tuple(node.bullets.get("requests", ())))
    start, end = _states(node, "from", book), _states(node, "to", book)
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


def _check_run_steps(node: BookNode, book: Mapping[str, BookNode], f: list[Finding]) -> None:
    run_types = _RUN_STEP_TYPES[_host_type(node, book)]
    named = " or ".join(run_types)
    resolved = {edge.href: edge.to for edge in node.edges if edge.via == "steps" and edge.href}
    fix = f"list one `- [<title>](<page>#<anchor>)` per {named} the passage runs"
    items = node.bullets.get("steps", ())
    if not items:
        _shape(node, "steps", f"lists no {named}", f, fix)
    for item in items:
        links = markdown.extract_refs(item).links
        if not links:
            _shape(node, "steps", f"entry {item!r} links no {named}", f, fix)
        for _text, href in links:
            target = book.get(resolved.get(href, ""))
            if target is not None and target.type not in run_types:
                _shape(node, "steps", f"links `{target.id}`, which is no {named}", f, fix)


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


def _captured_by(node: BookNode | None) -> set[str]:
    names: set[str] = set()
    for value in node.bullets.get("capture", ()) if node is not None else ():
        parsed = captures_mod.parse_bullet(value)
        if isinstance(parsed, captures_mod.CaptureDecl):
            names.add(parsed.name)
    return names


def _route_text(node: BookNode, book: Mapping[str, BookNode]) -> str:
    for source in (node, *node.targets("on", book)):
        text = " ".join((*source.bullets.get("route", ()), *source.bullets.get("path", ())))
        if text.strip():
            return text
    return ""


def _missing_inputs(node: BookNode, book: Mapping[str, BookNode], captured: set[str], facts: set[str]) -> list[str]:
    route = _route_text(node, book)
    missing = [f"{{{name}}}" for name in PATH_VARIABLE.findall(route)
               if name not in captured and not any(fact.rpartition(".")[2] == name for fact in facts)]
    for ref in references.find_references(" ".join((route, *node.bullets.get("arrange", ())))):
        if isinstance(ref, references.NodeRef):
            if f"{ref.node}.{ref.key}" not in facts:
                missing.append(f"@{ref.node}.{ref.key}")
        elif ref.name not in captured:
            missing.append(f"${ref.name}")
    return list(dict.fromkeys(missing))


def _check_inputs(
    flow: BookNode, book: Mapping[str, BookNode], passages: Mapping[str, Passage],
    provided: Mapping[str, Sequence[str]], f: list[Finding],
) -> None:
    facts = {fact for edge in flow.edges if edge.via == "fixture" and edge.to
             for fact in provided.get(_fixture_name(edge.to), ())}
    held: set[str] = set()
    for number, step in enumerate(journey_steps.journey_steps(flow, book), start=1):
        node = book.get(step.ref)
        passage = passages.get(step.ref) if step.node_type == "passage" and node is not None else None
        if passage is None or node is None or _host_type(node, book) != "server":
            held |= _captured_by(node) if step.node_type in ("endpoint", "invocation") else set()
            continue
        for ref in passage.steps:
            inner = book[ref]
            missing = _missing_inputs(inner, book, held, facts)
            if missing:
                named = ", ".join(f"`{value}`" for value in missing)
                f.append(Finding(
                    "error", "broken-joint",
                    f"{flow.id}: step {number} links passage `{step.ref}`, whose step `{ref}` sends {named}, and "
                    f"the walk holds no such value there: no earlier step captures it and no fixture the flow "
                    f"names provides it. Take the passage after a step that captures it, or add a `- fixture:` "
                    f"that provides it to the flow",
                    ref=refs_mod.bullet_ref(flow.id, "steps"), path=flow.id.split("#", 1)[0], line=flow.line))
            held |= _captured_by(inner)


def _check_flow(
    flow: BookNode, book: Mapping[str, BookNode], passages: Mapping[str, Passage],
    provided: Mapping[str, Sequence[str]], f: list[Finding],
) -> None:
    _check_inputs(flow, book, passages, provided, f)
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


def _hosting_screen(step: journey_steps.JourneyStep, book: Mapping[str, BookNode]) -> str:
    if step.node_type != "interaction":
        return ""
    page = step.ref.split("#", 1)[0]
    host = book.get(page)
    return page if host is not None and host.type == "screen" else ""


def _trigger_of(step: journey_steps.JourneyStep, book: Mapping[str, BookNode]) -> str:
    node = book.get(step.ref)
    return trigger_name(next(iter(node.bullets.get("trigger", ())), "")) if node is not None else ""


def _check_settled(flow: BookNode, book: Mapping[str, BookNode], f: list[Finding]) -> None:
    steps = journey_steps.journey_steps(flow, book)
    acts = [at for at, step in enumerate(steps) if _hosting_screen(step, book)]
    if not acts:
        return
    path = flow.id.split("#", 1)[0]
    ref = refs_mod.bullet_ref(flow.id, "steps")

    def report(message: str) -> None:
        f.append(Finding("error", "unsettled-act", f"{flow.id}: {message}", ref=ref, path=path, line=flow.line))

    for at in acts:
        step = steps[at]
        if _trigger_of(step, book) == "fill":
            continue
        following = steps[at + 1].node_type if at + 1 < len(steps) else ""
        if following not in ("state", "passage"):
            screen = _hosting_screen(step, book)
            report(f"Step `{step.ref}` acts on `{screen}` and no stop follows it. Add the next step as a link to "
                   f"the state that screen settles in after it, such as `- [Loaded](<relative link to screen>#loaded)`, "
                   f"or link a passage instead of the act. Declare the state under `## Screen states` on that "
                   f"screen if it is missing.")
    first = acts[0]
    if _trigger_of(steps[first], book) not in ARRIVAL_TRIGGERS and not any(
            step.node_type in ("state", "passage") for step in steps[:first]):
        screen = _hosting_screen(steps[first], book)
        report(f"the walk acts on `{screen}` at step `{steps[first].ref}` before it stopped there. Add a first step "
               f"linking the state the screen is in when the flow starts, such as "
               f"`- [Loaded](<relative link to screen>#loaded)`, and arrange its fixture on the flow's `fixture:` "
               f"when it has one.")


def _check_stateful(book: Mapping[str, BookNode], f: list[Finding]) -> None:
    stated = {node.id.split("#", 1)[0] for node in book.values() if node.type == "state"}
    for node in book.values():
        if node.type == "screen" and node.id not in stated:
            f.append(Finding(
                "error", "stateless-screen",
                f"{node.id} declares no screen state. Under `## Screen states`, add one `### <State>` per look "
                f"the screen settles in (loaded, and empty, error or disabled where the screen has them), each "
                f"with `shows:` listing the components a person sees in it. A walk stops at these states to "
                f"check the screen between acts.",
                path=node.id.split("#", 1)[0], line=node.line, ref=node.id,
                suggestion="add `## Screen states` holding `### Loaded` with `- shows:` linking its components"))


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
    provided = fixture_provides.index(book)
    for node in book.values():
        if node.type == "passage":
            if _host_type(node, book) in _RUN_STEP_TYPES:
                _check_run_steps(node, book, f)
            else:
                _check_ends(node, book, f)
                _check_steps(node, book, f)
            _check_requests(node, f)
        elif node.type == "flow":
            _check_flow(node, book, passages, provided, f)
            _check_settled(node, book, f)
    _check_stateful(book, f)
    _check_perceivable(book, f)
