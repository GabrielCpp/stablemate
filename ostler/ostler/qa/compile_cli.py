"""The CLI builders: a `command` node's claims and a journey of `run:`s, as `qa.tool(...)` calls."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from ostler import registry
from ostler.checks import CHECK_BY_NAME
from ostler.checks import CHECKS
from ostler.checks import CheckCall
from ostler.checks import parse_check
from ostler.data_states import DataState
from ostler.data_states import anchor_of
from ostler.data_states import move_obligation_id
from ostler.data_states import siblings_of
from ostler.data_states import state_obligation_id
from ostler.qa.book_index import BookIndex
from ostler.qa.compile_observe import observation_lines, within_off_observation
from ostler.qa.compile_support import expand_passages
from ostler.qa.compile_support import resolved_literal
from ostler.qa.obligation import CallRow
from ostler.qa.obligation import FlowStep
from ostler.qa.obligation import Obligation
from ostler.qa.plan_source import Gap
from ostler.qa.plan_source import ScenarioRefusal
from ostler.qa.plan_source import call_kwargs
from ostler.qa.plan_source import check_observes
from ostler.qa.plan_source import decline_captures
from ostler.qa.plan_source import python_literal
from ostler.qa.plan_source import operand_for
from ostler.qa.plan_source import out_of_band


@dataclass(frozen=True)
class StepRefusal:
    """Why a journey step names no `run:` this compiler can perform."""
    reason: str


def compares_the_tree(check: str | None) -> bool:
    """A check that compares the scenario's working directory before and after the tool ran."""
    return check_observes(check) == "subject-pair" and not out_of_band(check)


def reads_the_tree(row: CallRow) -> bool:
    """A check that reads the scenario's working directory at one moment, by its nature or through the `file=` it names."""
    spec = CHECK_BY_NAME.get(row.name)
    return spec is not None and (spec.cli_reads_tree or "file" in row.args)


def _touches_the_tree(row: CallRow) -> bool:
    """A check that needs the working directory recorded around the run."""
    return compares_the_tree(row.name) or reads_the_tree(row)


def _operand(row: CallRow, observed: str, before: str, after: str) -> str | ScenarioRefusal:
    """What a verify on a command's run is handed, or why a command shows it nothing to read."""
    check = row.name
    spec = CHECK_BY_NAME.get(check)
    if spec is not None and not spec.cli_reads and not spec.out_of_band:
        readable = ", ".join(f"`{s.name}`" for s in CHECKS if s.cli_reads)
        return ScenarioRefusal(
            "uncompilable-claim",
            f"`{check}` reads nothing a command shows, so it does not compile on a cli: "
            f"verify this claim with one of {readable}, as `ostler checks` describes")
    if compares_the_tree(check):
        return f"({before}, {after})"
    if reads_the_tree(row):
        return after
    return operand_for(check, observed, row.args)


def _start_operand(row: CallRow) -> str | ScenarioRefusal:
    """What a verify on a flow's `start:` is handed: the working directory before the first step, since no command has run yet."""
    if reads_the_tree(row):
        return "before"
    check = row.name
    spec = CHECK_BY_NAME.get(check)
    reads = spec.cli_reads if spec is not None and spec.cli_reads else "nothing a command shows"
    readable = ", ".join(f"`{s.name}`" for s in CHECKS if s.cli_reads_tree)
    files = ", ".join(f"`{s.name}`" for s in CHECKS if any(p.name == "file" for p in s.params))
    return ScenarioRefusal(
        "uncompilable-claim",
        f"`{check}` on a flow's `start:` reads {reads}, and no command has run before the "
        f"first step: verify the starting world with {readable} on the file it names, or "
        f"{files} with `file=` naming it, or state it on `fixture:`")


def _no_run_remedy(node_type: str) -> str:
    """What to change on the page when a CLI claim's node names no `run:`."""
    if "run" in registry.performed_keys(node_type):
        return (
            f"this {node_type} declares no `run:` for this claim. Add "
            '`- run: invoke(argv=["<subcommand>", "<arg>"])` to the node, before the claims it '
            "performs. `usage:`/`flags:`/`args:` are prose the compiler cannot run"
        )
    return (
        f"a {node_type} takes no `run:`, so a command-line scenario has nothing to call. "
        "State this claim on the `invocation` whose `run:` reaches this code, "
        "and cite the same `code:` there"
    )


