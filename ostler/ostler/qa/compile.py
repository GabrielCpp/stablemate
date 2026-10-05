"""Compile a QA plan skeleton out of the book, without reading the implementation."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

from ostler import registry
from ostler.qa import book_index as book_index_mod
from ostler.qa.book_index import BookIndex
from ostler.qa.compile_cli import cli_scenario_body
from ostler.qa.compile_http import api_scenarios
from ostler.qa.compile_http import probe_scenarios
from ostler.qa.compile_http import http_walk
from ostler.qa.compile_journey import JourneyPlan
from ostler.qa.compile_journey import JourneyWalkers
from ostler.qa.compile_journey import journey_scenarios
from ostler.qa.compile_maestro import maestro_walk
from ostler.qa.compile_maestro import mobile_scenarios
from ostler.qa.compile_page import page_scenarios
from ostler.qa.compile_playwright import web_walk
from ostler.qa.compile_support import PYTHON
from ostler.qa.compile_support import unarranged_scenario_gap
from ostler.qa.compile_support import unarranged_state_gap
from ostler.qa.dispatch import OBSERVED_TYPES
from ostler.qa.dispatch import dispatch_target
from ostler.qa.navigation import SurfaceNavigation
from ostler.qa.navigation import entry_url_refusal
from ostler.qa.navigation import surface_row
from ostler.qa.obligation import FixtureRow
from ostler.qa.obligation import Obligation
from ostler.qa.outcome import QaOutcome
from ostler.qa.packet import ContextPacket
from ostler.qa.packet import packet_of
from ostler.qa.plan_source import EmittedScenarios
from ostler.qa.plan_source import Gap
from ostler.qa.plan_source import PlanSinks
from ostler.qa.plan_source import ScenarioRefusal
from ostler.qa.plan_source import SourceScenario
from ostler.qa.plan_source import arrangement_of
from ostler.qa.plan_source import by_source
from ostler.qa.plan_source import claim_scenario_function_name
from ostler.qa.plan_source import decline_captures
from ostler.qa.plan_source import python_literal
from ostler.qa.plan_source import scenario_lines
from ostler.qa.plan_source import target_lines
from ostler.qa.plan_source import target_variable



_ARRANGEMENT_GAPS = frozenset({
    "unresolved-precondition",
    "needs-trigger-action",
    "screen-preconditions-undeclared",
    "unarranged-interaction-precondition",
    "unidentifiable-screen",
    "unparsed-capture-bullet",
    "uncaptured-declaration",
})

GAP_KINDS = frozenset({
    "uncompilable-claim",
    "browser-fixture-off-browser",
    "unresolved-precondition",
    "unreachable-screen",
    "screen-preconditions-undeclared",
    "needs-snapshot",
    "needs-out-of-band-observation",
    "undeclared-entry-url",
    "undeclared-bundle-id",
    "unresolved-extends",
    "undeclared-check-locator",
    "unstated-claim-combiner",
    "no-verify-declared",
    "precondition-discharged-by-arrangement",
    "unarranged-state",
    "unarranged-journey",
    "unarranged-scenario",
    "unarranged-request-body",
    "unarrangeable-server-fault",
    "deletes-shared-fixture",
    "unarranged-interaction-precondition",
    "unidentifiable-screen",
    "unparsed-fixture",
    "undetermined-provided-fact",
    "unparsed-capture-bullet",
    "unparsed-check-bullet",
    "uncaptured-declaration",
    "needs-target-backend",
    "needs-multi-target-runtime",
    "needs-trigger-action",
    "needs-absence-check",
    "invalid-http-method",
    "undeclared-launch-screen",
    "unreachable-from-launch",
})

HARNESS_LIMIT_GAPS = frozenset({
    "needs-target-backend",
    "needs-multi-target-runtime",
    "needs-trigger-action",
    "needs-absence-check",
})


@dataclass(frozen=True)
class Plan:
    """`compile_plan_gaps` succeeded: `source` is a plan the plan format admits."""
    source: str
    gaps: list[Gap]
    files: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Refusal:
    """`compile_plan_gaps` minted no scenario: `gaps` is the whole account of why."""
    gaps: list[Gap]


Compilation = Plan | Refusal


def book_digest(context: dict[str, Any]) -> str:
    """A digest of *context*'s owed obligation id set — what a compiled plan's `book=` names."""
    return packet_of(context).digest


def _declared_captures(obligations: list[Obligation]) -> set[tuple[str, str]]:
    """Every `(obligation id, capture name)` the packet declares — the set to account for."""
    return {
        (obligation.id, capture.name)
        for obligation in obligations
        for capture in obligation.captures
        if capture.name
    }


def _split_by_entry_url(
    obligations: list[Obligation],
    navigation: dict[str, SurfaceNavigation],
    base_url: str | None,
    gaps: list[Gap],
) -> tuple[list[Obligation], dict[str, str]]:
    """Partition *obligations* on whether their surface's target `base_url` is known."""
    resolved_by_surface: dict[str, str | None] = {}
    for obligation in obligations:
        surface = obligation.surface
        if surface in resolved_by_surface:
            continue
        resolved_by_surface[surface] = surface_row(navigation, surface).entry_url or base_url

    kept: list[Obligation] = []
    for obligation in obligations:
        surface = obligation.surface
        url = resolved_by_surface[surface]
        if url is None:
            refusal = entry_url_refusal(surface)
            gaps.append(Gap(obligation.id, refusal.kind, refusal.detail, refusal.owner))
            continue
        kept.append(obligation)

    resolved = {surface: url for surface, url in resolved_by_surface.items() if url is not None}
    return kept, resolved


