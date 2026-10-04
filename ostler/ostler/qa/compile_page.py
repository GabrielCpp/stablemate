"""The screen half of `compile-plan`: one arrival scenario per screen, and one per interaction arm."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ostler import acts as acts_mod
from ostler.qa.book_index import BookIndex
from ostler.qa.compile_playwright import WINDOW_VAR
from ostler.qa.compile_playwright import needs_window
from ostler.qa.compile_playwright import page_locator_expr
from ostler.qa.compile_playwright import page_observations
from ostler.qa.compile_playwright import perform_acts
from ostler.qa.compile_playwright import walk_hops
from ostler.qa.compile_support import PLAYWRIGHT
from ostler.qa.compile_support import bullet_value
from ostler.qa.compile_support import on_node
from ostler.qa.compile_support import on_label
from ostler.qa.compile_support import trailing_comment
from ostler.qa.compile_support import unarranged_state_gap
from ostler.qa.compile_support import vet_calls
from ostler.qa.navigation import NavHop
from ostler.qa.navigation import SurfaceNavigation
from ostler.qa.obligation import FixtureRow
from ostler.qa.obligation import NO_LOCATORS
from ostler.qa.obligation import Obligation
from ostler.qa.plan_source import EmittedScenarios
from ostler.qa.plan_source import Gap
from ostler.qa.plan_source import PlanSinks
from ostler.qa.plan_source import ScenarioRefusal
from ostler.qa.plan_source import arrangement_of
from ostler.qa.plan_source import check_observes
from ostler.qa.plan_source import decline_captures
from ostler.qa.plan_source import fixture_call
from ostler.qa.plan_source import python_identifier
from ostler.qa.plan_source import python_literal
from ostler.qa.plan_source import target_variable



def _prose_comment(text: str, *, label: str = "") -> list[str]:
    """*text* rendered as one or more `#`-prefixed lines, each four-space indented."""
    first, *rest = text.splitlines() or [""]
    lines = [f"    # {label}{first}"]
    lines.extend(f"    #   {line}" for line in rest)
    return lines


def _has_screens(navigation: dict[str, SurfaceNavigation]) -> bool:
    """Condition 1: a book with zero screen nodes on every surface grows no Playwright target."""
    return any(nav.screen_count > 0 for nav in navigation.values())


def page_scenarios(
    navigation: dict[str, SurfaceNavigation], page_owed: list[Obligation],
    book: BookIndex, sinks: PlanSinks, emitted: EmittedScenarios,
) -> list[str]:
    """Every screen's scenarios, or an `unreachable-screen` gap when the book has no screens."""
    if not page_owed:
        return []
    if not _has_screens(navigation):
        sinks.gaps.extend(
            Gap(o.id, "unreachable-screen",
                "the book's navigation graph has no screen nodes on any surface to walk to")
            for o in page_owed
        )
        return []
    return _compile_page_scenarios(book, navigation, page_owed, sinks, emitted)


@dataclass(frozen=True)
class _ScreenPath:
    """How a page scenario reaches one screen: its surface's root path and the hops from there."""
    root_path: str
    hops: tuple[NavHop, ...]


def _screen_path(
    navigation: dict[str, SurfaceNavigation], surface: str, screen: str,
) -> _ScreenPath | ScenarioRefusal:
    """The route to *screen* on *surface*, or why no page scenario can reach it."""
    nav = navigation.get(surface) if surface else None
    if nav is None:
        return ScenarioRefusal("uncompilable-claim",
                               f"surface {surface!r} has no `navigation` data to address this screen by")
    if screen in nav.unreachable:
        return ScenarioRefusal(
            "unreachable-screen",
            f"{surface}'s navigation cannot reach {screen} from its start screen {nav.start or '(none stated)'}; "
            f"no scenario compiled. On {screen}, state `entry: /<route>` when its route opens on its own "
            f"and holds no `:parameter` or `*`, or add a `leads-to:` link to it on the component that navigates there. "
            f"A route with a parameter is reached only through such a link",
            owner=screen)
    hops = nav.routes.get(screen)
    if hops is None:
        return ScenarioRefusal(
            "uncompilable-claim",
            f"{screen} is no screen of {surface} and continues none, so no page scenario can open it. "
            f"A `visible(...)` claim compiles on a screen page or on a fragment whose `host:` is one")
    opened = nav.path_to(screen)
    if opened is None:
        return ScenarioRefusal("uncompilable-claim",
                               f"surface {surface!r} states no root path a page scenario can open from")
    return _ScreenPath(opened, hops)


