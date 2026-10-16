"""A server page's data states and the moves that carry a record between them: the one reading `ostler doctor` and the walk compiler share."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from ostler import checks as checks_mod, markdown, refs as refs_mod
from ostler.finding import Finding
from ostler.qa.compile_support import bullet_value
from ostler.qa.obligation_frame import BookNode, book_nodes

_OF = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_NONE_MOVE = re.compile(r"none,\s*because\s+\S", re.IGNORECASE)
_LINK = r"\[[^\]]+\]\([^)\s]*\)"
_FROM_TO_MOVE = re.compile(rf"{_LINK}\s+to\s+{_LINK}")
_TO_MOVE = re.compile(rf"to\s+{_LINK}")
_FIELD_ARGS = ("path", "subject")
_MOVE_FORMS = ("`- moves: [<from state>](#<anchor>) to [<to state>](#<anchor>)`, "
               "`- moves: to [<state>](#<anchor>)` or `- moves: none, because <reason>`")


@dataclass(frozen=True, slots=True)
class DataState:
    """One data state as the context packet carries it: the record it describes, the endpoint that reads that record, and the checks that tell its answer from a sibling's."""

    node: str
    of: str
    observe: str
    verify: tuple[str, ...]
    method: str
    path: str


@dataclass(frozen=True, slots=True)
class Move:
    """One `moves:` row: the state a record leaves (empty when any sibling may precede it) and the state it lands on (empty when the step moves nothing)."""

    start: str
    end: str
    index: int = 0


def _page_of(node_id: str) -> str:
    return node_id.split("#", 1)[0]


def anchor_of(node_id: str) -> str:
    """The anchor a state is named by in a failure: what follows `#` in its node id."""
    return node_id.split("#", 1)[1] if "#" in node_id else node_id


def of_of(node: BookNode) -> str:
    """The record *node*'s `of:` names, or `""` when it is not one plain word."""
    value = bullet_value(next(iter(node.bullets.get("of", ())), None)) or ""
    return value if _OF.fullmatch(value) else ""


def _read_nodes(node: BookNode, book: Mapping[str, BookNode]) -> list[BookNode]:
    return [target for target in node.targets("observe", book) if target.type in ("endpoint", "command")]


def _route(endpoint: BookNode) -> tuple[str, str]:
    method = bullet_value(next(iter(endpoint.bullets.get("method", ())), None)) or ""
    path = bullet_value(next(iter(endpoint.bullets.get("path", ())), None)) or ""
    return method.upper(), path


def data_state_of(node: BookNode, book: Mapping[str, BookNode]) -> DataState | None:
    """The data state *node* declares, or `None` while its `of:`, `observe:` or `verify:` do not name what a walk needs."""
    observed = _read_nodes(node, book)
    checks = tuple(value for value in node.bullets.get("verify", ())
                   if isinstance(checks_mod.parse_check(value), checks_mod.CheckCall))
    if not of_of(node) or len(observed) != 1 or not checks:
        return None
    method, path = _route(observed[0]) if observed[0].type == "endpoint" else ("", "")
    return DataState(node.id, of_of(node), observed[0].id, checks, method, path)


def data_states_of(book: Mapping[str, BookNode]) -> dict[str, DataState]:
    """Every well-formed data state of the book, by node id."""
    found = {node.id: data_state_of(node, book) for node in book.values() if node.type == "data-state"}
    return {node_id: state for node_id, state in found.items() if state is not None}


def siblings_of(state: DataState, states: Mapping[str, DataState]) -> list[DataState]:
    """The other states of *state*'s lifecycle that read the same endpoint, in document order."""
    page = _page_of(state.node)
    return [other for other in states.values()
            if other.node != state.node and other.of == state.of and other.observe == state.observe
            and _page_of(other.node) == page]