def _is_owed_for_dispatch(obligation: Obligation) -> bool:
    """Whether an obligation carries something a builder could act on."""
    return bool(obligation.checks) or obligation.kind == "states"


def compile_plan(
    context: dict[str, Any],
    *,
    story: str,
    run_id: str | None = None,
    base_url: str | None = None,
) -> str:
    """Render a `qa_plan.py` skeleton covering every obligation the change owes live proof."""
    result = compile_plan_gaps(context, story=story, run_id=run_id, base_url=base_url)
    assert isinstance(result, Plan), (
        "compile_plan has no way to report a refusal — call compile_plan_gaps directly if "
        "the context might compile to nothing"
    )
    return result.source


@dataclass(frozen=True)
class _UnreadableRule:
    """One way a claim's bullets fail to read, and the gap that says so."""
    kind: str
    applies: Callable[[Obligation], bool]
    detail: Callable[[Obligation], str]


def _undetermined_facts(obligation: Obligation) -> list[FixtureRow]:
    """The declared fixtures whose provided facts name no source, or two."""
    return [row for row in obligation.fixtures if row.provides_undetermined]


_UNREADABLE_RULES = (
    _UnreadableRule(
        "unstated-claim-combiner",
        lambda o: o.combiner_unstated,
        lambda o: ("the claim list this belongs to does not say whether its children are parts of one "
                   "effect or alternative outcomes, so the check written above them proves this claim "
                   "or refutes it and the book does not say which")),
    _UnreadableRule(
        "unparsed-fixture",
        lambda o: bool(o.fixtures_unparsed),
        lambda o: ("this claim's arrangement could not be read: "
                   + "; ".join(f"`fixture: {row.value}` is not a fixture reference — {row.problem}"
                               for row in o.fixtures_unparsed))),
    _UnreadableRule(
        "undetermined-provided-fact",
        lambda o: bool(_undetermined_facts(o)),
        lambda o: ("this claim's arrangement provides facts whose source the book does not state: "
                   + "; ".join(
                       f"`{row.name}` provides {', '.join(row.provides_undetermined)} with neither "
                       "`from:`/`read:` nor `is:`, or with both"
                       for row in _undetermined_facts(o)))),
    _UnreadableRule(
        "unparsed-check-bullet",
        lambda o: bool(o.checks_unparsed),
        lambda o: ("this claim's check could not be read: "
                   + "; ".join(f"`{row.value}` {row.problem}" for row in o.checks_unparsed))),
)


