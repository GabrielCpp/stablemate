"""What every plan builder shares: the gap record and the literal spelling of a check call."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from ostler.checks import CHECK_BY_NAME
from ostler.qa import references
from ostler.qa.obligation import FixtureRow
from ostler.qa.obligation import Obligation


_IDENTIFIER_BREAK = re.compile(r"[^0-9a-zA-Z]+")


@dataclass(frozen=True)
class Gap:
    """One obligation left uncompiled, and why — `compile_plan`'s structured gap report."""
    obligation_id: str
    kind: str
    detail: str


@dataclass(frozen=True)
class ScenarioRefusal:
    """Why no scenario can be minted for an obligation: the gap kind and its detail."""
    kind: str
    detail: str


def check_observes(name: str | None) -> str | None:
    """What check *name* is handed to look at, or `None` for an unknown/missing check."""
    spec = CHECK_BY_NAME.get(name) if name else None
    return spec.observes if spec is not None else None


def out_of_band(name: str | None) -> bool:
    """Whether *name* observes through a channel this compiler has no handle on."""
    spec = CHECK_BY_NAME.get(name) if name else None
    return spec.out_of_band if spec is not None else False


def python_literal(value: object) -> str:
    """A Python literal spelled the way the repo's formatter would spell it."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(python_literal(item) for item in value) + "]"
    return json.dumps(value)


def call_kwargs(args: Mapping[str, object]) -> str:
    """Render a check's declared arguments verbatim, wrapping only literals holding a reference."""
    parts = []
    for name, value in args.items():
        if isinstance(value, str) and references.find_references(value):
            parts.append(f", {name}=qa.resolve({python_literal(value)})")
        else:
            parts.append(f", {name}={python_literal(value)}")
    return "".join(parts)


def file_refusal(check: str) -> ScenarioRefusal:
    """Why a check naming a `file=` does not compile where no command ran in a working directory."""
    return ScenarioRefusal(
        "uncompilable-claim",
        f"`{check}(file=...)` reads a file a command left in its working directory, and "
        "this surface runs no command: drop `file=` and read what the surface shows, or "
        "state the claim on the cli that writes the file")


def operand_for(check: str, observed: str, args: Mapping[str, object]) -> str | ScenarioRefusal:
    """What the compiled call is handed, or the arrangement it still needs and why."""
    if "file" in args:
        return file_refusal(check)
    observes = check_observes(check)
    if observes == "response":
        return observed
    if observes == "body":
        return f"{observed}.json()"
    if out_of_band(check):
        return ScenarioRefusal(
            "needs-out-of-band-observation",
            f"`{check}` observes a subject read through a channel this compiler has no "
            "handle on — arrange it out of band",
        )
    if observes == "subject":
        return observed
    return ScenarioRefusal(
        "needs-snapshot",
        f"`{check}` observes a subject before and after the action — hand it the pair",
    )


def decline_captures(
    obligations: list[Obligation],
    gaps: list[Gap],
    captured: set[tuple[str, str]],
    *,
    because: str,
) -> None:
    """Gap the captures this builder will not emit, from inside the builder that declined."""
    for obligation in obligations:
        for capture in obligation.captures:
            if not capture.name:
                continue
            captured.add((obligation.id, capture.name))
            gaps.append(Gap(
                obligation.id, "uncaptured-declaration",
                f"capture {capture.name!r} from {capture.source!r} is declared on "
                f"this node and {because}",
            ))


def python_identifier(path: str) -> str:
    """*path* spelled as a Python identifier, for a scenario function or target name."""
    stem = path.removesuffix(".md")
    ident = _IDENTIFIER_BREAK.sub("_", stem).strip("_").lower()
    return ident or "book"


def target_variable(surface: str, kind: str) -> str:
    """The variable (and literal target `name`) one surface's `kind` ("api"/"web") target gets."""
    return f"{python_identifier(surface)}_{kind}"


