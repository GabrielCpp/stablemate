"""The data state each record of a flow is in at each step, and the conditions a flow's cases need: the one reading `ostler doctor` and the screen conditions share."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ostler import data_states, refs as refs_mod
from ostler.finding import Finding
from ostler.passages import Passage, passages_of
from ostler.qa import fixture_provides, journey_steps
from ostler.qa.compile_support import PATH_VARIABLE, bullet_value
from ostler.qa.obligation_frame import BookNode, book_nodes

Ledger = dict[tuple[str, str], str]


@dataclass(frozen=True, slots=True)
class LedgerStep:
    """One request a flow sends: its number among the flow's steps, the node that sends it, the record it acts on and the ledger before it."""

    number: int
    ref: str
    key: str
    held: Mapping[tuple[str, str], str]


def _stem(target: str) -> str:
    return target.split("#", 1)[0].rsplit("/", 1)[-1].removesuffix(".md")


def _own_path(node: BookNode) -> str:
    return " ".join(bullet_value(value) or "" for value in (*node.bullets.get("route", ()), *node.bullets.get("path", ())))


def record_key(node: BookNode, book: Mapping[str, BookNode]) -> str:
    """The path variable of *node*'s route that addresses its record, or `""` for the caller's own record."""
    text = _own_path(node)
    if not text.strip():
        text = next((path for target in node.targets("on", book) if (path := _own_path(target)).strip()), "")
    match = PATH_VARIABLE.search(text)
    return match.group(1) if match else ""


def initial_ledger(flow: BookNode, book: Mapping[str, BookNode]) -> Ledger:
    """The states the flow's `fixture:` rows arrange before its first step."""
    arranged = {_stem(edge.to) for edge in flow.edges if edge.via == "fixture" and edge.to}
    provided = fixture_provides.closure(book)
    held: Ledger = {}
    for state in data_states.data_states_of(book).values():
        for edge in book[state.node].edges:
            if edge.via != "fixture" or not edge.to or _stem(edge.to) not in arranged:
                continue
            facts = sorted(fact.rpartition(".")[2] for fact, _undetermined in provided.get(_stem(edge.to), ()))
            for key in facts or [""]:
                held[(state.of, key)] = state.node
    return held


@dataclass(frozen=True, slots=True)
class LedgerStop:
    """One stop a flow makes: its number among the flow's steps, the screen state it stops at and the ledger before it."""

    number: int
    ref: str
    held: Mapping[tuple[str, str], str]


def _requests(ref: str, book: Mapping[str, BookNode], passages: Mapping[str, Passage]) -> list[str]:
    passage = passages.get(ref)
    if passage is None:
        return [ref]
    return list(passage.steps) if not passage.start else []


def _set(held: Ledger, record: str, key: str, state: str) -> None:
    held.pop((record, key), None)
    held[(record, key)] = state


def _apply(node: BookNode, key: str, book: Mapping[str, BookNode], held: Ledger) -> None:
    for move in data_states.moves_of(node, book):
        if move.end in book:
            _set(held, data_states.of_of(book[move.end]), key, move.end)


def _send(interaction: BookNode, book: Mapping[str, BookNode], held: Ledger) -> None:
    for sent in interaction.targets("sends", book):
        if sent.type in ("endpoint", "invocation", "command"):
            _apply(sent, record_key(sent, book), book, held)


def _walk(flow: BookNode, book: Mapping[str, BookNode]) -> list[LedgerStep | LedgerStop]:
    passages = passages_of(book)
    held = initial_ledger(flow, book)
    found: list[LedgerStep | LedgerStop] = []
    for number, step in enumerate(journey_steps.journey_steps(flow, book), start=1):
        if step.node_type == "interaction" and step.ref in book:
            _send(book[step.ref], book, held)
        elif step.node_type == "state":
            found.append(LedgerStop(number, step.ref, dict(held)))
        elif step.node_type == "passage" and (passage := passages.get(step.ref)) is not None and passage.start:
            for ref in passage.steps:
                if ref in book and book[ref].type == "interaction":
                    _send(book[ref], book, held)
            found.append(LedgerStop(number, passage.end, dict(held)))
        elif step.node_type in ("endpoint", "invocation", "passage", "command"):
            for ref in _requests(step.ref, book, passages):
                node = book.get(ref)
                if node is None or node.type not in ("endpoint", "invocation", "command"):
                    continue
                key = record_key(node, book)
                found.append(LedgerStep(number, ref, key, dict(held)))
                _apply(node, key, book, held)
    return found