def _readable(owed: list[Obligation], gaps: list[Gap]) -> list[Obligation]:
    """Gap every claim whose bullets could not be read, and return the ones that can compile."""
    for rule in _UNREADABLE_RULES:
        gaps.extend(Gap(o.id, rule.kind, rule.detail(o)) for o in owed if rule.applies(o))
        owed = [o for o in owed if not rule.applies(o)]
    gaps.extend(
        Gap(o.id, "unparsed-capture-bullet",
            "this claim's capture could not be read, so it mints no fact for a later `$name` "
            "to resolve against: "
            + "; ".join(f"`capture: {row.value}` {row.problem}"
                        for row in o.captures_unparsed))
        for o in owed if o.captures_unparsed
    )
    return owed


@dataclass(frozen=True)
class ObligationLanes:
    """The owed obligations sorted by the builder that compiles each one."""
    page: list[Obligation] = field(default_factory=list[Obligation])
    http: list[Obligation] = field(default_factory=list[Obligation])
    cli: list[Obligation] = field(default_factory=list[Obligation])
    mobile: list[Obligation] = field(default_factory=list[Obligation])
    flow: list[Obligation] = field(default_factory=list[Obligation])
    no_verify: list[Obligation] = field(default_factory=list[Obligation])


def _driver(obligation: Obligation, navigation: dict[str, SurfaceNavigation]) -> str | None:
    """The driver that performs *obligation*: a CLI page's own, else its surface's."""
    if obligation.on_cli_page and obligation.node_type in OBSERVED_TYPES:
        return "cli"
    return surface_row(navigation, obligation.surface).driver


def _signs_in_off_browser(
    obligation: Obligation, navigation: dict[str, SurfaceNavigation], browser_fixtures: frozenset[str],
) -> Gap | None:
    """The gap for a claim that arranges a browser sign-in and is performed by something other than a browser."""
    signing = sorted({row.name for row in obligation.fixtures if row.name in browser_fixtures})
    if not signing:
        return None
    target = dispatch_target(obligation.node_type, _driver(obligation, navigation))
    if target == "playwright":
        return None
    runner = target if isinstance(target, str) else "no runner"
    return Gap(obligation.id, "browser-fixture-off-browser", (
        f"fixture {', '.join(signing)} signs a browser in, and this {obligation.node_type} claim on "
        f"surface {obligation.surface!r} is performed by {runner}, which opens no browser: arrange "
        "this claim with a fixture whose steps all `run:`, or state it on a screen of a browser surface"))


def _dispatch(
    owed: list[Obligation], navigation: dict[str, SurfaceNavigation], gaps: list[Gap],
    browser_fixtures: frozenset[str] = frozenset(),
) -> ObligationLanes:
    """Route each owed obligation to the builder D1's table names for its node and surface."""
    lanes = ObligationLanes()
    by_target = {"playwright": lanes.page, "http": lanes.http, "cli": lanes.cli, "maestro": lanes.mobile}
    for obligation in owed:
        if not _is_owed_for_dispatch(obligation):
            lanes.no_verify.append(obligation)
            continue
        off_browser = _signs_in_off_browser(obligation, navigation, browser_fixtures)
        if off_browser is not None:
            gaps.append(off_browser)
            continue
        if obligation.node_type == "flow":
            lanes.flow.append(obligation)
            continue
        target = dispatch_target(obligation.node_type, _driver(obligation, navigation))
        if isinstance(target, ScenarioRefusal):
            gaps.append(Gap(obligation.id, target.kind, target.detail, target.owner))
            continue
        by_target[target].append(obligation)
    return lanes


def _no_verify_detail(obligation: Obligation) -> str:
    """Why this obligation has no check, and the edit that gives it one."""
    if obligation.node_type == "untyped":
        headings = ", ".join(f"`## {heading}`" for heading in registry.UI_HEADING_TO_TYPE)
        return (
            f"`{obligation.node}` sits under a heading that gives its sections no type, so no "
            "`verify:` bullet in it binds to a claim, however many it has. Move the section under "
            f"the page's heading for its type ({headings}); an invented heading such as "
            "`## Additional endpoint notes` types nothing"
        )
    return (
        "the book declares no check for this obligation to prove. Add a `- verify: <check>(...)` "
        "bullet right after the claim, naming what a run would observe. `ostler checks` prints "
        "every check with its arguments"
    )


