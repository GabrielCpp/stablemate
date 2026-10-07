"""The flow half of `compile-plan`: bind each flow's journey to one driver and walk its steps."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from ostler import reach
from ostler.qa.book_index import BookIndex
from ostler.qa.compile_cli import cli_journey
from ostler.qa.dispatch import dispatch_target
from ostler.qa.navigation import MaestroLaunch
from ostler.qa.navigation import SurfaceNavigation
from ostler.qa.navigation import entry_url_refusal
from ostler.qa.navigation import maestro_launch
from ostler.qa.navigation import surface_row
from ostler.qa.obligation import FixtureRow
from ostler.qa.obligation import FlowStep
from ostler.qa.obligation import Obligation
from ostler.qa.plan_source import EmittedScenarios
from ostler.qa.plan_source import Gap
from ostler.qa.plan_source import PlanSinks
from ostler.qa.plan_source import ScenarioRefusal
from ostler.qa.plan_source import arrangement_of
from ostler.qa.plan_source import by_source
from ostler.qa.plan_source import fixture_call
from ostler.qa.plan_source import python_identifier
from ostler.qa.plan_source import python_literal
from ostler.qa.plan_source import target_lines
from ostler.qa.plan_source import target_variable


@dataclass(frozen=True)
class JourneyWalk:
    """One flow's journey, bound to the surface whose driver performs every step."""
    book: BookIndex
    steps: tuple[FlowStep, ...]
    obligations: list[Obligation]
    ids: list[str]
    nav: SurfaceNavigation
    left_on: str | None = None


@dataclass(frozen=True)
class WalkedJourney:
    """The scenario body a journey's walk compiled, and the obligations that body covers."""
    lines: list[str]
    covered: frozenset[str]


@dataclass(frozen=True)
class BoundJourney:
    """A journey whose target is settled: its variable, the source spliced into `target(...)`, and its walk."""
    target_var: str
    target_kwargs: str
    walk: Callable[[PlanSinks], WalkedJourney]


Walker = Callable[[JourneyWalk, PlanSinks], WalkedJourney]


@dataclass(frozen=True)
class JourneyWalkers:
    """The step builders the page, endpoint and mobile compilers lend the journey engine."""
    http: Walker
    web: Walker
    maestro: Callable[[JourneyWalk, MaestroLaunch, PlanSinks], WalkedJourney]


@dataclass(frozen=True)
class JourneyTarget:
    """The one D1 target that performs every step of a journey, and the surface it runs on."""
    target: str
    surface: str


@dataclass(frozen=True)
class JourneyBackend:
    """One journey target: the target it declares, and how a journey binds to it."""
    kind: str
    driver: str
    bind: Callable[[JourneyWalk], BoundJourney | ScenarioRefusal]


def _cli_walk(walk: JourneyWalk, sinks: PlanSinks) -> WalkedJourney:
    """Walk the journey as tool runs in one working directory."""
    book, covered = walk.book, set[str]()
    lines = cli_journey(walk.steps, walk.obligations, walk.ids, sinks.gaps, covered,
                        sinks.captured, acts_by_node=book.acts_by_node,
                        acts_refused=book.acts_refused, cli_binaries=book.cli_binaries)
    return WalkedJourney(lines, frozenset(covered))


def api_target(surface: str, source: str, book: BookIndex) -> tuple[str, str | None]:
    """The target a page's HTTP scenario runs on and its base URL: the server the page names, when its origin is not the surface's."""
    surface_url = book.resolved_api_base_urls.get(surface)
    origin = book.server_origins.get(source)
    if not origin or (surface_url and reach.url_origin(surface_url) == origin):
        return target_variable(surface, "api"), surface_url
    return f"{target_variable(surface, 'api')}_{python_identifier(urlparse(origin).netloc)}", origin


def _bind_at_base_url(
    target_var: str, url: str | None, walk: JourneyWalk, walker: Walker,
) -> BoundJourney | ScenarioRefusal:
    """Bind a journey whose target declares a `base_url=`, or refuse it for a missing entry URL."""
    if url is None:
        return entry_url_refusal(walk.nav.surface)
    return BoundJourney(target_var, f", base_url={python_literal(url)}", lambda sinks: walker(walk, sinks))