def ledger_steps(flow: BookNode, book: Mapping[str, BookNode]) -> list[LedgerStep]:
    """The requests of *flow* in order, passages expanded, each with the ledger as it stands before the request."""
    return [step for step in _walk(flow, book) if isinstance(step, LedgerStep)]


def ledger_stops(flow: BookNode, book: Mapping[str, BookNode]) -> list[LedgerStop]:
    """The stops of *flow* in order, each with the ledger as it stands when the walk reaches it."""
    return [step for step in _walk(flow, book) if isinstance(step, LedgerStop)]


def _holds(held: Mapping[tuple[str, str], str], record: str, key: str) -> str:
    state = held.get((record, key), "")
    return f"`{data_states.anchor_of(state)}`" if state else f"no state of the {record}"


def _touched(held: Mapping[tuple[str, str], str], record: str) -> str:
    return next((key for held_record, key in reversed(list(held)) if held_record == record), "")


def _arranging(state: BookNode) -> str:
    names = sorted({_stem(edge.to) for edge in state.edges if edge.via == "fixture" and edge.to})
    if names:
        return "add `- fixture:` linking " + " or ".join(f"`{name}`" for name in names) + " to the flow, or take"
    return "add a `fixture:` to the state and link it from the flow, or take"


def _finding(flow: BookNode, message: str, fix: str) -> Finding:
    return Finding("error", "unheld-condition", f"{flow.id}: {message}. {fix}", path=flow.id.split("#", 1)[0],
                   line=flow.line, ref=refs_mod.bullet_ref(flow.id, "steps"), suggestion=fix)


def _check_flow(flow: BookNode, book: Mapping[str, BookNode], f: list[Finding]) -> None:
    for step in ledger_steps(flow, book):
        node = book[step.ref]
        for state in node.targets("when", book):
            if state.type != "data-state":
                continue
            record = data_states.of_of(state)
            if step.held.get((record, step.key)) == state.id:
                continue
            seen = _holds(step.held, record, step.key)
            fix = f"{_arranging(state)} an earlier step that moves the {record} to `{data_states.anchor_of(state.id)}`"
            f.append(_finding(
                flow, f"step {step.number} links the case `{data_states.anchor_of(step.ref)}`, which applies only "
                f"while the {record} is `{data_states.anchor_of(state.id)}`, and the walk holds {seen} there", fix))
        for move in data_states.moves_of(node, book):
            if not move.start or move.start not in book:
                continue
            record = data_states.of_of(book[move.start])
            current = step.held.get((record, step.key), "")
            if current and current != move.start:
                fix = (f"{_arranging(book[move.start])} an earlier step that moves the {record} to "
                       f"`{data_states.anchor_of(move.start)}`")
                f.append(_finding(
                    flow, f"step {step.number} takes `{data_states.anchor_of(step.ref)}`, which moves the {record} "
                    f"from `{data_states.anchor_of(move.start)}`, and the walk holds {_holds(step.held, record, step.key)} "
                    f"there", fix))


def _check_stops(flow: BookNode, book: Mapping[str, BookNode], f: list[Finding]) -> None:
    for stop in ledger_stops(flow, book):
        node = book.get(stop.ref)
        if node is None or node.type != "state":
            continue
        for state in node.targets("when", book):
            if state.type != "data-state":
                continue
            record = data_states.of_of(state)
            key = _touched(stop.held, record)
            if stop.held.get((record, key)) == state.id:
                continue
            seen = _holds(stop.held, record, key)
            fix = f"{_arranging(state)} an earlier step that moves the {record} to `{data_states.anchor_of(state.id)}`"
            f.append(_finding(
                flow, f"step {stop.number} stops at `{data_states.anchor_of(stop.ref)}`, which the screen settles in "
                f"only while the {record} is `{data_states.anchor_of(state.id)}`, and the walk holds {seen} there", fix))


def check_conditions(data: dict, f: list[Finding]) -> None:
    """Each case that applies only while a record is in a data state is taken while the flow holds the record in it, and each move leaves the state the flow holds."""
    book = book_nodes({node["id"]: node for node in data["nodes"]})
    for node in book.values():
        if node.type == "flow":
            _check_flow(node, book, f)
            _check_stops(node, book, f)