def _book_debt(no_verify: list[Obligation], gaps: list[Gap]) -> list[Obligation]:
    """Gap every obligation that declares no check, and return the ones that are book debt."""
    when_owed = [o for o in no_verify if o.kind == "when"]
    debt = [o for o in no_verify if o.kind != "when"]
    gaps.extend(Gap(o.id, "no-verify-declared", _no_verify_detail(o)) for o in debt)
    gaps.extend(
        Gap(o.id, "precondition-discharged-by-arrangement",
            "this `when:` states a condition under which the node's claims hold, not an "
            "observable claim, so no check is expected to prove it — a `when:` precondition "
            "the compiler tried and failed to arrange is reported separately as "
            "`unarranged-interaction-precondition`")
        for o in when_owed
    )
    return debt


def _plan_header(digest: str, story: str, run_id: str | None) -> list[str]:
    """The plan module's banner, imports and `plan(...)` call."""
    return [
        "# Compiled from the book by `ostler qa compile-plan`. Every `covers=` below is the",
        "# obligation the book itself attributed the check to. Fill the TODO markers from the",
        "# story, the fixtures and the flows — not from the implementation, which is the thing",
        "# under test and cannot also be the specification it is tested against.",
        "",
        "from ostler_qa import Qa, plan, scenario, target",
        "",
        "",
        f"plan(run_id={python_literal(run_id or f'qa-{story}')}, story={python_literal(story)}, "
        f"book={python_literal(digest)})",
    ]


def _cli_scenarios(
    cli_owed: list[Obligation], book: BookIndex, sinks: PlanSinks, emitted: EmittedScenarios,
) -> list[str]:
    """One scenario per book page whose commands owe live evidence, each run as the built tool."""
    declared = [o for o in cli_owed if o.checks]
    sinks.gaps.extend(unarranged_state_gap(o) for o in cli_owed if not o.checks)
    decline_captures(declared, sinks.gaps, sinks.captured, because=(
        "the CLI builder does not yet capture a fact out of a tool run"))
    lines: list[str] = []
    for source, obligations in by_source(declared).items():
        arrangement = arrangement_of(obligations)
        if arrangement.unstated:
            sinks.gaps.extend(unarranged_scenario_gap(o) for o in obligations)
            continue
        covered: set[str] = set()
        body = cli_scenario_body(obligations, sinks.gaps, covered, book.cli_binaries.get(source))
        if not covered:
            continue
        emitted.covered.update(covered)
        target_var = target_variable(obligations[0].surface, "cli")
        lines.extend(target_lines(target_var, PYTHON.name, "", emitted))
        scenario = SourceScenario(
            source, target_var, [o.id for o in obligations if o.id in covered],
            arrangement, body)
        lines.extend(scenario_lines(scenario, claim_scenario_function_name(scenario, emitted)))
    return lines


def _debt_lines(debt: list[Obligation]) -> list[str]:
    """The trailing comment block listing every obligation that declares no check."""
    if not debt:
        return []
    lines = [
        "",
        "",
        "# Book debt. Each of these is owed live evidence by this change and declares no",
        "# `verify:`, so there is nothing to compile and nothing an author could copy. The",
        "# fix is a check on the bullet in the book, not an assertion invented down here.",
    ]
    for obligation in debt:
        requirement = " ".join(obligation.requirement.split())
        lines.append(f"#   {obligation.id}")
        lines.append(f"#     {requirement[:100]}")
    return lines


