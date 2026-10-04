"""The Playwright builders page scenarios and web journeys share: locators, hops, observations and acts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import get_args as _get_args

from ostler import acts as acts_mod
from ostler.qa.book_index import BookIndex
from ostler.qa.compile_journey import JourneyWalk
from ostler.qa.compile_journey import WalkedJourney
from ostler.qa.compile_support import PLAYWRIGHT
from ostler.qa.compile_support import bullet_value
from ostler.qa.compile_support import check_document
from ostler.qa.compile_support import on_node
from ostler.qa.compile_support import on_label
from ostler.qa.compile_support import trailing_comment
from ostler.qa.compile_support import unobservable_gap
from ostler.qa.compile_support import vet_calls
from ostler.qa.navigation import NavHop
from ostler.qa.obligation import CallRow
from ostler.qa.obligation import FlowStep
from ostler.qa.obligation import Locators
from ostler.qa.obligation import NO_LOCATORS
from ostler.qa.obligation import Obligation
from ostler.qa.plan_source import Gap
from ostler.qa.plan_source import PlanSinks
from ostler.qa.plan_source import call_kwargs
from ostler.qa.plan_source import check_observes
from ostler.qa.plan_source import decline_captures
from ostler.qa.plan_source import file_refusal
from ostler.qa.plan_source import out_of_band
from ostler.qa.plan_source import python_literal
from ostler import selector_forms



try:
    from playwright._impl._api_structures import AriaRole as _AriaRole
    _MATCHABLE_ROLES: frozenset[str] | None = frozenset(_get_args(_AriaRole)) - {
        "generic", "none", "presentation",
    }
except ImportError:
    _MATCHABLE_ROLES = None


def page_locator_expr(locators: Locators) -> str | None:
    """A concrete Playwright locator expression built from a node's own book-declared locators."""
    role = bullet_value(next(iter(locators.role), None))
    if role is not None and (_MATCHABLE_ROLES is None or role not in _MATCHABLE_ROLES):
        role = None
    name = bullet_value(next(iter(locators.name), None))
    selector = bullet_value(next(iter(locators.selector), None))
    if role and name:
        return f"qa.by_role({python_literal(role)}, name={python_literal(name)})"
    if selector:
        if selector_forms.parse_scheme_selector(selector) is not None:
            return None
        return f"qa.by_css({python_literal(selector)})"
    return None


_ACT_METHODS: dict[str, tuple[str, str | None]] = {
    "fill": ("fill", "value"),
    "click": ("click", None),
    "press": ("press", "key"),
    "select": ("select_option", "option"),
}


@dataclass(frozen=True)
class PerformedActs:
    """The calls that perform a node's acts, `None` when one cannot be performed, and whether that refusal filed its own gap."""
    lines: list[str] | None
    gap_filed: bool = False


def perform_acts(
    rows: list[CallRow], driver: str, gaps: list[Gap], ids: list[str]
) -> PerformedActs:
    """The calls that perform *rows* in order, with no lines if any one of them cannot be performed."""
    lines: list[str] = []
    for row in rows:
        spec = acts_mod.ACT_BY_NAME.get(row.name)
        if spec is None or driver not in spec.drivers:
            return PerformedActs(None)
        located = row.locates.get("locator")
        expr = page_locator_expr(located.locators if located else NO_LOCATORS)
        if expr is None:
            return PerformedActs(None)
        if driver == acts_mod.WEB and spec.name == "press":
            book_key = row.text_arg("key")
            if any(ch.isspace() for ch in book_key):
                gaps.extend(Gap(oid, "uncompilable-claim",
                                f"`press` names key {book_key!r}, which contains whitespace "
                                "and so is not a Playwright key")
                            for oid in ids)
                return PerformedActs(None, gap_filed=True)
        method, value_param = _ACT_METHODS[spec.name]
        argument = "" if value_param is None else python_literal(row.args.get(value_param, ""))
        lines.append(f"    {expr}.{method}({argument})  # arrange: {row.call}")
    return PerformedActs(lines)


def walk_hops(
    hops: tuple[NavHop, ...],
    destination: str,
    book: BookIndex,
    gaps: list[Gap],
    oids: list[str],
) -> list[str]:
    """One `.click()` per hop on the way to *destination*, after the acts the book says that click needs to land there."""
    lines: list[str] = []
    for index, hop in enumerate(hops):
        target_node = hop.node
        expr = page_locator_expr(book.locators_by_node.get(target_node, NO_LOCATORS))
        if expr is None:
            lines.append(f"    # TODO(arrange): no locator declared for {target_node!r}"
                         f" ({hop.label!r})")
            gaps.extend(Gap(oid, "unresolved-precondition",
                             f"no locator declared for navigation hop {target_node!r}", target_node)
                        for oid in oids)
            continue
        lands_on = hops[index + 1].from_page if index + 1 < len(hops) else destination
        needed = perform_acts(book.hop_acts.get((target_node, lands_on), []), acts_mod.WEB, gaps, oids)
        lines.extend(needed.lines or [])
        lines.append(f"    {expr}.click()  # {trailing_comment(hop.label)}")
    return lines