def _gap_cli_obligations(obligations: list[Obligation], gaps: list[Gap]) -> None:
    """Command-linked obligations with no `run:` for the CLI builder to bind to."""
    for obligation in obligations:
        gaps.append(Gap(obligation.id, "uncompilable-claim", _no_run_remedy(obligation.node_type)))


def _cli_actions(obligation: Obligation) -> list[CallRow]:
    """The `run:`s of this obligation, in document order; the last is the one observed."""
    return [row for row in obligation.acts if row.name == "invoke"]


def _run_arguments(row: CallRow) -> str:
    """The arguments of the `.run(...)` call that performs *row*: its argv, the scenario's checkout copy and its environment."""
    env = row.map_arg("env")
    parts = [*map(python_literal, row.list_arg("argv")), "cwd=qa.scenario_checkout_copy()"]
    if env:
        parts.append(f"env=qa.scenario_env({python_literal(env)})")
    return ", ".join(parts)


def invoke_env_names(rows: Iterable[CallRow]) -> list[str]:
    """Every environment variable name an `invoke` among *rows* sets, sorted."""
    return sorted({name for row in rows if row.name == "invoke" for name in row.map_arg("env")})


def _verify_line(row: CallRow, operand: str, oid: str) -> str:
    """The `qa.verify(...)` line that asserts *row* on *operand* for obligation *oid*."""
    return (f"    qa.verify({python_literal(row.name)}, {operand}{call_kwargs(row.args)}, "
            f"covers=[{python_literal(oid)}])")


def cli_scenario_body(
    obligations: list[Obligation], gaps: list[Gap], covered: set[str], binary: str | None,
    resources: Mapping[str, frozenset[str]] | None = None,
) -> list[str]:
    """Compile every CLI obligation's assertion half — `_scenario_body`'s counterpart for a `command` node instead of a route."""
    lines: list[str] = []
    index = 0
    for obligation in sorted(obligations, key=lambda o: o.doc_position):
        oid = obligation.id
        rows = obligation.checks
        requirement = " ".join(obligation.requirement.split())
        lines.append("")
        lines.append(f"    # {oid}")
        lines.append(f"    # {requirement}")
        index += 1
        name = f"observed_{index}"
        runs = _cli_actions(obligation)
        if not runs:
            lines.append(
                "    # TODO(arrange): this command declares no `run:` — `usage:`/`flags:`/"
                "`args:` are prose, not a concrete invocation")
            lines.append(f"    {name} = None  # TODO(arrange): what this scenario observes")
            _gap_cli_obligations([obligation], gaps)
            continue
        if binary is None:
            lines.append(
                "    # TODO(arrange): the owning `cli` node declares no `binary:`, so this "
                "compiler cannot name the executable this `run:` invokes")
            lines.append(f"    {name} = None  # TODO(arrange): what this scenario observes")
            gaps.append(Gap(
                oid, "uncompilable-claim",
                "the owning `cli` node declares no `binary:`, so the compiler cannot name "
                "the executable this `run:` invokes",
            ))
            continue
        tool = f"qa.tool({python_literal(binary)})"
        *setup, observed_args = map(_run_arguments, runs)
        lines.extend(f"    _ = {tool}.run({call_args})" for call_args in setup)
        reads_tree_either_side = any(_touches_the_tree(row) for row in rows)
        if reads_tree_either_side:
            lines.append(f"    before_{index} = qa.tree(qa.scenario_checkout_copy())")
        lines.append(f"    {name} = {tool}.run({observed_args})")
        if reads_tree_either_side:
            lines.append(f"    after_{index} = qa.tree(qa.scenario_checkout_copy())")

        assertions: list[str] = []
        whole = True
        for row in rows:
            operand = _operand(row, name, f"before_{index}", f"after_{index}")
            if isinstance(operand, ScenarioRefusal):
                lines.append(f"    # TODO(arrange): {operand.detail}")
                gaps.append(Gap(oid, operand.kind, operand.detail))
                whole = False
                continue
            assertions.append(_verify_line(row, operand, oid))
        if within_off_observation(obligation, gaps):
            whole = False
        side = observation_lines(obligation, name, resources or {}, gaps)
        if whole and side.whole:
            lines.extend(assertions)
            lines.extend(side.lines)
            covered.add(oid)
    return lines


