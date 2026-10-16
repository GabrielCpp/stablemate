"""The walks that settle what no flow settled: a move a route makes, and the data states it reads."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace

from ostler.data_states import DataState
from ostler.data_states import Move
from ostler.data_states import anchor_of
from ostler.data_states import siblings_of
from ostler.data_states import state_obligation_id
from ostler.qa import references
from ostler.qa.book_index import BookIndex
from ostler.qa.compile_cli import cli_move_walk
from ostler.qa.compile_cli import cli_observe_walk
from ostler.qa.compile_http import move_walk
from ostler.qa.compile_http import observe_walk
from ostler.qa.compile_journey import JourneyWalk
from ostler.qa.compile_journey import WalkedJourney
from ostler.qa.compile_journey import api_target
from ostler.qa.compile_support import PYTHON
from ostler.qa.navigation import SurfaceNavigation
from ostler.qa.navigation import surface_row
from ostler.qa.obligation import FixtureRow
from ostler.qa.obligation import FlowStep
from ostler.qa.obligation import Obligation
from ostler.qa.plan_source import Arrangement
from ostler.qa.plan_source import EmittedScenarios
from ostler.qa.plan_source import Gap
from ostler.qa.plan_source import PlanSinks
from ostler.qa.plan_source import SourceScenario
from ostler.qa.plan_source import arrangement_of
from ostler.qa.plan_source import data_state_walk_function_name
from ostler.qa.plan_source import move_walk_function_name
from ostler.qa.plan_source import python_literal
from ostler.qa.plan_source import scenario_lines
from ostler.qa.plan_source import target_lines
from ostler.qa.plan_source import target_variable


def _start_of(move: Move, book: BookIndex, states: Mapping[str, Obligation]) -> str:
    """The state a one-move walk arranges: the one the move leaves, else the first sibling of the one it lands on that a fixture arranges, else the landing state itself."""
    if move.start:
        return move.start
    landing = book.data_states[move.end]
    return next((sibling.node for sibling in siblings_of(landing, book.data_states)
                 if state_obligation_id(sibling.node) in states and states[state_obligation_id(sibling.node)].fixtures),
                move.end)


def _named_fixtures(nodes: list[str], book: BookIndex, available: Mapping[str, FixtureRow]) -> list[FixtureRow]:
    """The fixtures the acts of *nodes* name through an `@fixture.fact` reference."""
    found: dict[str, FixtureRow] = {}
    for node in nodes:
        for row in book.acts_by_node.get(node, ()):
            for ref in references.find_references(json.dumps(row.args)):
                if isinstance(ref, references.NodeRef) and ref.node in available:
                    found[ref.node] = available[ref.node]
    return list(found.values())


def _unarranged(move: Obligation, start: DataState) -> Gap:
    return Gap(move.id, "unarranged-state", (
        f"the starting state `{anchor_of(start.node)}` of this move has no `fixture:`, so no walk can put a record "
        f"in it and the move stays uncovered. Add `- fixture:` to `{anchor_of(start.node)}` linking a fixture that "
        "arranges it, or `- fixture: none, because ...` saying why any record is already there"))


def move_walks(
    moves: list[Obligation], states: Mapping[str, Obligation], book: BookIndex,
    navigation: dict[str, SurfaceNavigation], sinks: PlanSinks, emitted: EmittedScenarios,
    available: Mapping[str, FixtureRow],
) -> list[str]:
    """A one-move walk for each owed move no compiled flow takes: arrange the starting state, read the record there, send the move's request and hold the state it lands on."""
    lines: list[str] = []
    for move_obligation in sorted(moves, key=lambda o: o.id):
        if move_obligation.id in emitted.covered:
            continue
        index = int(move_obligation.id.rpartition(":")[2])
        move = next((row for row in book.moves.get(move_obligation.node, ()) if row.index == index), None)
        if move is None or move.end not in book.data_states:
            sinks.gaps.append(Gap(move_obligation.id, "uncompilable-claim",
                                  f"the move lands on `{anchor_of(move.end) if move else 'nothing'}`, which is no "
                                  "well-formed data state, so no walk can read the record back"))
            continue
        start_id = _start_of(move, book, states)
        start = book.data_states.get(start_id)
        start_obligation = states.get(state_obligation_id(start_id))
        if start is None or start_obligation is None:
            sinks.gaps.append(Gap(move_obligation.id, "uncompilable-claim",
                                  f"the starting state `{anchor_of(start_id)}` of this move is no well-formed data "
                                  "state, so no walk can read the record in it"))
            continue
        starting = arrangement_of([start_obligation])
        if starting.unstated:
            sinks.gaps.append(_unarranged(move_obligation, start))
            continue
        named = _named_fixtures([move_obligation.node, start.observe, book.data_states[move.end].observe],
                                book, available)
        rows = list({(row.name, row.args): row for row in [*starting.rows, *named]}.values())
        carrier = replace(start_obligation, fixtures=tuple(rows), checks=())
        cli = move_obligation.on_cli_page
        node_type = "invocation" if move_obligation.node in book.invocation_claims else ("command" if cli else "endpoint")
        step = FlowStep(move_obligation.node, "", node_type, move_obligation.surface)
        walk = JourneyWalk(replace(book, moves={**book.moves, move_obligation.node: (move,)}), (step,), [carrier],
                           [move_obligation.id], surface_row(navigation, move_obligation.surface))
        if cli:
            cli_walked = cli_move_walk(step, start, walk.book, sinks.gaps, walk.ids)
            walked = None if cli_walked is None else WalkedJourney(cli_walked[0], cli_walked[1], cli_walked[1])
        else:
            walked = move_walk(walk, start, sinks, frozenset(row.name for row in starting.rows))
        if walked is None:
            continue
        emitted.covered.update(walked.covered)
        source = move_obligation.node.partition("#")[0]
        if cli:
            target_var = target_variable(move_obligation.surface, "cli")
            lines.extend(target_lines(target_var, PYTHON.name, "", emitted))
        else:
            target_var, base_url = api_target(move_obligation.surface, source, book)
            lines.extend(target_lines(target_var, PYTHON.name, f", base_url={python_literal(base_url)}", emitted))
        landing = state_obligation_id(move.end)
        scenario = SourceScenario(
            source, target_var, [move_obligation.id, state_obligation_id(start_id), landing],
            Arrangement(rows, starting.stated_none, {(row.name, row.args): [move_obligation.id] for row in rows}),
            walked.lines,
            objective=(f"Whether `{anchor_of(move_obligation.node)}` moves a record from "
                       f"`{anchor_of(start_id)}` to `{anchor_of(move.end)}`."))
        lines.extend(scenario_lines(scenario, move_walk_function_name(move_obligation, emitted)))
    return lines


