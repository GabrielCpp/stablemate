"""The mobile half of `compile-plan`: each owed screen claim and each journey as a Maestro flow."""

from __future__ import annotations

import itertools
import json
import re
from collections.abc import Iterator
from collections.abc import Mapping
from dataclasses import dataclass

import yaml

from ostler import accessible_names
from ostler import acts as acts_mod
from ostler.checks import CheckValue
from ostler.qa import references
from ostler.qa.book_index import BookIndex
from ostler.qa.compile_journey import JourneyWalk
from ostler.qa.compile_journey import WalkedJourney
from ostler.qa.compile_stops import ScreenStop
from ostler.qa.compile_stops import expand_steps
from ostler.qa.compile_stops import resolve_state
from ostler.qa.compile_stops import resolve_stop
from ostler.qa.compile_support import MAESTRO
from ostler.qa.compile_support import name_refusal
from ostler.qa.compile_support import bullet_value
from ostler.qa.compile_support import check_document
from ostler.qa.compile_support import on_node
from ostler.qa.compile_support import on_label
from ostler.qa.compile_support import shown_on
from ostler.qa.compile_support import trailing_comment
from ostler.qa.compile_support import unarranged_scenario_gap
from ostler.qa.compile_support import unarranged_state_gap
from ostler.qa.compile_support import unarranged_state_walk_gap
from ostler.qa.compile_support import unobservable_gap
from ostler.qa.compile_support import vettable
from ostler.qa.navigation import MaestroLaunch
from ostler.qa.navigation import NavHop
from ostler.qa.navigation import SurfaceNavigation
from ostler.qa.navigation import fixture_launch
from ostler.qa.navigation import maestro_launch
from ostler.qa.navigation import surface_row
from ostler.qa.obligation import CallRow
from ostler.qa.obligation import Locators
from ostler.qa.obligation import NO_LOCATORS
from ostler.qa.obligation import Obligation
from ostler.qa.plan_source import EmittedScenarios
from ostler.qa.plan_source import Gap
from ostler.qa.plan_source import PlanSinks
from ostler.qa.plan_source import ScenarioRefusal
from ostler.qa.plan_source import SourceScenario
from ostler.qa.plan_source import arrangement_of
from ostler.qa.plan_source import by_source
from ostler.qa.plan_source import claim_scenario_function_name
from ostler.qa.plan_source import call_kwargs
from ostler.qa.plan_source import check_observes
from ostler.qa.plan_source import decline_captures
from ostler.qa.plan_source import operand_for
from ostler.qa.plan_source import python_identifier
from ostler.qa.plan_source import python_literal
from ostler.qa.plan_source import scenario_lines
from ostler.qa.plan_source import state_walk_function_name
from ostler.qa.plan_source import target_lines
from ostler.qa.plan_source import target_variable
from ostler.qa.plan_source import typed_literal
from ostler import selector_forms
from ostler.qa.harness_host import load_harness_module


MaestroLocator = tuple[str, str]

_ELEMENTS = load_harness_module("ostler_qa_elements")
_HOLE = re.compile(r"\$?\{[^{}]*\}")
_VARIABLE = re.compile(r"\$\{OKF_REF_(\d+)\}")
_QUOTED = re.compile(r"\\Q.*?\\E", re.DOTALL)