@dataclass(frozen=True)
class _Arrival:
    """One arrival scenario a screen compiles: its function name and the nodes it observes."""
    name: str
    nodes: dict[str, list[Obligation]]


@dataclass(frozen=True)
class _ScreenScenarios:
    """One screen's claims, sorted into the arrival scenarios and interaction scenarios they compile into."""
    arrivals: list[_Arrival]
    interactions: dict[str, list[Obligation]]


def _state_arrivals(
    slug: str, node_id: str, obligations: list[Obligation], gaps: list[Gap],
) -> list[_Arrival]:
    """One arrival per `states` claim that declares a check and arranges its state or says the seeded world is already in it, gapping the rest."""
    arrivals: list[_Arrival] = []
    for obligation in (o for o in obligations if o.kind == "states"):
        if obligation.checks and not arrangement_of([obligation]).unstated:
            arrivals.append(_Arrival(f"{slug}_{obligation.id.rsplit(':', 1)[-1]}", {node_id: [obligation]}))
        else:
            gaps.append(unarranged_state_gap(obligation))
    return arrivals


_SharedShape = Literal["interaction", "exclusive", "plain"]


@dataclass(frozen=True)
class _NodeClaims:
    """One node's claims on a screen: the arrivals it owns alone, and the rest with the scenario shape they share."""
    own_arrivals: list[_Arrival]
    remaining: list[Obligation]
    remaining_shape: _SharedShape | None


def _shared_shape(remaining: list[Obligation], gaps: list[Gap]) -> _SharedShape | None:
    """Which scenario a node's remaining claims compile into, or `None` after gapping ones nothing can address."""
    locators = remaining[0].locators
    if locators.on:
        return "interaction"
    if not page_locator_expr(locators):
        gaps.extend(Gap(oid, "uncompilable-claim",
                         "no addressable `### <component>` owns this `visible(...)` claim")
                    for oid in sorted(o.id for o in remaining))
        return None
    return "exclusive" if locators.exclusive_with else "plain"


def _node_claims(page: str, node_id: str, obligations: list[Obligation], gaps: list[Gap]) -> _NodeClaims:
    """Sort one node's claims into its state and keyboard arrivals, and the rest with their shared shape."""
    slug = f"{page}_{_node_slug(node_id)}"
    arrivals = _state_arrivals(slug, node_id, obligations, gaps)
    rest = [o for o in obligations if o.kind != "states"]
    keyboard = [o for o in rest if _observes_keyboard_only(o)]
    if keyboard:
        arrivals.append(_Arrival(f"{slug}_keyboard", {node_id: keyboard}))
        rest = [o for o in rest if o not in keyboard]
    return _NodeClaims(arrivals, rest, _shared_shape(rest, gaps) if rest else None)


def _screen_scenarios(source: str, group: list[Obligation], gaps: list[Gap]) -> _ScreenScenarios:
    """Assemble one screen's arrival and interaction scenarios per Amendment 3 from each node's sorted claims."""
    by_node: dict[str, list[Obligation]] = {}
    for obligation in group:
        by_node.setdefault(obligation.node, []).append(obligation)
    page = python_identifier(source)
    arrivals: list[_Arrival] = []
    plain: dict[str, list[Obligation]] = {}
    exclusive: list[_Arrival] = []
    interactions: dict[str, list[Obligation]] = {}
    for node_id, obligations in sorted(by_node.items()):
        claims = _node_claims(page, node_id, obligations, gaps)
        arrivals.extend(claims.own_arrivals)
        if claims.remaining_shape == "interaction":
            interactions[node_id] = claims.remaining
        elif claims.remaining_shape == "exclusive":
            exclusive.append(_Arrival(f"{page}_{_node_slug(node_id)}", {node_id: claims.remaining}))
        elif claims.remaining_shape == "plain":
            plain[node_id] = claims.remaining
    if plain:
        arrivals.append(_Arrival(f"{page}_arrival", plain))
    return _ScreenScenarios([*arrivals, *exclusive], interactions)