def moves_of(node: BookNode, book: Mapping[str, BookNode]) -> list[Move]:
    """The well-formed `moves:` rows of *node* that name a state to land on."""
    resolved = {edge.href: edge.to for edge in node.edges if edge.via == "moves" and edge.href}
    moves: list[Move] = []
    for index, value in enumerate(node.bullets.get("moves", ()), start=1):
        text = " ".join(value.split())
        links = [resolved.get(href, "") for _title, href in markdown.extract_refs(value).links]
        if _FROM_TO_MOVE.fullmatch(text) and len(links) == 2 and all(links):
            moves.append(Move(links[0], links[1], index))
        elif _TO_MOVE.fullmatch(text) and len(links) == 1 and links[0]:
            moves.append(Move("", links[0], index))
    return moves


def state_obligation_id(node_id: str) -> str:
    """The id of the obligation a data state owes: the walk that observes it covers it."""
    return f"okf:{node_id}:contract"


def move_obligation_id(node_id: str, index: int) -> str:
    """The id of the obligation one `moves:` row owes: the walk that takes the move covers it."""
    return f"okf:{node_id}:moves:{index}"


def _shape_problem(node: BookNode, key: str, message: str, fix: str, f: list[Finding]) -> None:
    f.append(Finding("error", "data-state-shape", f"{node.id}: {message}. {fix}", path=_page_of(node.id),
                     line=node.line, ref=refs_mod.bullet_ref(node.id, key), suggestion=fix))


def _moves_problem(node: BookNode, message: str, fix: str, f: list[Finding], key: str = "moves") -> None:
    f.append(Finding("error", "moves-shape", f"{node.id}: {message}. {fix}", path=_page_of(node.id),
                     line=node.line, ref=refs_mod.bullet_ref(node.id, key), suggestion=fix))


def _check_sends(node: BookNode, book: Mapping[str, BookNode], f: list[Finding]) -> None:
    for edge in node.edges:
        if edge.via != "sends" or not edge.to or edge.to not in book:
            continue
        if book[edge.to].type not in ("endpoint", "invocation"):
            _moves_problem(node, f"`sends:` links `{edge.to}`, which is no endpoint or invocation",
                           "link the endpoint or invocation of a server page that the act sends a request to", f, "sends")


def _check_when(node: BookNode, book: Mapping[str, BookNode], f: list[Finding]) -> None:
    for edge in node.edges:
        if edge.via != "when" or not edge.to or edge.to not in book:
            continue
        if book[edge.to].type != "data-state":
            _shape_problem(node, "when", f"`when:` links `{edge.to}`, which is no data state",
                           "link a state declared under `## Data states`, or delete the row", f)


def _check_state(node: BookNode, book: Mapping[str, BookNode], f: list[Finding]) -> None:
    if "of" in node.bullets and not of_of(node):
        _shape_problem(node, "of", f"`of:` is {node.bullets['of'][0]!r}, not one plain word",
                       "write `- of: <record>` with one word naming the record, such as `bill`", f)
    if node.bullets.get("observe"):
        linked = [edge for edge in node.edges if edge.via == "observe"]
        if not linked:
            _shape_problem(node, "observe", "`observe:` links nothing",
                           "write `- observe: [<title>](<page>#<endpoint or command anchor>)` naming the endpoint or command that reads the record",
                     f)
        elif all(edge.to in book for edge in linked) and len(_read_nodes(node, book)) != 1:
            _shape_problem(node, "observe", "`observe:` does not link exactly one endpoint or command",
                           "link the one endpoint or command that reads the record", f)