def _journey_backends(walkers: JourneyWalkers) -> dict[str, JourneyBackend]:
    """Each built journey target, keyed by the name D1's table gives it."""

    def bind_http(walk: JourneyWalk) -> BoundJourney | ScenarioRefusal:
        surface = walk.nav.surface
        targets = {api_target(surface, step.ref.split("#", 1)[0], walk.book) for step in walk.steps}
        if len(targets) > 1:
            return ScenarioRefusal(
                "needs-multi-target-runtime",
                "this journey's endpoints answer at "
                + ", ".join(sorted(url or "the surface's own address" for _var, url in targets))
                + " — `@scenario(target=...)` sends every request to one base URL, so a walk "
                  "across two servers fits no scenario. Split the flow at the server it changes to")
        target_var, url = targets.pop() if targets else (target_variable(surface, "api"), None)
        return _bind_at_base_url(target_var, url or walk.nav.entry_url, walk, walkers.http)

    def bind_web(walk: JourneyWalk) -> BoundJourney | ScenarioRefusal:
        url = walk.book.resolved_web_base_urls.get(walk.nav.surface) or walk.nav.entry_url
        return _bind_at_base_url(target_variable(walk.nav.surface, "web"), url, walk, walkers.web)

    def bind_maestro(walk: JourneyWalk) -> BoundJourney | ScenarioRefusal:
        launch = maestro_launch(walk.nav)
        if isinstance(launch, ScenarioRefusal):
            return launch
        return BoundJourney(target_variable(walk.nav.surface, "mobile"), f", app_id={python_literal(launch.bundle_id)}",
                            lambda sinks: walkers.maestro(walk, launch, sinks))

    def bind_cli(walk: JourneyWalk) -> BoundJourney | ScenarioRefusal:
        return BoundJourney(target_variable(walk.nav.surface, "cli"), "", lambda sinks: _cli_walk(walk, sinks))

    return {
        "http": JourneyBackend("api", "python", bind_http),
        "playwright": JourneyBackend("web", "playwright", bind_web),
        "maestro": JourneyBackend("mobile", "maestro", bind_maestro),
        "cli": JourneyBackend("cli", "python", bind_cli),
    }


def journey_target(
    steps: tuple[FlowStep, ...], navigation: dict[str, SurfaceNavigation],
) -> JourneyTarget | ScenarioRefusal:
    """The one target and surface that perform every step, or why no one does."""
    if not steps:
        return ScenarioRefusal(
            "uncompilable-claim",
            "this flow's claim is about what its `steps:` did, and it names no steps to walk. "
            "A step is a `[label](page.md#node)` link to the control, endpoint or command it "
            "performs. A step written as a sentence links nothing, and a link to a screen, "
            "component or field only says where a step happens or what it shows")
    unlinked = sum(1 for step in steps if not step.href)
    if unlinked:
        return ScenarioRefusal(
            "uncompilable-claim",
            f"{unlinked} of this flow's `steps:` entries link no node. A walker performs only "
            "what a step links, so it would skip each such sentence and observe a world the "
            "journey did not reach. Link the interaction, invocation, endpoint or command the "
            "entry performs, or drop an entry that only narrates what the reader sees")
    unresolved = [step.href for step in steps if not step.ref]
    if unresolved:
        return ScenarioRefusal(
            "uncompilable-claim",
            "a `steps:` entry names "
            + ", ".join(repr(href) for href in unresolved)
            + ", which resolves to no node this book declares; a journey walked "
              "one step short observes a world it did not reach")
    pairs: list[JourneyTarget] = []
    for step in steps:
        step_target = dispatch_target(step.node_type, surface_row(navigation, step.surface).driver)
        if isinstance(step_target, ScenarioRefusal):
            return step_target
        pairs.append(JourneyTarget(step_target, step.surface))
    if len(set(pairs)) > 1:
        return ScenarioRefusal(
            "needs-multi-target-runtime",
            "this journey's steps are performed by "
            + ", ".join(f"{pair.target} on {pair.surface!r}"
                        for pair in sorted(set(pairs), key=lambda pair: (pair.target, pair.surface)))
            + " — `@scenario(target=...)` binds one driver to one service, so "
              "there is no scenario shape a journey across two of them fits into. When the "
              "page's own request is what reaches an endpoint named here, make that endpoint "
              "the `on:` of the invocation that sends it. The journey then reads the endpoint "
              "as that invocation's request")
    return pairs[0]