def _web_target_lines(
    book: BookIndex, lines_by_surface: dict[str, list[str]], emitted: EmittedScenarios,
) -> list[str]:
    """Each surface's page scenarios, preceded by its web target the first time one is emitted."""
    lines: list[str] = []
    for surface in sorted(lines_by_surface):
        surface_lines = lines_by_surface[surface]
        if not surface_lines:
            continue
        target_var = target_variable(surface, "web")
        if target_var in emitted.targets:
            lines.extend(surface_lines)
            continue
        web_target = (f'{target_var} = target({python_literal(target_var)}, driver={python_literal(PLAYWRIGHT.name)}, '
                      f'base_url={python_literal(book.resolved_web_base_urls.get(surface))})')
        emitted.targets.add(target_var)
        lines.extend(["", "", web_target, *surface_lines])
    return lines


def _compile_page_scenarios(
    book: BookIndex,
    navigation: dict[str, SurfaceNavigation],
    page_declared: list[Obligation],
    sinks: PlanSinks,
    emitted: EmittedScenarios,
) -> list[str]:
    """Compile every screen's `visible(...)` bullets, partitioned per Amendment 3."""
    gaps, covered = sinks.gaps, emitted.covered
    lines_by_surface: dict[str, list[str]] = {}
    by_screen: dict[tuple[str, str], list[Obligation]] = {}
    for obligation in page_declared:
        by_screen.setdefault((obligation.surface, obligation.source), []).append(obligation)

    for (surface, source), group in sorted(by_screen.items()):
        ids = sorted(o.id for o in group)
        shown_on = book.fragment_hosts.get(source, source)
        screen_path = _screen_path(navigation, surface, shown_on)
        if isinstance(screen_path, ScenarioRefusal):
            gaps.extend(Gap(oid, screen_path.kind, screen_path.detail, screen_path.owner) for oid in ids)
            continue
        if shown_on in navigation[surface].undeclared:
            gaps.append(Gap(ids[0], "screen-preconditions-undeclared",
                             "reachable, but this screen declares no `requires:`/`params:` bullets"))
        screen = _PageScreen(book, source, shown_on, screen_path, target_variable(surface, "web"))
        bucket = lines_by_surface.setdefault(surface, [])
        scenarios = _screen_scenarios(source, group, gaps)
        for arrival in scenarios.arrivals:
            bucket.extend(_arrival_scenario(screen, arrival, sinks, covered))
        for node_id, rest in scenarios.interactions.items():
            bucket.extend(_interaction_scenario(screen, node_id, rest, sinks, covered))
    return _web_target_lines(book, lines_by_surface, emitted)


def _observes_keyboard_only(obligation: Obligation) -> bool:
    """Whether every check *obligation* declares observes the keyboard."""
    rows = obligation.checks
    return bool(rows) and all(check_observes(row.name) == "keyboard" for row in rows)


def _node_slug(node_id: str) -> str:
    fragment = node_id.rsplit("#", 1)[-1]
    return python_identifier(fragment)


@dataclass(frozen=True)
class _PageScreen:
    """One screen a page scenario arrives at: the book it reads, the route to it, and the target it runs on."""
    book: BookIndex
    source: str
    screen: str
    path: _ScreenPath
    target_var: str