def state_walks(
    states: list[Obligation], book: BookIndex, navigation: dict[str, SurfaceNavigation], sinks: PlanSinks,
    emitted: EmittedScenarios, available: Mapping[str, FixtureRow],
) -> list[str]:
    """An observe-only walk for each owed data state no walk reached whose fixture arranges a record: arrange it and hold the state's checks on the read."""
    lines: list[str] = []
    for state_obligation in sorted(states, key=lambda o: o.id):
        if state_obligation.id in emitted.covered:
            continue
        state = book.data_states.get(state_obligation.node)
        arrangement = arrangement_of([state_obligation])
        if state is None or arrangement.unstated or not arrangement.rows:
            continue
        named = _named_fixtures([state.observe], book, available)
        rows = list({(row.name, row.args): row for row in [*arrangement.rows, *named]}.values())
        carrier = replace(state_obligation, fixtures=tuple(rows), checks=())
        cli = state_obligation.on_cli_page
        if cli:
            read = cli_observe_walk(state, book, sinks.gaps, [state_obligation.id])
            walked = None if read is None else WalkedJourney(read, frozenset({state_obligation_id(state.node)}),
                                                               frozenset({state_obligation_id(state.node)}))
        else:
            walked = observe_walk([carrier], state, book, sinks, frozenset(row.name for row in arrangement.rows))
        if walked is None:
            continue
        emitted.covered.update(walked.covered)
        source = state_obligation.node.partition("#")[0]
        if cli:
            target_var = target_variable(state_obligation.surface, "cli")
            lines.extend(target_lines(target_var, PYTHON.name, "", emitted))
        else:
            target_var, base_url = api_target(state_obligation.surface, source, book)
            lines.extend(target_lines(target_var, PYTHON.name, f", base_url={python_literal(base_url)}", emitted))
        scenario = SourceScenario(
            source, target_var, [state_obligation.id],
            Arrangement(rows, arrangement.stated_none, {(row.name, row.args): [state_obligation.id] for row in rows}),
            walked.lines,
            objective=f"Whether a record arranged by its fixture reads as `{anchor_of(state.node)}`.")
        lines.extend(scenario_lines(scenario, data_state_walk_function_name(state_obligation, emitted)))
    return lines


def _unreached_advice(state: Obligation) -> str:
    anchor = anchor_of(state.node)
    if state.fixtures:
        return ""
    if state.arranges_nothing:
        return (f". `{anchor}` says `fixture: none`, so no walk can arrange it. A flow step whose `moves:` row lands "
                "on it, or a move that leaves it from a state with a `fixture:`, must reach it")
    return f". Add `- fixture:` to `{anchor}` so a walk can arrange and read it"


def unreached_state_gaps(states: list[Obligation], covered: set[str], gapped: set[str]) -> list[Gap]:
    """One gap per owed data state no compiled walk read a record in."""
    return [
        Gap(state.id, "unreached-data-state", (
            f"no compiled walk reads a record in the data state `{anchor_of(state.node)}`. A flow step whose "
            "`moves:` row lands on it observes it, and so does a one-move walk that leaves it from a state with a "
            "`fixture:`" + _unreached_advice(state)))
        for state in states if state.id not in covered and state.id not in gapped
    ]