def _node_call(
    where: str, ref: str, acts_by_node: dict[str, list[CallRow]], acts_refused: set[str],
    cli_binaries: dict[str, str],
) -> str | StepRefusal:
    """The `qa.tool(...).run(...)` the node *ref* performs, or why the book names none."""
    if ref in acts_refused:
        return StepRefusal(f"{where} links a node whose act bullets could not be read")
    invokes = {row.call: row for row in acts_by_node.get(ref, []) if row.name == "invoke"}
    if not invokes:
        return StepRefusal(f"{where} links a node that declares no `run:` for this journey to perform")
    if len(invokes) > 1:
        return StepRefusal(
            f"{where} links a node that declares {len(invokes)} different `run:`s, and a "
            "step performs one: link the invocation that states the run this step means")
    binary = cli_binaries.get(ref.split("#", 1)[0])
    if binary is None:
        return StepRefusal(
            f"{where} links a node whose owning `cli` node declares no `binary:`, so "
            "the compiler cannot name the executable its `run:` invokes")
    return f"qa.tool({python_literal(binary)}).run({_run_arguments(next(iter(invokes.values())))})"


def _stated_exit(claim: Obligation) -> int | None:
    """The exit code a declared `exit_status` check of *claim* expects."""
    for row in claim.checks:
        code = row.args.get("code")
        if row.name == "exit_status" and isinstance(code, int) and not isinstance(code, bool):
            return code
    return None


def _case_codes(claim: Obligation) -> set[int]:
    """The exit codes one invocation claim expects: its `exit_status` codes, else the code its refusal bullet states."""
    codes = {code for row in claim.checks if row.name == "exit_status"
             if isinstance(code := row.args.get("code"), int) and not isinstance(code, bool)}
    stated = claim.requirement.strip()
    if not codes and claim.kind in registry.refusal_keys(claim.node_type) and stated.isdigit():
        codes.add(int(stated))
    return codes


def _expected_claims(step: FlowStep, book: BookIndex) -> list[Obligation]:
    """The claims one step's run is held to: an invocation's one case, else a command's success claims."""
    if step.node_type == "invocation":
        return list(book.invocation_claims.get(step.ref, ()))
    refusing = registry.refusal_keys("command")
    return [claim for claim in book.outcomes_by_node.get(step.ref, ())
            if claim.kind not in refusing and _stated_exit(claim) in (None, 0)]


def _state_rows(state: DataState, observed: str) -> list[str] | str:
    """The `(check, operand, args)` tuples that assert *state* on the run held in *observed*, or why no operand observes one."""
    rows: list[str] = []
    for text in state.verify:
        call = parse_check(text)
        if not isinstance(call, CheckCall):
            continue
        row = CallRow(call.name, call.text(), dict(call.args), {})
        if compares_the_tree(row.name):
            return f"`{row.name}` compares the working directory before and after a run, which a read has no pair of"
        operand = _operand(row, observed, "", f"{observed}_tree")
        if isinstance(operand, ScenarioRefusal):
            return operand.detail
        args = "{" + ", ".join(f"{python_literal(key)}: {resolved_literal(value)}" for key, value in row.args.items()) + "}"
        rows.append(f"({python_literal(row.name)}, {operand}, {args})")
    return rows