def _scenario_head(
    target_var: str, ids: list[str], covered: set[str], preconditions: list[str],
) -> list[str]:
    """The `@scenario(...)` decorator a page scenario opens with, its preconditions already literals."""
    if preconditions:
        precondition_lines = ["    preconditions=[",
                              *(f"        {row}," for row in preconditions),
                              "    ],"]
    else:
        precondition_lines = [
            "    preconditions=[],  # TODO(arrange): what must hold before this scenario runs",
        ]
    return [
        "",
        "",
        "@scenario(",
        f"    target={target_var},",
        '    mechanism="live",',
        "    covers=[",
        *(f"        {python_literal(oid)}," for oid in ids if oid in covered),
        "    ],",
        *precondition_lines,
        "    checkpoints=[],  # TODO(arrange): what an observer should see it prove",
        "    forbid=[],  # TODO: the weaker observations this scenario must not settle for",
        ")",
    ]


def _arrive(screen: _PageScreen, arranged: list[FixtureRow], gaps: list[Gap], ids: list[str]) -> list[str]:
    """Arrange the fixtures, open the surface's root, and click through to the screen."""
    return [
        *(fixture_call(row) for row in arranged),
        f"    qa.goto({python_literal(screen.path.root_path)})",
        *walk_hops(screen.path.hops, screen.screen, screen.book, gaps, ids),
    ]


def _arrival_scenario(
    screen: _PageScreen, arrival: _Arrival, sinks: PlanSinks, covered: set[str],
) -> list[str]:
    """Arrive at the screen through the book's own navigation and assert what it shows."""
    gaps = sinks.gaps
    obligations = [o for obs in arrival.nodes.values() for o in obs]
    decline_captures(obligations, gaps, sinks.captured, because=(
        "this scenario arrives at the screen and observes what is on it — nothing here performs "
        "an action that would produce a value to bind"))
    ids = sorted(o.id for o in obligations)
    arranged = arrangement_of(obligations).rows
    body = _arrive(screen, arranged, gaps, ids)
    body.extend(vet_calls([screen.screen], screen.book.screen_routes, ids, gaps, screen.book.fragment_hosts))
    for node_id in sorted(arrival.nodes):
        node_acts = screen.book.acts_by_node.get(node_id, [])
        if node_acts:
            body.extend(perform_acts(node_acts, acts_mod.WEB, gaps, ids).lines or [])
    observed = page_observations(
        [o for _node_id, obs in sorted(arrival.nodes.items()) for o in obs], gaps)
    if not observed.covered:
        return []
    if needs_window(observed.lines):
        body.insert(len(arranged), f"    {WINDOW_VAR} = qa.window()")
    covered.update(observed.covered)
    return [
        *_scenario_head(screen.target_var, ids, observed.covered,
                        [python_literal(row.precondition) for row in arranged]),
        f"def {arrival.name}(qa: Qa) -> None:",
        f'    """Arrive at {screen.screen} via the book\'s own navigation and check what it shows."""',
        "",
        *body,
        *observed.lines,
    ]


_CLICK_TRIGGER = "click"


@dataclass(frozen=True)
class _InteractionArm:
    """What an interaction's bullets say: the control it acts on, how, what follows, and when."""
    on_node_id: str
    label: str
    trigger: str
    does: str
    when: str


def _interaction_arm(source: str, obligation: Obligation) -> _InteractionArm:
    """The `on:`/`trigger:`/`does:`/`when:` bullets one interaction arm declares."""
    locators = obligation.locators

    def first(values: tuple[str, ...]) -> str:
        return next(iter(values), "")

    on_value = first(locators.on)
    on_node_id = on_node(source, on_value) or (f"{source}#{on_value}" if on_value else "")
    return _InteractionArm(on_node_id, on_label(on_value), first(locators.trigger), first(locators.does), first(locators.when))


def _trigger_refusal(arm: _InteractionArm, on_expr: str | None, when_arranged: bool) -> ScenarioRefusal | None:
    """Why no scenario can perform *arm*, or `None` when one can."""
    if on_expr is None:
        return ScenarioRefusal("unresolved-precondition",
                               f"no locator declared for `on:` component {arm.label!r}")
    if arm.when and not when_arranged:
        return ScenarioRefusal("unarranged-interaction-precondition",
                               f"`when:` states a precondition ({arm.when!r}) this scenario does "
                               "not arrange, so its assertions would observe an unestablished state")
    return None


