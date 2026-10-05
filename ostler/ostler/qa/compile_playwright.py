"""The Playwright builders page scenarios and web journeys share: locators, hops, observations and acts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import get_args as _get_args

from ostler import accessible_names
from ostler import acts as acts_mod
from ostler.checks import Call
from ostler.checks import parse_call
from ostler.qa.book_index import BookIndex
from ostler.qa.compile_journey import JourneyWalk
from ostler.qa.compile_journey import WalkedJourney
from ostler.qa.compile_support import PLAYWRIGHT
from ostler.qa.compile_support import bullet_value
from ostler.qa.compile_support import check_document
from ostler.qa.compile_support import on_node
from ostler.qa.compile_support import on_label
from ostler.qa.compile_support import shown_on
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
from ostler.qa.plan_source import ScenarioRefusal
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
    if role and name and not accessible_names.prose_mark(name):
        return f"qa.by_role({python_literal(role)}, name={python_literal(accessible_names.literal_name(name))})"
    if selector:
        if selector_forms.parse_scheme_selector(selector) is not None:
            return None
        return f"qa.by_css({python_literal(selector)})"
    return None


def name_refusal(locators: Locators) -> str:
    """Why a node's `name:` could not address it, as a sentence for a gap, or `""`."""
    name = bullet_value(next(iter(locators.name), None))
    mark = accessible_names.prose_mark(name) if name else ""
    if not mark:
        return ""
    return (f". Its `name:` {name!r} carries {mark}, so it describes the accessible name "
            "instead of stating the one string a browser computes, and `getByRole` would wait "
            "for that description and time out. State the literal name, one value per node. "
            "A control rendered once per item declares `one-per:` and names itself with a "
            "template over the item, such as `{tab.label}`")


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
        act_locators = located.locators if located else NO_LOCATORS
        expr = page_locator_expr(act_locators)
        if expr is None:
            refusal = name_refusal(act_locators)
            if not refusal:
                return PerformedActs(None)
            gaps.extend(Gap(oid, "uncompilable-claim", f"`{row.call}` cannot be performed{refusal}")
                        for oid in ids)
            return PerformedActs(None, gap_filed=True)
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


TRIGGER_ACTS: dict[str, str] = {"fill": "value", "press": "key"}


def trigger_name(raw: str) -> str:
    """The act a `trigger:` names: its bare word, or the name of the call it is written as."""
    value = bullet_value(raw) or ""
    parsed = parse_call(value)
    return (parsed.name if parsed is not None else value).lower()


def trigger_performance(raw: str, on_expr: str) -> str | ScenarioRefusal:
    """The line that performs a `fill(value=…)` or `press(key=…)` trigger on *on_expr*, or why the book's spelling of it cannot be performed."""
    name = trigger_name(raw)
    param = TRIGGER_ACTS[name]
    parsed = parse_call(bullet_value(raw) or "")
    argument: object = None
    if isinstance(parsed, Call) and set(parsed.keywords) <= {param}:
        if parsed.keywords and not parsed.positional:
            argument = parsed.keywords[param]
        elif len(parsed.positional) == 1 and not parsed.keywords:
            argument = parsed.positional[0]
    example = "Escape" if name == "press" else "…"
    if not isinstance(argument, str) or not argument:
        return ScenarioRefusal("uncompilable-claim",
                               f"trigger {raw!r} does not say what to {name}: write "
                               f'`trigger: {name}({param}="{example}")`, the {param} the user sends '
                               "to the `on:` control, which is the control it acts on")
    if name == "press" and any(ch.isspace() for ch in argument):
        return ScenarioRefusal("uncompilable-claim",
                               f"trigger `press` names key {argument!r}, which contains whitespace "
                               "and so is not a Playwright key")
    method, _ = _ACT_METHODS[name]
    return f"    {on_expr}.{method}({python_literal(argument)})  # trigger: {trailing_comment(raw)}"


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
        hop_locators = book.locators_by_node.get(target_node, NO_LOCATORS)
        expr = page_locator_expr(hop_locators)
        if expr is None:
            lines.append(f"    # TODO(arrange): no locator declared for {target_node!r}"
                         f" ({hop.label!r})")
            gaps.extend(Gap(oid, "unresolved-precondition",
                             f"no locator declared for navigation hop {target_node!r}"
                             f"{name_refusal(hop_locators)}", target_node)
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
                         f"`visible(...)` assertion{name_refusal(locators)}"))
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
            f"selector — so the book says what to look at and not how to address it"
            f"{name_refusal(target.locators)}"))
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


REQUEST_EVENT = re.compile(r"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) +(/[^\s?#]*)", re.IGNORECASE)


def _request_operand(row: CallRow, obligation: Obligation, gaps: list[Gap]) -> str | None:
    """The requests an `emitted(event="METHOD /path")` row counts inside the window, or `None` with the gap filed."""
    event = row.text_arg("event").strip()
    spelled = REQUEST_EVENT.fullmatch(event)
    if spelled is None:
        gaps.append(Gap(
            obligation.id, "uncompilable-claim",
            f"`emitted(event={event!r})` names no request this driver can count. The playwright driver "
            "sees every request the page sends, so spell the event as the request: "
            "`emitted(event=\"POST /v1/items/{id}\", count=1)`, with each `{name}` standing for one "
            "path segment, and `count=0` for a request the page must not send"))
        return None
    method, path = spelled.groups()
    return f"{WINDOW_VAR}.requests_to({python_literal(path)}, method={python_literal(method.upper())})"


def _browser_operand(row: CallRow, obligation: Obligation, channel: str | None, gaps: list[Gap]) -> str | None:
    """Where a page scenario is pointed for a row that reads the page's title, console or requests."""
    if channel == "title":
        return "qa.browser_page"
    if channel == "console":
        return f"{WINDOW_VAR}.console()"
    return _request_operand(row, obligation, gaps)


BROWSER_READS = frozenset({"title", "console"})


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
        browser_read = channel in BROWSER_READS or row.name == "emitted"
        if browser_read or channel in {"response", "body"} and not out_of_band(row.name):
            operand = (_browser_operand(row, obligation, channel, gaps) if browser_read
                       else _exchange_operand(row, obligation, exchange, str(channel), gaps))
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
    first_source = shown_on(walk.steps[0].ref.split("#")[0], walk.nav.routes, walk.book.fragment_hosts)
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
    on_locators = book.locators_by_node.get(on_node_id, NO_LOCATORS)
    expr = page_locator_expr(on_locators)
    if expr is None:
        gaps.extend(Gap(oid, "uncompilable-claim",
                        f"step {index} acts on {on_label(on_value)!r}, which declares no role/name "
                        "pair and no selector to address it by; every step after it would "
                        f"run in a world this journey never reached{name_refusal(on_locators)}")
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
    if trigger_name(trigger_value) in TRIGGER_ACTS:
        action = trigger_performance(trigger_value, expr)
        if isinstance(action, ScenarioRefusal):
            gaps.extend(Gap(oid, action.kind, f"step {index}: {action.detail}") for oid in ids)
            return None
        return [*performed.lines, action]
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
        *vet_calls(observed.documents, walk.book.screen_routes, walk.ids, gaps, walk.book.fragment_hosts),
        *observed.lines,
    ], frozenset(observed.covered))
