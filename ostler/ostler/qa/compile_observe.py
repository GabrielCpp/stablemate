"""A claim's side observations compiled: the harness reads a resource's document, and the claim's `verify:` rows held on it assert on that read."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ostler.checks import CheckValue
from ostler.qa import references
from ostler.qa.obligation import CallRow, Obligation
from ostler.qa.plan_source import Gap, call_kwargs, check_observes, python_literal


@dataclass(frozen=True)
class ObservationLines:
    """The `qa.observe` and `qa.verify` lines of one claim's observations, and whether every one compiled."""
    lines: list[str]
    whole: bool


def has_checks(obligation: Obligation) -> bool:
    """Whether the obligation declares anything to assert: a check on the response or a row held on an observation."""
    return bool(obligation.checks or obligation.observations or obligation.observations_unparsed)


def _without_within(args: Mapping[str, CheckValue]) -> dict[str, CheckValue]:
    return {name: value for name, value in args.items() if name != "within"}


def _args_literal(args: Mapping[str, CheckValue]) -> str:
    parts = []
    for name, value in args.items():
        if isinstance(value, str) and references.find_references(value):
            parts.append(f"{python_literal(name)}: qa.resolve({python_literal(value)})")
        else:
            parts.append(f"{python_literal(name)}: {python_literal(value)}")
    return "{" + ", ".join(parts) + "}"


def _seconds(rows: tuple[CallRow, ...]) -> int:
    waits = [w for row in rows if isinstance(w := row.args.get("within"), int) and not isinstance(w, bool)]
    return max(waits, default=0)


def within_off_observation(obligation: Obligation, gaps: list[Gap]) -> bool:
    """Gap each response row that carries `within=`, and say whether any did."""
    found = False
    for row in obligation.checks:
        if "within" in row.args:
            found = True
            gaps.append(Gap(obligation.id, "within-off-observation",
                            f"`{row.call}` waits with `within=`, and only a row held on an `observe:` has anything "
                            f"to wait for. A response is read once"))
    return found


def observation_lines(
    obligation: Obligation, variable: str, resources: Mapping[str, frozenset[str]], gaps: list[Gap],
) -> ObservationLines:
    """Each of the claim's observations read once through the harness, then its rows asserted on what the read returned."""
    oid = obligation.id
    lines: list[str] = []
    whole = True
    for unparsed in obligation.observations_unparsed:
        gaps.append(Gap(oid, "unparsed-observation", f"`observe: {unparsed.value}` {unparsed.problem}"))
        whole = False
    for number, row in enumerate(obligation.observations, start=1):
        held = resources.get(row.resource)
        if held is None or row.observation not in held:
            named = f"@{row.resource}.{row.observation}"
            why = "names no resource page" if held is None else "names an observation the page does not hold"
            gaps.append(Gap(oid, "unknown-observation", f"`observe: {named}` {why}"))
            whole = False
            continue
        name = f"{variable}_o{number}"
        waits = tuple(check for check in row.checks if "within" in check.args)
        until = ", ".join(f"({python_literal(check.name)}, {_args_literal(_without_within(check.args))})"
                          for check in waits)
        within = f", within={_seconds(row.checks)}, until=[{until}]" if waits else ""
        verifies: list[str] = []
        for check in row.checks:
            if check_observes(check.name) not in ("subject", "body") or "file" in check.args:
                gaps.append(Gap(oid, "uncompilable-claim",
                                f"`{check.name}` reads a response or a channel an observation does not have. "
                                f"A row held on `observe:` reads the document the resource returned"))
                whole = False
                continue
            verifies.append(f"    qa.verify({python_literal(check.name)}, {name}.json()"
                            f"{call_kwargs(_without_within(check.args))}, covers=[{python_literal(oid)}])")
        lines.append(f"    {name} = qa.observe({python_literal(row.resource)}, "
                     f"{python_literal(row.observation)}{within})")
        lines.extend(verifies)
    return ObservationLines(lines, whole)