def _assertion_operand(locators: Locators, oid: str, gaps: list[Gap]) -> str | None:
    """The concrete operand a `visible(...)` assertion is handed — never a page/body fallback."""
    expr = page_locator_expr(locators)
    if expr is None:
        gaps.append(Gap(oid, "uncompilable-claim",
                         "no addressable role/name or selector locator for this obligation's "
                         "`visible(...)` assertion"))
        return None
    return expr


def _check_operand(
    row: CallRow, obligation: Obligation, gaps: list[Gap]
) -> str | None:
    """Where the driver is pointed for one `verify:` row."""
    located = row.locates
    if not located:
        return _assertion_operand(obligation.locators, obligation.id, gaps)
    param = sorted(located)[0]
    target = located[param]
    node_id = target.node
    if not node_id:
        gaps.append(Gap(
            obligation.id, "undeclared-check-locator",
            f"`{row.name}` points `{param}=` at "
            f"`{row.args.get(param)}`, which names no component or interaction this "
            f"book declares — there is nothing to point a driver at, so nothing is emitted"))
        return None
    expr = page_locator_expr(target.locators)
    if expr is None:
        gaps.append(Gap(
            obligation.id, "uncompilable-claim",
            f"`{node_id}` is what `{param}=` names, and it declares no role/name pair and no "
            f"selector — so the book says what to look at and not how to address it"))
        return None
    return expr


WINDOW_VAR = "exchanges"


def _observed_exchange(obligation: Obligation) -> tuple[str | None, str] | None:
    """Which HTTP exchange this obligation's response/body checks are about, if the book says."""
    pairs = {
        (row.args.get("method"), row.text_arg("path"))
        for row in obligation.checks
        if row.name == "http_status" and isinstance(row.args.get("path"), str)
    }
    if len(pairs) != 1:
        return None
    method, path = next(iter(pairs))
    return (str(method) if isinstance(method, str) else None, path)


def _exchange_operand(
    row: CallRow, obligation: Obligation, exchange: tuple[str | None, str] | None,
    channel: str, gaps: list[Gap],
) -> str | None:
    """Where a page scenario is pointed for one response- or body-observing `verify:` row."""
    if exchange is None:
        gaps.append(Gap(
            obligation.id, "uncompilable-claim",
            f"`{row.name}` observes an HTTP {channel}, which the playwright driver "
            "can see — but a browser makes many requests and nothing in this obligation "
            "says which one, uniquely, by method and path. Declare the exchange with an "
            "`http_status(method=\"…\", path=\"…\")` bullet on the same claim; two different "
            "(method, path) pairs on one obligation are two claims, not one"))
        return None
    method, path = exchange
    args = f"{python_literal(path)}, method={python_literal(method)}" if method else python_literal(path)
    selection = f"{WINDOW_VAR}.response_for({args})"
    return f"{selection}.json()" if channel == "body" else selection


def needs_window(lines: list[str]) -> bool:
    """Whether any emitted assertion reads the observation window, so it has to be opened."""
    return any(f"{WINDOW_VAR}." in line for line in lines)


def _page_assertions(
    obligation: Obligation, gaps: list[Gap]
) -> tuple[list[str], list[str]] | None:
    """One obligation's assertions and the screens they observe, or `None` if it is not whole."""
    lines: list[str] = []
    documents: list[str] = []
    whole = True
    exchange = _observed_exchange(obligation)
    for row in obligation.checks:
        channel = check_observes(row.name)
        if "file" in row.args:
            refusal = file_refusal(row.name)
            gaps.append(Gap(obligation.id, refusal.kind, refusal.detail, refusal.owner))
            whole = False
            continue
        if channel in {"response", "body"} and not out_of_band(row.name):
            operand = _exchange_operand(row, obligation, exchange, channel, gaps)
            if operand is None:
                whole = False
                continue
            lines.append(
                f"    qa.verify({python_literal(row.name)}, {operand}"
                f"{call_kwargs(row.args)}, "
                f"covers=[{python_literal(obligation.id)}])"
            )
            continue
        if channel not in {"page", "keyboard"}:
            gaps.append(unobservable_gap(obligation.id, row.name, PLAYWRIGHT))
            whole = False
            continue
        operand = _check_operand(row, obligation, gaps)
        if operand is None:
            whole = False
            continue
        document = check_document(row, obligation)
        if document and document not in documents:
            documents.append(document)
        lines.append(
            f"    qa.verify({python_literal(row.name)}, {operand}"
            f"{call_kwargs(row.args)}, "
            f"covers=[{python_literal(obligation.id)}])"
        )
    if not whole:
        return None
    return lines, documents