def _scaffold_click_refusal(arm: _InteractionArm) -> ScenarioRefusal | None:
    """Why *arm*'s performed click is only a scaffold for a trigger that is not a click, or `None` when it is one."""
    if (bullet_value(arm.trigger) or "").lower() == _CLICK_TRIGGER:
        return None
    return ScenarioRefusal("unresolved-precondition",
                           f"trigger {arm.trigger!r} compiles to a scaffold click on {arm.label!r}, "
                           "not a verified action")


@dataclass(frozen=True)
class _PerformedTrigger:
    """An interaction arm's trigger as scenario lines: the acts that set it up, then the click and what it does."""
    setup: list[str]
    action: list[str]


def _performed_trigger(
    book: BookIndex, node_id: str, arm: _InteractionArm, gaps: list[Gap], ids: list[str],
) -> _PerformedTrigger | None:
    """Perform *arm*'s acts and click its `on:` control, or `None` with the gap filed when no scenario can."""
    node_acts = book.acts_by_node.get(node_id, [])
    performed = perform_acts(node_acts, acts_mod.WEB, gaps, ids).lines if node_acts else None
    when_arranged = performed is not None and node_id not in book.acts_refused
    on_expr = page_locator_expr(book.locators_by_node.get(arm.on_node_id, NO_LOCATORS))
    refusal = _trigger_refusal(arm, on_expr, when_arranged)
    if refusal is not None:
        gaps.extend(Gap(oid, refusal.kind, refusal.detail, refusal.owner) for oid in ids)
        return None
    scaffold = _scaffold_click_refusal(arm)
    if scaffold is not None:
        gaps.extend(Gap(oid, scaffold.kind, scaffold.detail, scaffold.owner) for oid in ids)
    action = [f"    {on_expr}.click()  # trigger: {trailing_comment(arm.trigger)}"]
    if arm.does:
        action.extend(_prose_comment(arm.does, label="does: "))
    return _PerformedTrigger(performed or [], action)


def _interaction_scenario(
    screen: _PageScreen, node_id: str, obligations: list[Obligation], sinks: PlanSinks,
    covered: set[str],
) -> list[str]:
    """Arrive, trigger the interaction, then assert what the book says holds afterward."""
    gaps, book = sinks.gaps, screen.book
    decline_captures(obligations, gaps, sinks.captured, because=(
        "the trigger is performed here, but this builder has no declared way to read a value "
        "back out of the page and bind it under that name"))
    arm = _interaction_arm(screen.source, obligations[0])
    ids = sorted(o.id for o in obligations)
    if obligations[0].extends_unresolved:
        gaps.extend(Gap(oid, "unresolved-extends",
                         "this arm's `extends:` target is missing or not the same node type, "
                         "so its control identity could not be inherited from the base case")
                    for oid in ids)
    arranged = arrangement_of(obligations).rows
    arrived = _arrive(screen, arranged, gaps, ids)
    trigger = _performed_trigger(book, node_id, arm, gaps, ids)
    if trigger is None:
        return []
    observed = page_observations(obligations, gaps)
    if not observed.covered:
        return []
    window = [f"    {WINDOW_VAR} = qa.window()"] if needs_window(observed.lines) else []
    body = [*arrived, *trigger.setup, *window, *trigger.action]
    covered.update(observed.covered)
    preconditions = [python_literal(row.precondition) for row in arranged]
    if arm.when:
        preconditions.append(python_literal(arm.when))
    return [
        *_scenario_head(screen.target_var, ids, observed.covered, preconditions),
        f"def {python_identifier(screen.source)}_{_node_slug(node_id)}(qa: Qa) -> None:",
        f"    {python_literal(f'{arm.label or node_id}: {arm.trigger}')}",
        "",
        *body,
        *vet_calls(observed.documents, book.screen_routes, ids, gaps, book.fragment_hosts),
        *observed.lines,
    ]