def _assert_accounted(
    packet: ContextPacket, owed: list[Obligation], sinks: PlanSinks, covered_ids: set[str],
) -> None:
    """Fail loudly when an owed obligation or declared capture fell through every builder."""
    known_ids = {o.id for o in packet.obligations}
    for gap in sinks.gaps:
        assert gap.obligation_id in known_ids, (
            f"compiled a {gap.kind!r} gap keyed by {gap.obligation_id!r}, which is not a known "
            "obligation id — every Gap must be filterable by the live-audit's "
            "`covers` intersection, which only ever holds real obligation ids"
        )
    gapped_ids = {gap.obligation_id for gap in sinks.gaps}
    dropped = {o.id for o in owed} - gapped_ids - covered_ids
    assert not dropped, (
        f"{len(dropped)} owed obligation(s) landed in neither `gaps` nor a compiled scenario: "
        f"{sorted(dropped)!r}"
    )
    unobserved = {gap.obligation_id for gap in sinks.gaps if gap.kind not in _ARRANGEMENT_GAPS}
    unaccounted = _declared_captures(owed) - sinks.captured
    unaccounted -= {pair for pair in unaccounted if pair[0] in unobserved}
    assert not unaccounted, (
        f"{len(unaccounted)} declared capture(s) were neither emitted nor gapped by the builder "
        f"that declined them: {sorted(unaccounted)!r}"
    )
    contradicted = unobserved & covered_ids
    assert not contradicted, (
        f"{len(contradicted)} obligation(s) are both gapped as unobserved and claimed by a "
        f"compiled scenario: {sorted(contradicted)!r}"
    )


def compile_plan_gaps(
    context: dict[str, Any],
    *,
    story: str,
    run_id: str | None = None,
    base_url: str | None = None,
    covered_ids: set[str] | None = None,
) -> Compilation:
    """Compile the book into a plan, or refuse and say why nothing compiled."""
    return _compile_packet(packet_of(context), story=story, run_id=run_id, base_url=base_url,
                           covered_ids=covered_ids)


def _compile_packet(
    packet: ContextPacket,
    *,
    story: str,
    run_id: str | None,
    base_url: str | None,
    covered_ids: set[str] | None,
) -> Compilation:
    """Compile one validated packet into a plan, or refuse and say why nothing compiled."""
    sinks = PlanSinks(gaps=[], captured=set(), files={})
    emitted = EmittedScenarios(targets=set(), covered=set() if covered_ids is None else covered_ids)
    owed = _readable(packet.owed, sinks.gaps)
    navigation = packet.navigation
    lanes = _dispatch(owed, navigation, sinks.gaps, packet.browser_fixtures)
    debt = _book_debt(lanes.no_verify, sinks.gaps)
    http_owed, api_urls = _split_by_entry_url(lanes.http, navigation, base_url, sinks.gaps)
    page_owed, web_urls = _split_by_entry_url(lanes.page, navigation, base_url, sinks.gaps)
    carried = list(packet.obligations)
    acts = book_index_mod.node_acts(carried)
    book = BookIndex(
        locators_by_node=book_index_mod.node_locator_index(carried),
        screen_routes=packet.screen_routes,
        acts_by_node=acts.by_node, acts_refused=acts.refused,
        captures_by_node=book_index_mod.captures_by_node(carried),
        cli_binaries=packet.cli_binaries,
        resolved_web_base_urls=web_urls, resolved_api_base_urls=api_urls,
        queries_by_node=book_index_mod.queries_by_node(carried),
        claims_by_node=acts.claims_by_node,
        hop_acts=book_index_mod.hop_acts(carried, acts.by_node),
        fixture_pages=book_index_mod.fixture_pages(carried, rebuilt=packet.scenario_fixtures),
        fragment_hosts=packet.fragment_hosts,
        guards_by_node=book_index_mod.guards_by_node(carried),
    )
    journeys = JourneyPlan(book=book, sinks=sinks, navigation=navigation, walkers=_JOURNEY_WALKERS)
    lines = [
        *_plan_header(packet.digest, story, run_id),
        *probe_scenarios(http_owed, book, emitted),
        *api_scenarios(http_owed, book, sinks, emitted),
        *_cli_scenarios(lanes.cli, book, sinks, emitted),
        *mobile_scenarios(lanes.mobile, book, navigation, sinks, emitted),
        *page_scenarios(navigation, page_owed, book, sinks, emitted),
        *journey_scenarios(lanes.flow, journeys, emitted),
        *_debt_lines(debt),
    ]
    _assert_accounted(packet, owed, sinks, emitted.covered)
    if not emitted.targets:
        return Refusal(sinks.gaps)
    return Plan("\n".join(lines).rstrip() + "\n", sinks.gaps, files=sinks.files)