def cli_read_back(where: str, observed: str, target: DataState, book: BookIndex) -> list[str] | str:
    """The lines that run *target*'s observing command and hold its checks on what it left, naming the sibling state that holds when they fail, or why the walk cannot read it."""
    label = f"{where} of `{anchor_of(target.node)}`"
    call = _node_call(label, target.observe, book.acts_by_node, book.acts_refused, book.cli_binaries)
    if isinstance(call, StepRefusal):
        return call.reason
    states = {target.node: _state_rows(target, observed)}
    states.update({other.node: _state_rows(other, observed) for other in siblings_of(target, book.data_states)})
    for rows in states.values():
        if isinstance(rows, str):
            return f"{label}: {rows}"
    held = ", ".join(f"{python_literal(anchor_of(node))}: [{', '.join(rows)}]"
                     for node, rows in states.items() if not isinstance(rows, str))
    taken_tree = any(reads_the_tree(CallRow(call.name, call.text(), dict(call.args), {}))
                     for state in (target, *siblings_of(target, book.data_states))
                     for call in map(parse_check, state.verify) if isinstance(call, CheckCall))
    return [
        f"    {observed} = {call}",
        *([f"    {observed}_tree = qa.tree(qa.scenario_checkout_copy())"] if taken_tree else []),
        f"    qa.holds({python_literal(anchor_of(target.node))}, {{{held}}})",
    ]


def _step_lines(
    index: int, step: FlowStep, call: str, book: BookIndex, ids: list[str], gaps: list[Gap], reached: set[str],
) -> list[str] | None:
    """The lines that run one step, hold its outcome and read back the state its `moves:` rows land on, all in one `qa.at_node` block, or `None` once a gap says why the walk stops."""
    claims = _expected_claims(step, book)
    if step.node_type == "invocation":
        codes = sorted({code for claim in claims for code in _case_codes(claim)})
        if len(codes) > 1:
            gaps.extend(Gap(oid, "uncompilable-claim", (
                f"step {index} ({step.href or step.ref!r}) links a node with several outcomes (exit codes "
                f"{', '.join(map(str, codes))}): link one case per step")) for oid in ids)
            return None
    rows = [(claim, row) for claim in claims for row in claim.checks]
    taped = any(_touches_the_tree(row) for _claim, row in rows)
    observed, before, after = f"observed_{index}", f"before_{index}", f"after_{index}"
    lines = [f"    {before} = qa.tree(qa.scenario_checkout_copy())"] if taped else []
    lines.append(f"    {observed} = {call}")
    if taped:
        lines.append(f"    {after} = qa.tree(qa.scenario_checkout_copy())")
    inside: list[str] = []
    for claim, row in rows:
        operand = _operand(row, observed, before, after)
        if isinstance(operand, ScenarioRefusal):
            gaps.append(Gap(claim.id, operand.kind, operand.detail))
            continue
        inside.append(f"    {_verify_line(row, operand, claim.id)}")
    for number, move in enumerate(book.moves.get(step.ref, ()), start=1):
        target = book.data_states.get(move.end)
        if target is None:
            continue
        name = f"moved_{index}" if number == 1 else f"moved_{index}_{number}"
        found = cli_read_back(f"step {index}'s read-back", name, target, book)
        if isinstance(found, str):
            gaps.extend(Gap(oid, "unresolved-precondition", found) for oid in ids)
            continue
        inside.extend(f"    {line}" for line in found)
        reached.update((move_obligation_id(step.ref, move.index), state_obligation_id(move.end)))
    if inside:
        lines.append(f"    with qa.at_node({python_literal(step.ref)}):")
        lines.extend(inside)
    return lines


def _walk_steps(
    steps: tuple[FlowStep, ...], book: BookIndex, ids: list[str], gaps: list[Gap],
) -> list[tuple[FlowStep, str]] | None:
    """Each step with the call it performs, or `None` once a gap says why a step names none."""
    calls: list[tuple[FlowStep, str]] = []
    for index, step in enumerate(steps, start=1):
        call = _node_call(f"step {index} ({step.href or step.ref!r})", step.ref, book.acts_by_node,
                          book.acts_refused, book.cli_binaries)
        if isinstance(call, StepRefusal):
            gaps.extend(Gap(oid, "uncompilable-claim", call.reason) for oid in ids)
            return None
        calls.append((step, call))
    return calls