class _Refs:
    """The values a flow hands Maestro as variables, each kept as the Python expression the scenario evaluates for it."""

    def __init__(self) -> None:
        self._expressions: list[str] = []

    def bind(self, expression: str) -> str:
        """The variable that stands for *expression* in a flow's text."""
        if expression not in self._expressions:
            self._expressions.append(expression)
        return "${OKF_REF_%d}" % len(self._expressions)

    def numbered(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """*text* with its variables numbered from 1 in order of appearance, and the `(name, expression)` of each."""
        order: list[str] = []
        for found in _VARIABLE.finditer(text):
            if found.group(1) not in order:
                order.append(found.group(1))
        names = {each: f"OKF_REF_{at}" for at, each in enumerate(order, start=1)}
        renamed = _VARIABLE.sub(lambda found: "${" + names[found.group(1)] + "}", text)
        return renamed, [(names[each], self._expressions[int(each) - 1]) for each in order]


def maestro_locator(locators: Locators) -> MaestroLocator | None:
    """A `(Maestro selector key, value)` pair built from a node's own book-declared locators."""
    selector = bullet_value(next(iter(locators.selector), None))
    if selector:
        parsed = selector_forms.parse_scheme_selector(selector)
        if parsed is not None and parsed[0] == "testID":
            return "id", parsed[1]
    name = bullet_value(next(iter(locators.name), None))
    if name and not name_refusal(locators):
        literal = accessible_names.literal_name(name)
        if literal:
            return "text", literal
    return None


def _flow_yaml(
    commands: list[str], launch: MaestroLaunch, refs: _Refs, *, first: bool = True,
) -> tuple[str, str]:
    """One Maestro flow file and the `env=` argument that runs it: the app, then, in the first file of a scenario, a cold launch that clears the device unless a fixture signed it in, then *commands* in order."""
    opening = [] if not first else ["- launchApp"] if launch.signed_in else ["- launchApp:", "    clearState: true"]
    if first:
        commands = _drawn_first(commands)
    text = "\n".join([f"appId: {json.dumps(launch.bundle_id)}", "---", *opening, *commands]) + "\n"
    text, variables = refs.numbered(text)
    if any(references.find_references(each) or _HOLE.search(each) for each in _unquoted(text)):
        raise ValueError(f"a Maestro flow still holds an unrendered book value:\n{text}")
    env = ", ".join(f"{json.dumps(name)}: {expression}" for name, expression in variables)
    return text, f", env={{{env}}}" if env else ""


def _unquoted(flow: str) -> Iterator[str]:
    """Each string of *flow* with its variables and its regex-quoted literals cut out: what is left reached the flow without being rendered."""
    pending: list[object] = list(yaml.safe_load_all(flow))
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            pending.extend([*node.keys(), *node.values()])
        elif isinstance(node, list):
            pending.extend(node)
        elif isinstance(node, str):
            yield _QUOTED.sub("", _VARIABLE.sub("", node))


_PRESS_KEYS: frozenset[str] = frozenset({
    "home", "lock", "enter", "backspace", "volume up", "volume down", "back", "power", "tab",
    "Remote Dpad Up", "Remote Dpad Down", "Remote Dpad Left", "Remote Dpad Right",
    "Remote Dpad Center", "Remote Media Play Pause", "Remote Media Stop", "Remote Media Next",
    "Remote Media Previous", "Remote Media Rewind", "Remote Media Fast Forward",
    "Remote System Navigation Up", "Remote System Navigation Down", "Remote Button A",
    "Remote Button B", "Remote Menu", "TV Input", "TV Input HDMI 1", "TV Input HDMI 2",
    "TV Input HDMI 3",
})
_PRESS_KEYS_BY_NORMAL: dict[str, str] = {
    " ".join(key.casefold().split()): key for key in _PRESS_KEYS
}


def maestro_press_key(key: str) -> str | None:
    """*key*, canonicalized to Maestro's own documented spelling, or `None` if it names no `pressKey` key at all under that normalization."""
    normal = " ".join(key.casefold().split())
    return _PRESS_KEYS_BY_NORMAL.get(normal)


def _scalar(value: str, refs: _Refs) -> str:
    """*value* as a YAML scalar, or as the variable the scenario fills with it once it holds a reference."""
    if references.find_references(value):
        return json.dumps(refs.bind(typed_literal(value)))
    return json.dumps(value)


def _selector(
    locator: MaestroLocator, text: str | None, refs: _Refs, indent: str,
) -> list[str]:
    """The mapping lines that address the control at *locator*, holding *text* when given: one `text:` key, a regex that reads the book's value the way the browser driver does."""
    key, value = locator
    name = "" if key == "id" else value
    lines = [f"{indent}id: {json.dumps(value)}"] if key == "id" else []
    if key == "id" and text is None:
        return lines
    if any(references.find_references(each) for each in (name, text or "")):
        arguments = [typed_literal(name)] if name else []
        if text is not None:
            arguments.append(f"text={typed_literal(text)}")
        pattern = json.dumps(refs.bind(f"qa.maestro.pattern({', '.join(arguments)})"))
    else:
        pattern = json.dumps(_ELEMENTS.maestro_pattern(name, text=text))
    return [*lines, f"{indent}text: {pattern}"]


def _into_view(locator: MaestroLocator, text: str | None, refs: _Refs) -> list[str]:
    """The scroll that brings the control at *locator* onto the screen: Maestro sees only what is drawn, where a browser driver scrolls to a control by itself."""
    return [
        "- scrollUntilVisible:", "    element:", *_selector(locator, text, refs, "      "),
        "    direction: DOWN",
    ]


_DRAW_TIMEOUT_MS = 15000


def _drawn_first(commands: list[str]) -> list[str]:
    """*commands*, their first scroll after launch waiting for its control to be drawn: Maestro's launch returns before the app's first frame, and an absence reads as below the fold only once the screen has drawn."""
    if commands[:2] != ["- scrollUntilVisible:", "    element:"]:
        return commands
    selector = list(itertools.takewhile(lambda line: line.startswith("      "), commands[2:]))
    wait = ["- extendedWaitUntil:", "    visible:", *selector, f"    timeout: {_DRAW_TIMEOUT_MS}", "    optional: true"]
    return [*wait, *commands]


def _act_commands(
    act_name: str, locator: MaestroLocator, args: Mapping[str, CheckValue], refs: _Refs,
) -> list[str]:
    """The Maestro commands that perform act *act_name* on the control at *locator*."""
    tap = [*_into_view(locator, None, refs), "- tapOn:", *_selector(locator, None, refs, "    ")]
    if act_name == "fill":
        return [*tap, f"- inputText: {_scalar(str(args.get('value', '')), refs)}"]
    if act_name == "press":
        return [*tap, f"- pressKey: {json.dumps(str(args.get('key', '')))}"]
    return tap


def _check_commands(
    check_name: str, locator: MaestroLocator, args: Mapping[str, CheckValue], refs: _Refs,
) -> list[str]:
    """The Maestro assertion that observes check *check_name* on the control at *locator*."""
    if check_name == "hidden":
        return ["- assertNotVisible:", *_selector(locator, None, refs, "    ")]
    text = args.get("text")
    held = text if check_name == "visible" and isinstance(text, str) else None
    block = [*_into_view(locator, held, refs), "- assertVisible:", *_selector(locator, held, refs, "    ")]
    if check_name == "actionable":
        block.append("    enabled: true")
    elif check_name == "inert":
        block.append("    enabled: false")
    return block


def _act_locator(row: CallRow) -> MaestroLocator | None:
    """The control an act's `locator=` argument resolved to, addressed for Maestro."""
    located = row.locates.get("locator")
    return maestro_locator(located.locators if located else NO_LOCATORS)


def _check_locator(row: CallRow, obligation: Obligation, gaps: list[Gap]) -> MaestroLocator | None:
    """The `(id|text, value)` pair a `page`-channel check's `verify:` row addresses."""
    oid = obligation.id
    if not row.locates:
        locator = maestro_locator(obligation.locators)
        if locator is None:
            gaps.append(Gap(oid, "uncompilable-claim",
                             f"`{row.name}` declares no `locator=` and this obligation's "
                             "own node states no `testID=` selector and no `name:` to fall back "
                             f"on{name_refusal(obligation.locators)}"))
        return locator
    param = sorted(row.locates)[0]
    target = row.locates[param]
    if not target.node:
        gaps.append(Gap(
            oid, "undeclared-check-locator",
            f"`{row.name}` points `{param}=` at "
            f"`{row.args.get(param)}`, which names no component or interaction this "
            "book declares — there is nothing to point a driver at, so nothing is emitted"))
        return None
    locator = maestro_locator(target.locators)
    if locator is None:
        gaps.append(Gap(
            oid, "uncompilable-claim",
            f"`{target.node}` is what `{param}=` names, and it declares no `testID=` selector and "
            "no `name:` — so the book says what to look at and not how to address it"
            f"{name_refusal(target.locators)}"))
    return locator


def _on_locator(
    source: str, on_value: str, locators_by_node: dict[str, Locators],
) -> MaestroLocator | None:
    """The Maestro locator of the node an `on:` bullet on *source* points at."""
    return maestro_locator(locators_by_node.get(on_node(source, on_value), NO_LOCATORS))


@dataclass(frozen=True)
class UnaddressedHop:
    """The first hop on a route that no locator lets the mobile driver tap."""
    label: str
    refusal: str = ""


def _hop_commands(
    hops: tuple[NavHop, ...], locators_by_node: dict[str, Locators], refs: _Refs,
) -> list[str] | UnaddressedHop:
    """One `tapOn` per navigation hop from the launch screen, or the first hop no locator addresses."""
    commands: list[str] = []
    for hop in hops:
        locators = locators_by_node.get(hop.node, NO_LOCATORS)
        on_value = next(iter(locators.on), None)
        locator = None
        refusal = ""
        if on_value is not None:
            locator = _on_locator(hop.from_page, on_value, locators_by_node)
            refusal = name_refusal(locators_by_node.get(on_node(hop.from_page, on_value), NO_LOCATORS))
        locator = locator or maestro_locator(locators)
        if locator is None:
            return UnaddressedHop(hop.label or hop.node, refusal or name_refusal(locators))
        commands.extend(_act_commands("click", locator, {}, refs))
    return commands


def _reach_commands(
    page: str, launch: MaestroLaunch, locators_by_node: dict[str, Locators], refs: _Refs,
) -> list[str] | ScenarioRefusal:
    """The taps that reach *page* from a cold launch, or why the book gives no way there."""
    hops = () if page == launch.launch_screen else launch.routes.get(page)
    if hops is None:
        return ScenarioRefusal(
            "unreachable-from-launch",
            f"a cold `launchApp` opens on {launch.launch_screen!r}, not {page!r}, and no "
            "navigation path in the book gets from the one to the other",
        )
    hop_commands = _hop_commands(hops, locators_by_node, refs)
    if isinstance(hop_commands, UnaddressedHop):
        return ScenarioRefusal(
            "unresolved-precondition",
            f"navigation hop {hop_commands.label!r} from {launch.launch_screen!r} declares no "
            f"`testID=` selector and no `name:` for the mobile driver to tap{hop_commands.refusal}",
        )
    return hop_commands


def _act_command_lines(obligation: Obligation, gaps: list[Gap], refs: _Refs) -> list[str] | None:
    """The Maestro commands that perform *obligation*'s declared acts, or `None` after a gap."""
    commands: list[str] = []
    for row in obligation.acts:
        spec = acts_mod.ACT_BY_NAME.get(row.name)
        if spec is None or acts_mod.MOBILE not in spec.drivers:
            gaps.append(Gap(obligation.id, "uncompilable-claim",
                             f"`{row.name}` arranges this obligation's interaction "
                             "and the mobile driver cannot perform it"))
            return None
        locator = _act_locator(row)
        if locator is None:
            located = row.locates.get("locator")
            gaps.append(Gap(obligation.id, "uncompilable-claim",
                             f"`{row.name}` points at a subject with no `testID=` "
                             "selector and no `name:` for the mobile driver to address"
                             f"{name_refusal(located.locators if located else NO_LOCATORS)}"))
            return None
        if spec.name == "fill":
            typed = str(row.args.get("value", ""))
            if _HOLE.search(typed) or "${" in typed:
                gaps.append(Gap(obligation.id, "uncompilable-claim",
                                 f"`fill` types {typed!r}, which holds a template hole or a "
                                 "`${`, so there is no one text the mobile driver can type for it"))
                return None
        act_args: Mapping[str, CheckValue] = row.args
        if spec.name == "press":
            book_key = row.text_arg("key")
            canonical_key = maestro_press_key(book_key)
            if canonical_key is None:
                gaps.append(Gap(obligation.id, "uncompilable-claim",
                                 f"`press` names key {book_key!r}, which is not one of "
                                 "Maestro's `pressKey` keys"))
                return None
            act_args = {**row.args, "key": canonical_key}
        commands.extend(_act_commands(spec.name, locator, act_args, refs))
    return commands


def _trigger_tap_commands(
    obligation: Obligation, locators_by_node: dict[str, Locators], gaps: list[Gap], refs: _Refs,
) -> list[str] | None:
    """The tap on *obligation*'s `on:` control, when it names one, or `None` after a gap."""
    on_value = next(iter(obligation.locators.on), None)
    if on_value is None:
        return []
    on_locator = _on_locator(obligation.source, on_value, locators_by_node)
    if on_locator is None:
        gaps.append(Gap(obligation.id, "uncompilable-claim",
                         f"`on:` names {on_label(on_value)!r}, which declares no `testID=` "
                         "selector and no `name:` for the mobile driver to address"
                         f"{name_refusal(locators_by_node.get(on_node(obligation.source, on_value), NO_LOCATORS))}"))
        return None
    return _act_commands("click", on_locator, {}, refs)


@dataclass(frozen=True)
class _CompiledCheck:
    """One check compiled against a flow's result: its Maestro assertions, its verdict line, and the screen it observes."""
    assertions: list[str]
    python_line: str
    document: str | None


@dataclass
class _FlowChecks:
    """What one flow's checks compiled to: Maestro assertions, Python verdicts, and the screens observed."""
    assertions: list[str]
    python_lines: list[str]
    documents: list[str]

    def add(self, check: _CompiledCheck) -> None:
        """Fold one compiled check into the flow."""
        self.assertions.extend(check.assertions)
        self.python_lines.append(check.python_line)
        if check.document and check.document not in self.documents:
            self.documents.append(check.document)


def _compiled_check(
    row: CallRow, obligation: Obligation, result_name: str, gaps: list[Gap], refs: _Refs,
) -> _CompiledCheck | None:
    """Compile one of *obligation*'s checks against a flow's result, or `None` after a gap."""
    oid = obligation.id
    channel = check_observes(row.name)
    if channel == "subject":
        operand = operand_for(row.name, result_name, row.args)
        if isinstance(operand, ScenarioRefusal):
            gaps.append(Gap(oid, operand.kind, operand.detail))
            return None
        return _CompiledCheck([], f"    qa.verify({python_literal(row.name)}, {operand}"
                                  f"{call_kwargs(row.args)}, covers=[{python_literal(oid)}])", None)
    if channel != "page":
        gaps.append(unobservable_gap(oid, row.name, MAESTRO))
        return None
    if row.name == "visible" and "count" in row.args:
        gaps.append(Gap(oid, "uncompilable-claim",
                        f"`{row.name}(count=...)` counts the elements a locator matches, and "
                        "Maestro cannot count them: it asserts that one is shown, so no check is "
                        "compiled for the row"))
        return None
    locator = _check_locator(row, obligation, gaps)
    if locator is None:
        return None
    return _CompiledCheck(
        _check_commands(row.name, locator, row.args, refs),
        f"    qa.verify({python_literal(row.name)}, {result_name}"
        f"{call_kwargs(row.args)}, covers=[{python_literal(oid)}])",
        check_document(row, obligation) or None,
    )


def _flow_checks(
    obligation: Obligation, result_name: str, gaps: list[Gap], refs: _Refs,
) -> _FlowChecks | None:
    """Compile *obligation*'s checks against one flow's result, or `None` when any check gapped."""
    compiled = _FlowChecks([], [], [])
    whole = True
    for row in obligation.checks:
        check = _compiled_check(row, obligation, result_name, gaps, refs)
        if check is None:
            whole = False
            continue
        compiled.add(check)
    return compiled if whole else None


def _scenario_body(
    obligations: list[Obligation], book: BookIndex, launch: MaestroLaunch,
    sinks: PlanSinks, covered: set[str],
) -> list[str]:
    """Compile every mobile obligation's own Maestro flow — `cli_scenario_body`'s counterpart for a `mobile`-driven surface instead of a `command` node."""
    lines: list[str] = []
    index = 0
    for obligation in sorted(obligations, key=lambda o: o.doc_position):
        oid = obligation.id
        refs = _Refs()
        reach = _reach_commands(obligation.source, launch, book.locators_by_node, refs)
        if isinstance(reach, ScenarioRefusal):
            sinks.gaps.append(Gap(oid, reach.kind, reach.detail))
            continue
        requirement = " ".join(obligation.requirement.split())
        lines.append("")
        lines.append(f"    # {oid}")
        lines.append(f"    # {requirement}")
        index += 1
        name = f"observed_{index}"
        acted = (_act_command_lines(obligation, sinks.gaps, refs) if obligation.acts
                 else _trigger_tap_commands(obligation, book.locators_by_node, sinks.gaps, refs))
        if acted is None:
            continue
        compiled = _flow_checks(obligation, name, sinks.gaps, refs)
        if compiled is None:
            continue
        commands = [*reach, *acted]
        if not (commands or compiled.assertions or compiled.python_lines):
            continue
        flow_path = f"maestro/{python_identifier(oid)}.yaml"
        sinks.files[flow_path], env = _flow_yaml([*commands, *compiled.assertions], launch, refs)
        lines.append(f"    {name} = qa.maestro.run(qa.spec_dir / {python_literal(flow_path)}{env})")
        lines.extend(compiled.python_lines)
        if compiled.assertions:
            lines.extend(
                f"    qa.vet({python_literal(document)})"
                for document in vettable(compiled.documents, book.screen_routes, [oid], sinks.gaps,
                                         mobile=True, hosts=book.fragment_hosts)
            )
        covered.add(oid)
    return lines


def mobile_scenarios(
    mobile_owed: list[Obligation], book: BookIndex, navigation: dict[str, SurfaceNavigation],
    sinks: PlanSinks, emitted: EmittedScenarios,
) -> list[str]:
    """One scenario per book page whose screens owe live evidence, each run as Maestro flows."""
    declared = [o for o in mobile_owed if o.checks or o.acts]
    sinks.gaps.extend(unarranged_state_gap(o) for o in mobile_owed if not o.checks and not o.acts)
    decline_captures(declared, sinks.gaps, sinks.captured, because=(
        "the mobile builder does not yet capture a fact out of a Maestro flow run"))
    lines: list[str] = []
    for source, obligations in by_source(declared).items():
        arrangement = arrangement_of(obligations)
        if arrangement.unstated:
            sinks.gaps.extend(unarranged_scenario_gap(o) for o in obligations)
            continue
        surface = obligations[0].surface
        launch = maestro_launch(surface_row(navigation, surface))
        if not isinstance(launch, ScenarioRefusal):
            launch = fixture_launch(
                launch, (row.name for o in obligations for row in o.fixtures), book.fixture_launch_screens,
                book.fixture_needs)
        if isinstance(launch, ScenarioRefusal):
            sinks.gaps.extend(Gap(o.id, launch.kind, launch.detail) for o in obligations)
            continue
        covered: set[str] = set()
        body = _scenario_body(obligations, book, launch, sinks, covered)
        if not covered:
            continue
        emitted.covered.update(covered)
        target_var = target_variable(surface, "mobile")
        app_id = f", app_id={python_literal(launch.bundle_id)}"
        lines.extend(target_lines(target_var, MAESTRO.name, app_id, emitted))
        scenario = SourceScenario(
            source, target_var, [o.id for o in obligations if o.id in covered],
            arrangement, body)
        lines.extend(scenario_lines(scenario, claim_scenario_function_name(scenario, emitted)))
    return lines


@dataclass(frozen=True)
class _JourneyTaps:
    """A walk cut at its stops: the taps between them, and the stop that follows each run of taps."""
    segments: list[list[str]]
    stops: list[tuple[int, ScreenStop]]


def _journey_taps(walk: JourneyWalk, gaps: list[Gap], refs: _Refs) -> _JourneyTaps | None:
    """One tap per `interaction` step of a journey, cut at each stop, or `None` after gapping the first step it cannot make."""
    ids, locators_by_node = walk.ids, walk.book.locators_by_node
    taps = _JourneyTaps([[]], [])
    moves = expand_steps(walk, gaps)
    if moves is None:
        return None
    for index, step in ((move.index, move.step) for move in moves):
        if step.node_type == "state":
            stop = resolve_stop(index, step, walk, gaps, device=True)
            if stop is None:
                return None
            taps.stops.append((index, stop))
            taps.segments.append([])
            continue
        if step.node_type != "interaction":
            gaps.extend(Gap(oid, "uncompilable-claim",
                            f"step {index} names a {step.node_type or 'untyped'} node, which is a "
                            "place rather than an action; this builder performs only "
                            "`interaction` steps")
                        for oid in ids)
            return None
        on_value = next(iter(locators_by_node.get(step.ref, NO_LOCATORS).on), None)
        locator = _on_locator(step.ref.split("#")[0], on_value, locators_by_node) if on_value else None
        if locator is None:
            refusal = name_refusal(locators_by_node.get(
                on_node(step.ref.split("#")[0], on_value), NO_LOCATORS)) if on_value else ""
            gaps.extend(Gap(oid, "uncompilable-claim",
                            f"step {index} acts on {on_label(on_value) if on_value else on_value!r}, which "
                            "declares no `testID=` selector and no `name:` to address it by; every "
                            "step after it would run in a world this journey never reached"
                            f"{refusal}")
                        for oid in ids)
            return None
        taps.segments[-1].extend(_act_commands("click", locator, {}, refs))
    return taps


def _settle_lines(stop: ScreenStop, comment: str) -> list[str]:
    """The `qa.settle` call a device walk makes at a stop: the busy sign and the states, with no request feed."""
    return [
        "    qa.settle(",
        f"        {python_literal(stop.node)},",
        f"        busy={python_literal(stop.busy)},",
        f"        states={python_literal(stop.states)},",
        f"        expect={python_literal(stop.expect)},",
        f"        covers={python_literal(list(stop.covers))},",
        f"    )  # {comment}",
    ]


def maestro_walk(walk: JourneyWalk, launch: MaestroLaunch, sinks: PlanSinks) -> WalkedJourney:
    """Walk a flow's `interaction` steps as Maestro `tapOn` commands, one flow file per run of taps between stops, then assert the flow's own claims in the last."""
    steps, ids, gaps = walk.steps, walk.ids, sinks.gaps
    empty_walk = WalkedJourney([], frozenset())
    if steps and (first_page := shown_on(steps[0].ref.split("#")[0], {launch.launch_screen},
                                         walk.book.fragment_hosts)) != launch.launch_screen:
        gaps.extend(Gap(oid, "unreachable-from-launch",
                        f"a cold `launchApp` opens on {launch.launch_screen!r}, not "
                        f"{first_page!r}, and nothing before this journey's first step "
                        "gets from the one to the other")
                    for oid in ids)
        return empty_walk
    refs = _Refs()
    taps = _journey_taps(walk, gaps, refs)
    if taps is None:
        return empty_walk
    result_name = "journey_result"
    covered: set[str] = set()
    compiled = _FlowChecks([], [], [])
    page_oids: list[str] = []
    for obligation in walk.obligations:
        for row in obligation.checks:
            check = _compiled_check(row, obligation, result_name, gaps, refs)
            if check is None:
                continue
            compiled.add(check)
            covered.add(obligation.id)
            if check.assertions and obligation.id not in page_oids:
                page_oids.append(obligation.id)
    if not covered:
        return empty_walk
    segments = [*taps.segments[:-1], [*taps.segments[-1], *compiled.assertions]]
    flow_stem = f"maestro/{python_identifier('-'.join(ids))}"
    written = [at for at, commands in enumerate(segments) if commands or at == 0]
    lines: list[str] = []
    for at, commands in enumerate(segments):
        if at in written:
            flow_path = f"{flow_stem}.yaml" if len(segments) == 1 else f"{flow_stem}-{at + 1}.yaml"
            sinks.files[flow_path], env = _flow_yaml(commands, launch, refs, first=at == 0)
            flow = f"qa.spec_dir / {python_literal(flow_path)}"
            if at == written[-1]:
                lines.append(f"    {result_name} = qa.maestro.run({flow}{env})")
            else:
                lines.append(f"    qa.maestro.run({flow}, require=True{env})")
        if at < len(taps.stops):
            index, stop = taps.stops[at]
            lines.extend(_settle_lines(stop, f"step {index}: stop at {trailing_comment(stop.title)}"))
    lines.extend(compiled.python_lines)
    if page_oids:
        lines.extend(
            f"    qa.vet({python_literal(document)})"
            for document in vettable(compiled.documents, walk.book.screen_routes, page_oids, gaps,
                                     mobile=True, hosts=walk.book.fragment_hosts)
        )
    stop_ids = frozenset(oid for _, stop in taps.stops for oid in stop.covers)
    return WalkedJourney(lines, frozenset(covered) | stop_ids, stop_ids)


def device_state_walks(
    states: list[Obligation], book: BookIndex, navigation: dict[str, SurfaceNavigation],
    sinks: PlanSinks, emitted: EmittedScenarios,
) -> list[str]:
    """One scenario per screen state no flow stopped at: arrange its condition, launch cold, tap to its screen, settle it and vet it there."""
    gaps = sinks.gaps
    lines: list[str] = []
    for state in sorted(states, key=lambda o: o.id):
        arrangement = arrangement_of([state])
        if arrangement.unstated:
            gaps.append(unarranged_state_walk_gap(state))
            continue
        launch = maestro_launch(surface_row(navigation, state.surface))
        if not isinstance(launch, ScenarioRefusal):
            launch = fixture_launch(
                launch, (row.name for row in state.fixtures), book.fixture_launch_screens, book.fixture_needs)
        if isinstance(launch, ScenarioRefusal):
            gaps.append(Gap(state.id, launch.kind, launch.detail))
            continue
        page = state.node.split("#")[0]
        refs = _Refs()
        reach = _reach_commands(book.fragment_hosts.get(page, page), launch, book.locators_by_node, refs)
        if isinstance(reach, ScenarioRefusal):
            gaps.append(Gap(state.id, reach.kind, reach.detail))
            continue
        stop = resolve_state(state.node, book, [state.id], gaps, device=True,
                             where=f"the walk that settles `{state.node}`")
        if stop is None:
            continue
        name = state_walk_function_name(state, emitted)
        flow_path = f"maestro/{name}.yaml"
        sinks.files[flow_path], env = _flow_yaml(reach, launch, refs)
        title = " ".join(stop.title.split()).replace("\\", "").replace('"', "'")
        body = [
            f"    qa.maestro.run(qa.spec_dir / {python_literal(flow_path)}, require=True{env})",
            *_settle_lines(stop, f"settles in {trailing_comment(stop.title)}"),
            *(f"    qa.vet({python_literal(document)})"
              for document in vettable([page], book.screen_routes, [state.id], gaps,
                                       mobile=True, hosts=book.fragment_hosts)),
        ]
        emitted.covered.add(state.id)
        target_var = target_variable(state.surface, "mobile")
        lines.extend(target_lines(target_var, MAESTRO.name, f", app_id={python_literal(launch.bundle_id)}", emitted))
        scenario = SourceScenario(
            page, target_var, [state.id], arrangement, body,
            objective=f"Open {page} from a cold launch and check it settles in {title}.")
        lines.extend(scenario_lines(scenario, name))
    return lines