def _check_moves(node: BookNode, book: Mapping[str, BookNode], f: list[Finding]) -> None:
    resolved = {edge.href: edge.to for edge in node.edges if edge.via == "moves" and edge.href}
    for value in node.bullets.get("moves", ()):
        text = " ".join(value.split())
        if _NONE_MOVE.match(text):
            continue
        if not (_FROM_TO_MOVE.fullmatch(text) or _TO_MOVE.fullmatch(text)):
            _moves_problem(node, f"`moves: {text}` is none of the three spellings", f"write {_MOVE_FORMS}", f)
            continue
        targets = [resolved.get(href, "") for _title, href in markdown.extract_refs(value).links]
        if not all(target in book for target in targets):
            continue
        found = [book[target] for target in targets]
        for target in found:
            if target.type != "data-state":
                _moves_problem(node, f"`moves:` links `{target.id}`, which is no data state",
                           "link a state declared under `## Data states`", f)
        if len(found) == 2 and all(target.type == "data-state" for target in found):
            start, end = (of_of(target) for target in found)
            if start != end:
                _moves_problem(node, f"`moves:` leaves `{found[0].id}` (`of: {start}`) for `{found[1].id}` "
                           f"(`of: {end}`), and one move carries one record",
                           "link two states that share `of:`", f)


def _field(call: checks_mod.CheckCall) -> tuple[str, str]:
    return call.name, next((str(call.args[key]) for key in _FIELD_ARGS if key in call.args), "")


def _expected(call: checks_mod.CheckCall) -> dict[str, object]:
    return {key: value for key, value in call.args.items() if key not in _FIELD_ARGS}


def _calls(state: DataState) -> list[checks_mod.CheckCall]:
    parsed = [checks_mod.parse_check(value) for value in state.verify]
    return [call for call in parsed if isinstance(call, checks_mod.CheckCall)]


def told_apart(first: DataState, second: DataState) -> bool:
    """Whether some check of each state reads one field and expects different values, or the two read different endpoints."""
    if first.observe != second.observe:
        return True
    return any(_field(a) == _field(b) and _expected(a) != _expected(b)
               for a in _calls(first) for b in _calls(second))


def _check_distinct(states: Mapping[str, DataState], book: Mapping[str, BookNode], f: list[Finding]) -> None:
    lifecycles: dict[tuple[str, str], list[DataState]] = {}
    for state in states.values():
        lifecycles.setdefault((_page_of(state.node), state.of), []).append(state)
    for (_page, record), members in sorted(lifecycles.items()):
        for first, second in combinations(members, 2):
            if told_apart(first, second):
                continue
            node = book[second.node]
            fix = (f"add a `verify:` to `{anchor_of(second.node)}` that reads a field `{anchor_of(first.node)}` also "
                   f"reads and expects a different value, such as `json_path(path=\"$.status\", equals=\"...\")`")
            f.append(Finding(
                "error", "indistinct-states",
                f"{second.node}: `{anchor_of(first.node)}` and `{anchor_of(second.node)}` are states of one `{record}` "
                f"that read the same endpoint, and no check of one expects a different value than a check of the "
                f"other on the same field, so a record in one also passes the other. {fix}",
                path=_page_of(node.id), line=node.line, ref=refs_mod.bullet_ref(second.node, "verify"),
                suggestion=fix))


def check_data_states(data: dict, f: list[Finding]) -> None:
    """Each data state names a record and the endpoint that reads it, each `moves:` row links states of one record, and no two states of a record pass the same read."""
    book = book_nodes({node["id"]: node for node in data["nodes"]})
    for node in book.values():
        if node.type == "data-state":
            _check_state(node, book, f)
        elif node.type in ("endpoint", "invocation", "command") and node.bullets.get("moves"):
            _check_moves(node, book, f)
        elif node.type == "interaction" and node.bullets.get("sends"):
            _check_sends(node, book, f)
        elif node.type == "state" and node.bullets.get("when"):
            _check_when(node, book, f)
    _check_distinct(data_states_of(book), book, f)


def moves_table(book: Mapping[str, BookNode]) -> dict[str, list[Move]]:
    """Every endpoint's, invocation's and command's `moves:` rows that land on a state, by node id."""
    found = {node.id: moves_of(node, book) for node in book.values()
             if node.type in ("endpoint", "invocation", "command") and node.bullets.get("moves")}
    return {node_id: moves for node_id, moves in found.items() if moves}


def verify_texts(state: DataState) -> Sequence[str]:
    """The canonical spelling of each check *state* verifies."""
    return tuple(call.text() for call in _calls(state))