def cli_journey(
    steps: tuple[FlowStep, ...],
    obligations: list[Obligation],
    ids: list[str],
    gaps: list[Gap],
    covered: set[str],
    captured: set[tuple[str, str]],
    book: BookIndex,
) -> tuple[list[str], frozenset[str]]:
    """Run each step's `run:` in order in one working directory, holding each step's outcome where it ran, then assert the flow's claims on what the walk left. Also the move and state obligations the read-backs reached."""
    decline_captures(obligations, gaps, captured, because=(
        "the CLI builder does not yet capture a fact out of a tool run"))
    expanded = expand_passages(
        steps, book.passages, lambda ref: "invocation" if ref in book.invocation_claims else "command", ids, gaps)
    if expanded is None:
        return [], frozenset()
    calls = _walk_steps(expanded, book, ids, gaps)
    if calls is None:
        return [], frozenset()
    reached: set[str] = set()
    stepped: list[str] = []
    for index, (step, call) in enumerate(calls, start=1):
        found = _step_lines(index, step, call, book, ids, gaps, reached)
        if found is None:
            return [], frozenset()
        stepped.extend(found)
    reads_tree_either_side = any(_touches_the_tree(row)
                                 for obligation in obligations for row in obligation.checks)
    lines = ["    before = qa.tree(qa.scenario_checkout_copy())"] if reads_tree_either_side else []
    starts = [obligation for obligation in obligations if obligation.kind == "start"]
    for obligation in starts:
        _append_journey_verifies(obligation, _start_operand, lines, gaps, covered)
    lines.extend(stepped)
    if reads_tree_either_side:
        lines.append("    after = qa.tree(qa.scenario_checkout_copy())")
    observed = f"observed_{len(calls)}"
    for obligation in obligations:
        if obligation.kind != "start":
            _append_journey_verifies(
                obligation, lambda row: _operand(row, observed, "before", "after"),
                lines, gaps, covered)
    return lines, frozenset(reached)


def cli_move_walk(
    step: FlowStep, start: DataState, book: BookIndex, gaps: list[Gap], ids: list[str],
) -> tuple[list[str], frozenset[str]] | None:
    """Read the record in *start*, run the one step, and hold the state its `moves:` row lands on, or `None` once a gap says why the walk cannot be built."""
    calls = _walk_steps((step,), book, ids, gaps)
    if calls is None:
        return None
    reached: set[str] = set()
    stepped = _step_lines(1, step, calls[0][1], book, ids, gaps, reached)
    if stepped is None or not set(ids) <= reached:
        return None
    before = cli_read_back("the read of the starting state", "before_move", start, book)
    if isinstance(before, str):
        gaps.extend(Gap(oid, "unresolved-precondition", before) for oid in ids)
        return None
    reached.add(state_obligation_id(start.node))
    lines = [f"    with qa.at_node({python_literal(start.node)}):", *(f"    {line}" for line in before), *stepped]
    return lines, frozenset(reached)


def cli_observe_walk(
    state: DataState, book: BookIndex, gaps: list[Gap], ids: list[str],
) -> list[str] | None:
    """Run the command that reads the record in *state* and hold the state's checks on what it left, or `None` once a gap says why the walk cannot read it."""
    read = cli_read_back("the read of the state", "observed", state, book)
    if isinstance(read, str):
        gaps.extend(Gap(oid, "unresolved-precondition", read) for oid in ids)
        return None
    return [f"    with qa.at_node({python_literal(state.node)}):", *(f"    {line}" for line in read)]


def _append_journey_verifies(
    obligation: Obligation, operand_of: Callable[[CallRow], str | ScenarioRefusal],
    lines: list[str], gaps: list[Gap], covered: set[str],
) -> None:
    """Append the verify lines of one journey obligation, or the gaps that keep it from compiling whole."""
    oid = obligation.id
    assertions: list[str] = []
    whole = True
    for row in obligation.checks:
        operand = operand_of(row)
        if isinstance(operand, ScenarioRefusal):
            lines.append(f"    # TODO(arrange): {operand.detail}")
            gaps.append(Gap(oid, operand.kind, operand.detail))
            whole = False
            continue
        assertions.append(_verify_line(row, operand, oid))
    if whole and assertions:
        lines.append("")
        lines.append(f"    # {oid}")
        lines.extend(assertions)
        covered.add(oid)