def deferred_obligations(packet: ContextPacket, *, story: str) -> dict[str, Gap]:
    """Which owed obligations the reference compiler gapped without also covering."""
    covered: set[str] = set()
    result = _compile_packet(packet, story=story, run_id=None, base_url=None, covered_ids=covered)
    deferred: dict[str, Gap] = {}
    for gap in result.gaps:
        if gap.obligation_id in covered:
            continue
        deferred.setdefault(gap.obligation_id, gap)
    return deferred


def annotate_deferred_obligations(context: dict[str, Any], *, story: str = "") -> dict[str, Any]:
    """Stamp each obligation `deferred_obligations` names, in place, with why; *story* falls back to the packet's own slug."""
    packet = packet_of(context)
    deferred = deferred_obligations(packet, story=story or packet.story_slug or "story")
    for obligation in context.get("obligations", []):
        gap = deferred.get(str(obligation.get("id")))
        if gap is not None:
            obligation["deferred"] = {"kind": gap.kind, "detail": gap.detail}
    return context


_JOURNEY_WALKERS = JourneyWalkers(http=http_walk, web=web_walk, maestro=maestro_walk)


def cmd_compile_plan(
    spec_dir: Path,
    *,
    out: Path | None = None,
    story: str = "",
    run_id: str | None = None,
    base_url: str | None = None,
) -> QaOutcome:
    """Compile `spec_dir/qa-okf-context.json` into a plan skeleton."""
    context_file = spec_dir / "qa-okf-context.json"
    try:
        raw = json.loads(context_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{context_file} does not hold a context packet object")
        packet = packet_of(raw)
    except (OSError, ValueError) as exc:
        return QaOutcome(ok=False, message=f"error: {exc}", status="invalid",
                         data={"status": "invalid", "problems": [str(exc)]})

    story_name = story or packet.story_slug or "story"
    result = _compile_packet(packet, story=story_name, run_id=run_id, base_url=base_url,
                             covered_ids=None)

    owed = packet.owed
    declared = [o for o in owed if o.checks]
    owed_ids = [o.id for o in owed]
    no_verify_ids = {gap.obligation_id for gap in result.gaps if gap.kind == "no-verify-declared"}
    data: dict[str, Any] = {
        "owed": len(owed),
        "declared": len(declared),
        "debt": [oid for oid in owed_ids if oid in no_verify_ids],
        "gaps": [
            {"severity": "error", "code": gap.kind, "message": gap.detail, "ref": gap.obligation_id}
            for gap in result.gaps
        ],
    }

    if isinstance(result, Refusal):
        by_kind: dict[str, int] = {}
        for gap in result.gaps:
            by_kind[gap.kind] = by_kind.get(gap.kind, 0) + 1
        problems = [f"{kind}: {count}" for kind, count in sorted(by_kind.items())]
        return QaOutcome(
            ok=False,
            message=(
                "no scenario compiled — nothing this book states could be turned into "
                f"executable evidence ({len(result.gaps)} gap(s))"
            ),
            status="invalid",
            data={**data, "problems": problems},
        )
    source = result.source

    if out is None:
        return QaOutcome(ok=True, message=source, status="passed", data={**data, "plan": source})
    if out.exists():
        return QaOutcome(
            ok=False,
            message=f"error: {out} already exists; move it aside or compile to stdout",
            status="invalid",
            data={**data, "problems": [f"{out} already exists"]},
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(source, encoding="utf-8")
    for relpath, content in result.files.items():
        aux = out.parent / relpath
        aux.parent.mkdir(parents=True, exist_ok=True)
        aux.write_text(content, encoding="utf-8")
    return QaOutcome(
        ok=True,
        message=(f"Compiled {len(declared)} of {len(owed)} owed obligations into {out}.\n"
                 f"{len(data['debt'])} owed obligation(s) declare no `verify:` and are listed "
                 f"as book debt in the file."),
        status="passed",
        data=data,
    )
