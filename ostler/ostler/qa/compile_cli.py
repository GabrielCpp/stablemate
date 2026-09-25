"""The CLI builders: a `command` node's claims and a journey of `run:`s, as `qa.tool(...)` calls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ostler import registry
from ostler.checks import CHECK_BY_NAME
from ostler.checks import CHECKS
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


def _cli_action(obligation: Obligation) -> list[str] | None:
    """The argument list this obligation's `run:` names, or `None` if it named none."""
    for row in obligation.acts:
        if row.name == "invoke":
            return row.list_arg("argv")
    return None


def _verify_line(row: CallRow, operand: str, oid: str) -> str:
    """The `qa.verify(...)` line that asserts *row* on *operand* for obligation *oid*."""
    return (f"    qa.verify({python_literal(row.name)}, {operand}{call_kwargs(row.args)}, "
            f"covers=[{python_literal(oid)}])")


def cli_scenario_body(
    obligations: list[Obligation], gaps: list[Gap], covered: set[str], binary: str | None,
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
        argv = _cli_action(obligation)
        if argv is None:
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
        call_args = ", ".join([*(python_literal(a) for a in argv), "cwd=qa.scenario_dir"])
        reads_tree_either_side = any(_touches_the_tree(row) for row in rows)
        if reads_tree_either_side:
            lines.append(f"    before_{index} = qa.tree(qa.scenario_dir)")
        lines.append(f"    {name} = qa.tool({python_literal(binary)}).run({call_args})")
        if reads_tree_either_side:
            lines.append(f"    after_{index} = qa.tree(qa.scenario_dir)")

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
        if whole:
            lines.extend(assertions)
            covered.add(oid)
    return lines


def _step_call(
    index: int, step: FlowStep, *,
    acts_by_node: dict[str, list[CallRow]],
    acts_refused: set[str],
    cli_binaries: dict[str, str],
) -> str | StepRefusal:
    """The `qa.tool(...).run(...)` one journey step performs, or why the book names none."""
    ref = step.ref
    where = f"step {index} ({step.href!r})"
    if ref in acts_refused:
        return StepRefusal(f"{where} links a node whose act bullets could not be read")
    argvs = {row.call: row.list_arg("argv")
             for row in acts_by_node.get(ref, []) if row.name == "invoke"}
    if not argvs:
        return StepRefusal(f"{where} links a node that declares no `run:` for this journey to perform")
    if len(argvs) > 1:
        return StepRefusal(
            f"{where} links a node that declares {len(argvs)} different `run:`s, and a "
            "step performs one: link the invocation that states the run this step means")
    binary = cli_binaries.get(ref.split("#", 1)[0])
    if binary is None:
        return StepRefusal(
            f"{where} links a node whose owning `cli` node declares no `binary:`, so "
            "the compiler cannot name the executable its `run:` invokes")
    argv = next(iter(argvs.values()))
    return f"qa.tool({python_literal(binary)}).run({', '.join([*map(python_literal, argv), 'cwd=qa.scenario_dir'])})"


def cli_journey(
    steps: tuple[FlowStep, ...],
    obligations: list[Obligation],
    ids: list[str],
    gaps: list[Gap],
    covered: set[str],
    captured: set[tuple[str, str]],
    *,
    acts_by_node: dict[str, list[CallRow]],
    acts_refused: set[str],
    cli_binaries: dict[str, str],
) -> list[str]:
    """Run each step's `run:` in order in one working directory, then assert the flow's claims on what the walk left."""
    decline_captures(obligations, gaps, captured, because=(
        "the CLI builder does not yet capture a fact out of a tool run"))
    calls: list[str] = []
    for index, step in enumerate(steps, start=1):
        call = _step_call(index, step, acts_by_node=acts_by_node,
                          acts_refused=acts_refused, cli_binaries=cli_binaries)
        if isinstance(call, StepRefusal):
            gaps.extend(Gap(oid, "uncompilable-claim", call.reason) for oid in ids)
            return []
        calls.append(call)
    reads_tree_either_side = any(_touches_the_tree(row)
                                 for obligation in obligations for row in obligation.checks)
    lines = ["    before = qa.tree(qa.scenario_dir)"] if reads_tree_either_side else []
    starts = [obligation for obligation in obligations if obligation.kind == "start"]
    for obligation in starts:
        _append_journey_verifies(obligation, _start_operand, lines, gaps, covered)
    lines.extend(f"    observed_{index} = {call}" for index, call in enumerate(calls, start=1))
    if reads_tree_either_side:
        lines.append("    after = qa.tree(qa.scenario_dir)")
    observed = f"observed_{len(calls)}"
    for obligation in obligations:
        if obligation.kind != "start":
            _append_journey_verifies(
                obligation, lambda row: _operand(row, observed, "before", "after"),
                lines, gaps, covered)
    return lines


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