@dataclass(frozen=True)
class Arrangement:
    """What one scenario's obligations say about the state their claims are observed in."""

    rows: list[FixtureRow]
    stated_none: bool

    @property
    def unstated(self) -> bool:
        """Neither an arrangement nor a stated need for none — nothing may be compiled."""
        return not self.rows and not self.stated_none


def arrangement_of(obligations: list[Obligation]) -> Arrangement:
    """Every fixture the obligations in one scenario declare, in order, arranged once each."""
    rows = [row for obligation in obligations for row in obligation.fixtures]
    return Arrangement(
        rows=list({(row.name, row.args): row for row in rows}.values()),
        stated_none=any(o.arranges_nothing for o in obligations),
    )


def fixture_call(row: FixtureRow) -> str:
    """The `qa.fixture(...)` line that arranges *row* inside a scenario body."""
    return (f"    qa.fixture({python_literal(row.name)}"
            + "".join(f", {python_literal(arg)}" for arg in row.args) + ")")


@dataclass(frozen=True)
class PlanSinks:
    """Where every scenario builder in one plan records its gaps, its captured facts and its flow files."""
    gaps: list[Gap]
    captured: set[tuple[str, str]]
    files: dict[str, str]


@dataclass(frozen=True)
class EmittedScenarios:
    """What the plan has emitted so far: the target variables it declared, the obligations it covered and the scenario functions it named."""
    targets: set[str]
    covered: set[str]
    functions: set[str] = field(default_factory=set)


def by_source(obligations: list[Obligation]) -> dict[str, list[Obligation]]:
    """The obligations grouped by the book page that owes them, in first-seen order."""
    grouped: dict[str, list[Obligation]] = {}
    for obligation in obligations:
        grouped.setdefault(obligation.source or "book", []).append(obligation)
    return grouped


def target_lines(target_var: str, driver: str, kwargs: str, emitted: EmittedScenarios) -> list[str]:
    """The `target(...)` declaration for *target_var*, once per plan."""
    if target_var in emitted.targets:
        return []
    emitted.targets.add(target_var)
    return ["", f"{target_var} = target({python_literal(target_var)}, driver={python_literal(driver)}{kwargs})"]


@dataclass(frozen=True)
class SourceScenario:
    """One book page's compiled scenario: its target, the obligations it covers, and its arranged body."""
    source: str
    target_var: str
    covers: list[str]
    arranged: list[FixtureRow]
    body: list[str]


def claim_scenario_function_name(scenario: SourceScenario, emitted: EmittedScenarios) -> str:
    """Reserve the function name *scenario* gets, and return it: its page's, or its page's and its target's when another target on that page took the page's already."""
    page = python_identifier(scenario.source)
    name = f"{page}_from_the_book"
    if name in emitted.functions:
        name = f"{page}_on_{scenario.target_var}_from_the_book"
    emitted.functions.add(name)
    return name


def scenario_lines(scenario: SourceScenario, emitted: EmittedScenarios) -> list[str]:
    """The rendered `@scenario` source holding every obligation one book page owes live evidence for on one target."""
    arranged = scenario.arranged
    preconditions = [
        "    preconditions=[",
        *(f"        {python_literal(row.precondition)}," for row in arranged),
        "    ],",
    ] if arranged else ["    preconditions=[],"]
    fixtures = [
        "",
        *(fixture_call(row) for row in arranged),
    ] if arranged else []
    return [
        "",
        "",
        "@scenario(",
        f"    target={scenario.target_var},",
        '    mechanism="live",',
        "    covers=[",
        *(f"        {python_literal(oid)}," for oid in scenario.covers),
        "    ],",
        *preconditions,
        "    checkpoints=[],  # TODO(arrange): what an observer should see it prove",
        "    forbid=[],  # TODO: the weaker observations this scenario must not settle for",
        ")",
        f"def {claim_scenario_function_name(scenario, emitted)}(qa: Qa) -> None:",
        f'    """Obligations {scenario.source} owes live evidence for."""',
        *fixtures,
        *scenario.body,
    ]