@dataclass(frozen=True)
class PageObservations:
    """What a page scenario asserts: the lines, the claims they cover, and the screens they observe."""
    lines: list[str]
    covered: set[str]
    documents: list[str]


def page_observations(
    obligations: list[Obligation], gaps: list[Gap], *, scenario: str = "scenario",
) -> PageObservations:
    """Every obligation's assertions, with a TODO in place of each one that is not whole."""
    observed = PageObservations([], set(), [])
    for obligation in obligations:
        compiled = _page_assertions(obligation, gaps)
        if compiled is None:
            observed.lines.append(f"    # TODO(arrange): {obligation.id} declares an "
                                  f"observation this {scenario} cannot make")
            continue
        observed.lines.extend(compiled[0])
        observed.documents.extend(document for document in compiled[1]
                                  if document not in observed.documents)
        observed.covered.add(obligation.id)
    return observed


def _web_start(walk: JourneyWalk, gaps: list[Gap]) -> list[str] | None:
    """Open the surface's root and click through to where the journey's first step lives."""
    first_source = walk.steps[0].ref.split("#")[0]
    hops = walk.nav.routes.get(first_source)
    if hops is None:
        gaps.extend(Gap(oid, "uncompilable-claim",
                        f"no route computed to {first_source!r}, where this journey's first "
                        "step lives")
                    for oid in walk.ids)
        return None
    opened = walk.nav.path_to(first_source)
    if opened is None:
        gaps.extend(Gap(oid, "uncompilable-claim",
                        "this surface states no root path a journey can open from")
                    for oid in walk.ids)
        return None
    return [f"    qa.goto({python_literal(opened)})",
            *walk_hops(hops, first_source, walk.book, gaps, walk.ids)]


def _web_step(index: int, step: FlowStep, walk: JourneyWalk, gaps: list[Gap]) -> list[str] | None:
    """Arrange and click one `interaction` step, or `None` once the journey cannot go on."""
    book, ids = walk.book, walk.ids
    node_type = step.node_type
    if node_type != "interaction":
        gaps.extend(Gap(oid, "uncompilable-claim",
                        f"step {index} names a {node_type or 'untyped'} node, which is a "
                        "place rather than an action; this builder performs only "
                        "`interaction` steps")
                    for oid in ids)
        return None
    ref = step.ref
    locators = book.locators_by_node.get(ref, NO_LOCATORS)
    on_value = next(iter(locators.on), "")
    trigger_value = next(iter(locators.trigger), "")
    on_node_id = on_node(ref.split("#")[0], on_value)
    expr = page_locator_expr(book.locators_by_node.get(on_node_id, NO_LOCATORS))
    if expr is None:
        gaps.extend(Gap(oid, "uncompilable-claim",
                        f"step {index} acts on {on_label(on_value)!r}, which declares no role/name "
                        "pair and no selector to address it by; every step after it would "
                        "run in a world this journey never reached")
                    for oid in ids)
        return None
    performed = perform_acts(book.acts_by_node.get(ref, []), acts_mod.WEB, gaps, ids)
    if performed.lines is None or ref in book.acts_refused:
        if not performed.gap_filed:
            gaps.extend(Gap(oid, "uncompilable-claim",
                            f"step {index} declares an arrangement this journey cannot make — "
                            "an act with no driver or no addressable subject, or a bullet the "
                            "act parser refused; every step after it would run in a world this "
                            "journey never reached")
                        for oid in ids)
        return None
    return [*performed.lines, f"    {expr}.click()  # step {index}: {trailing_comment(trigger_value)}"]


def web_walk(walk: JourneyWalk, sinks: PlanSinks) -> WalkedJourney:
    """Arrive where the journey starts, click every step in order, then observe the end."""
    gaps = sinks.gaps
    decline_captures(walk.obligations, gaps, sinks.captured, because=(
        "a journey performs its steps and asserts the flow's own claim; a step's capture is "
        "emitted where that step's own obligation is compiled, not restated here"))
    unwalked = WalkedJourney([], frozenset())
    lines = _web_start(walk, gaps)
    if lines is None:
        return unwalked
    action_index = len(lines)
    for index, step in enumerate(walk.steps, start=1):
        performed = _web_step(index, step, walk, gaps)
        if performed is None:
            return unwalked
        lines.extend(performed)
    observed = page_observations(walk.obligations, gaps, scenario="journey")
    if not observed.covered:
        return unwalked
    if needs_window(observed.lines):
        lines.insert(action_index, f"    {WINDOW_VAR} = qa.window()")
    return WalkedJourney([
        *lines,
        *vet_calls(observed.documents, walk.book.screen_routes, walk.ids, gaps),
        *observed.lines,
    ], frozenset(observed.covered))