def journey_scenario(
    source: str, target_var: str, ids: list[str], walked: WalkedJourney,
    arranged: list[FixtureRow],
) -> list[str]:
    """The `@scenario` that walks *source*'s steps, arranged and asserted."""
    return [
        "",
        "",
        "@scenario(",
        f"    target={target_var},",
        '    mechanism="live",',
        "    covers=[",
        *(f"        {python_literal(oid)}," for oid in ids if oid in walked.covered),
        "    ],",
        "    preconditions=[",
        *(f"        {python_literal(row.precondition)}," for row in arranged),
        "    ],",
        "    checkpoints=[],  # TODO(arrange): what an observer should see it prove",
        "    forbid=[],  # TODO: the weaker observations this scenario must not settle for",
        ")",
        f"def {python_identifier(source)}_journey(qa: Qa) -> None:",
        f'    """Walk {source}\'s steps in order, then observe what the walk left."""',
        "",
        *(fixture_call(row) for row in arranged),
        *walked.lines,
    ]


@dataclass(frozen=True)
class JourneyPlan:
    """One plan's journeys: what they read, where they record, and who walks each driver."""
    book: BookIndex
    sinks: PlanSinks
    navigation: dict[str, SurfaceNavigation]
    walkers: JourneyWalkers


def journey_scenarios(
    flow_owed: list[Obligation], plan: JourneyPlan, emitted: EmittedScenarios,
) -> list[str]:
    """One scenario per flow: walk its `steps:` in order, then observe what the walk left."""
    backends = _journey_backends(plan.walkers)
    gaps = plan.sinks.gaps
    lines: list[str] = []
    for source, obligations in sorted(by_source(flow_owed).items()):
        ids = sorted(o.id for o in obligations)
        steps = obligations[0].steps
        chosen = journey_target(steps, plan.navigation)
        if isinstance(chosen, ScenarioRefusal):
            gaps.extend(Gap(oid, chosen.kind, chosen.detail) for oid in ids)
            continue
        surface = chosen.surface
        backend = backends.get(chosen.target)
        if backend is None:
            gaps.extend(Gap(oid, "needs-target-backend",
                            f"D1's table names {chosen.target!r} for every step of this "
                            "journey, and this compiler builds no journey path for it")
                        for oid in ids)
            continue
        arrangement = arrangement_of(obligations)
        left_on = plan.book.fixture_screens.get(arrangement.rows[-1].name) if arrangement.rows else None
        walk = JourneyWalk(plan.book, steps, obligations, ids, surface_row(plan.navigation, surface), left_on)
        bound = backend.bind(walk)
        if isinstance(bound, ScenarioRefusal):
            gaps.extend(Gap(oid, bound.kind, bound.detail) for oid in ids)
            continue
        if arrangement.unstated:
            gaps.extend(Gap(oid, "unarranged-journey",
                            "this flow arranges nothing before its walk and does not say it "
                            "needs nothing — add a `fixture:` naming the arrangement, or "
                            "`fixture: none, because ...` saying why the journey's claims hold "
                            "in whatever world it finds")
                        for oid in ids)
            continue
        walked = bound.walk(plan.sinks)
        if not walked.covered:
            continue
        emitted.covered.update(walked.covered)
        lines.extend(target_lines(bound.target_var, backend.driver, bound.target_kwargs, emitted))
        lines.extend(journey_scenario(source, bound.target_var, ids, walked, arrangement.rows))
    return lines


__all__ = [
    "BoundJourney", "JourneyBackend", "JourneyPlan", "JourneyTarget", "JourneyWalk",
    "JourneyWalkers", "WalkedJourney", "api_target", "journey_scenario", "journey_scenarios", "journey_target",
]
