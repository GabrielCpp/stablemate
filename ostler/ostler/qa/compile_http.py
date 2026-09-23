"""The endpoint half of `compile-plan`: a route's claims as HTTP calls, and a journey walked as requests."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from dataclasses import field

from ostler import acts as acts_mod
from ostler.checks import CheckValue
from ostler.checks import _rooted
from ostler.qa import references
from ostler.qa.book_index import BookIndex
from ostler.qa.book_index import OwnedCapture
from ostler.qa.book_index import decline_captures_by_node
from ostler.qa.compile_journey import JourneyWalk
from ostler.qa.compile_journey import WalkedJourney
from ostler.qa.compile_support import PYTHON
from ostler.qa.compile_support import bullet_value
from ostler.qa.compile_support import unarranged_scenario_gap
from ostler.qa.compile_support import unarranged_state_gap
from ostler.qa.obligation import CallRow
from ostler.qa.obligation import FlowStep
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
from ostler.qa.plan_source import call_kwargs
from ostler.qa.plan_source import check_observes
from ostler.qa.plan_source import decline_captures
from ostler.qa.plan_source import operand_for
from ostler.qa.plan_source import python_literal
from ostler.qa.plan_source import scenario_lines
from ostler.qa.plan_source import target_lines
from ostler.qa.plan_source import target_variable



HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
_ROUTE = re.compile(rf"^\s*`?\s*({'|'.join(HTTP_METHODS)})\s+(\S+?)\s*`?\s*$", re.I)


def _route(locators: Locators) -> tuple[str, str] | None:
    """The HTTP method and path template a node with these *locators* is addressed by."""
    for value in locators.route:
        matched = _ROUTE.match(value)
        if matched:
            return matched.group(1).upper(), matched.group(2)
    method = bullet_value(next(iter(locators.method), None))
    path = bullet_value(next(iter(locators.path), None))
    if method and path and method.upper() in HTTP_METHODS:
        return method.upper(), path
    return None


def _invalid_method(locators: Locators) -> str | None:
    """An `endpoint`'s declared `method:` value, when it is not one of the HTTP verbs `_route` (and `_ROUTE`, for the other node type's spelling) already hold every address to."""
    method = bullet_value(next(iter(locators.method), None))
    if method and method.upper() not in HTTP_METHODS:
        return method
    return None


def _concrete_path(rows: tuple[CallRow, ...]) -> str | None:
    """A real path from a declared check, preferred over the route's `{id}` template."""
    for row in rows:
        path = row.args.get("path")
        if isinstance(path, str) and path.startswith("/"):
            return path
    return None


def _expect_status(rows: tuple[CallRow, ...]) -> int | None:
    """The status code a declared `http_status` check expects, when one states it."""
    for row in rows:
        if row.name == "http_status":
            code = row.args.get("code")
            if isinstance(code, int) and not isinstance(code, bool):
                return code
    return None


def api_scenarios(
    http_owed: list[Obligation], book: BookIndex, sinks: PlanSinks, emitted: EmittedScenarios,
) -> list[str]:
    """One scenario per book page whose endpoints owe live evidence, each driven over HTTP."""
    lines: list[str] = []
    for source, obligations in by_source(http_owed).items():
        sinks.gaps.extend(unarranged_state_gap(o) for o in obligations if not o.checks)
        declared = [o for o in obligations if o.checks]
        if not declared:
            continue
        arrangement = arrangement_of(declared)
        if arrangement.unstated:
            sinks.gaps.extend(unarranged_scenario_gap(o) for o in declared)
            continue
        covered: set[str] = set()
        body = _scenario_body(declared, sinks.gaps, covered, sinks.captured)
        if not covered:
            continue
        emitted.covered.update(covered)
        surface = obligations[0].surface
        target_var = target_variable(surface, "api")
        base_url = f", base_url={python_literal(book.resolved_api_base_urls.get(surface))}"
        lines.extend(target_lines(target_var, PYTHON.name, base_url, emitted))
        lines.extend(scenario_lines(SourceScenario(
            source, target_var, [o.id for o in declared if o.id in covered],
            arrangement.rows, body)))
    return lines


_BODILESS_METHODS = frozenset({"GET", "DELETE", "HEAD", "OPTIONS"})


def _http_body(rows: tuple[CallRow, ...]) -> dict[str, CheckValue] | None:
    """The request body *rows* arrange, or `None` if any one of them cannot be sent over HTTP."""
    body: dict[str, CheckValue] = {}
    for row in rows:
        spec = acts_mod.ACT_BY_NAME.get(row.name)
        if spec is None or acts_mod.HTTP not in spec.drivers:
            return None
        key, value = row.text_arg("field"), row.args.get("value", "")
        if key in body and body[key] != value:
            return None
        body[key] = value
    return body


def _lit_body(fields: dict[str, CheckValue]) -> str:
    """A `json_body=` dict literal, spelled the way `python_literal` spells every value inside it."""
    return "{" + ", ".join(f"{json.dumps(k)}: {python_literal(v)}" for k, v in fields.items()) + "}"


@dataclass(frozen=True)
class _Produced:
    """What earlier claims in one endpoint scenario left for a later one to reference: fixture facts and captured names."""
    facts: set[tuple[str, str]] = field(default_factory=set[tuple[str, str]])
    captures: set[str] = field(default_factory=set[str])

    def resolves(self, ref: references.Reference) -> bool:
        """Whether *ref* names a fact some earlier producer in the scenario already left behind."""
        if isinstance(ref, references.NodeRef):
            return (ref.node, ref.key) in self.facts
        return ref.name in self.captures

    def record_fixtures(self, obligation: Obligation) -> None:
        """Add the `node.key` facts *obligation*'s fixtures provide."""
        for fixture_row in obligation.fixtures:
            for qualified in fixture_row.provides_keys:
                owner, sep, key = qualified.rpartition(".")
                if sep:
                    self.facts.add((owner, key))


@dataclass(frozen=True)
class _ClaimRequest:
    """One endpoint claim's request: the line that makes it, and whether its path still holds a template variable."""
    call: str
    templated: bool


@dataclass(frozen=True)
class _UnbuiltClaimRequest:
    """An endpoint claim that compiled no request: the TODO its scenario shows, and the gap it files."""
    todo: str
    refusal: ScenarioRefusal


def _claim_request(
    obligation: Obligation, observed: str, produced: _Produced, gaps: list[Gap],
) -> _ClaimRequest | _UnbuiltClaimRequest:
    """The request one endpoint claim makes into *observed*, or why the book gives it none."""
    route = _route(obligation.locators)
    if route is None:
        bad_method = _invalid_method(obligation.locators)
        if bad_method is not None:
            return _UnbuiltClaimRequest(
                f"method {bad_method!r} is not a recognized HTTP verb",
                ScenarioRefusal("invalid-http-method", f"`method: {bad_method}` is not a recognized HTTP verb"))
        why = "the book gives this node no `route:` to act on"
        return _UnbuiltClaimRequest(why, ScenarioRefusal("uncompilable-claim", why))
    method, template = route
    rows = obligation.checks
    path = _concrete_path(rows) or template
    path_refs = references.find_references(path)
    gaps.extend(Gap(obligation.id, "unresolved-precondition",
                    f"the path references {ref!r}, not resolvable without running the plan")
                for ref in path_refs if not produced.resolves(ref))
    wants_body = method not in _BODILESS_METHODS
    act_rows = obligation.acts
    body = None if (not act_rows or obligation.acts_unparsed) else _http_body(act_rows)
    if wants_body and body is None:
        why = "the book carries no request body"
        return _UnbuiltClaimRequest(why, ScenarioRefusal("unarranged-request-body", why))
    path_expr = f"qa.resolve({python_literal(path)})" if path_refs else python_literal(path)
    status = _expect_status(rows)
    expect = f", expect_status={status}" if status is not None else ""
    body_kw = f", json_body={_lit_body(body)}" if wants_body and body is not None else ""
    return _ClaimRequest(f"    {observed} = qa.http.{method.lower()}({path_expr}{expect}{body_kw})", "{" in path)


def _request_lines(
    oid: str, request: _ClaimRequest | _UnbuiltClaimRequest, observed: str, gaps: list[Gap],
) -> list[str]:
    """The lines that make *request*, or the TODO a claim the book gives no request leaves behind."""
    if isinstance(request, _UnbuiltClaimRequest):
        gaps.append(Gap(oid, request.refusal.kind, request.refusal.detail))
        return [f"    # TODO(arrange): {request.todo}",
                f"    {observed} = None  # TODO(arrange): what this scenario observes"]
    if not request.templated:
        return [request.call]
    gaps.append(Gap(oid, "unresolved-precondition", "the path still carries a template variable"))
    return [request.call, "    # TODO(arrange): the path above still carries a template variable"]


def _claim_captures(
    obligation: Obligation, observed: str | None, produced: _Produced, gaps: list[Gap],
    captured: set[tuple[str, str]],
) -> list[str]:
    """Bind each capture *obligation* declares out of the *observed* response, declining one no response here holds."""
    lines: list[str] = []
    for capture in obligation.captures:
        name, source_path = capture.name, capture.source
        if not name:
            continue
        if source_path.startswith("$") and observed is not None:
            lines.append(
                f'    qa.capture_field({python_literal(name)}, {observed}.json(), {python_literal(str(_rooted(source_path)))})'
            )
            produced.captures.add(name)
            captured.add((obligation.id, name))
            continue
        because = "names a UI locator, not a response field, and this builder holds a response"
        if source_path.startswith("$"):
            because = "has no observed response here to read the field off of"
        lines.append(f"    # TODO(arrange): capture {name!r} from {source_path!r} {because}")
        decline_captures([obligation], gaps, captured, because=because)
    return lines


@dataclass(frozen=True)
class _ClaimAssertions:
    """One claim's checks on its response: the `qa.verify` lines, and a TODO per check no operand here observes."""
    assertions: list[str]
    todos: list[str]


def _claim_assertions(
    obligation: Obligation, observed: str, produced: _Produced, gaps: list[Gap],
) -> _ClaimAssertions:
    """Every check *obligation* declares, asserted on the *observed* response where an operand observes it."""
    oid = obligation.id
    assertions: list[str] = []
    todos: list[str] = []
    for row in obligation.checks:
        gaps.extend(Gap(oid, "unresolved-precondition",
                        f"a verify argument references {ref!r}, not resolvable without running the plan")
                    for ref in references.find_references(json.dumps(row.args))
                    if not produced.resolves(ref))
        operand = operand_for(row.name, observed)
        if isinstance(operand, ScenarioRefusal):
            todos.append(f"    # TODO(arrange): {operand.detail}")
            gaps.append(Gap(oid, operand.kind, operand.detail))
            continue
        assertions.append(
            f"    qa.verify({python_literal(row.name)}, {operand}{call_kwargs(row.args)}, covers=[{python_literal(oid)}])"
        )
    return _ClaimAssertions(assertions, todos)


def _scenario_body(obligations: list[Obligation], gaps: list[Gap], covered: set[str],
                   captured: set[tuple[str, str]]) -> list[str]:
    """Compile every claim's request, captures and assertions, in book order."""
    lines: list[str] = []
    produced = _Produced()
    ordered = sorted(obligations, key=lambda o: o.doc_position or (0, 0))
    for index, obligation in enumerate(ordered, start=1):
        oid = obligation.id
        observed = f"observed_{index}"
        lines.extend(["", f"    # {oid}", f"    # {' '.join(obligation.requirement.split())}"])
        produced.record_fixtures(obligation)
        request = _claim_request(obligation, observed, produced, gaps)
        lines.extend(_request_lines(oid, request, observed, gaps))
        responded = observed if isinstance(request, _ClaimRequest) else None
        lines.extend(_claim_captures(obligation, responded, produced, gaps, captured))
        if responded is None:
            continue
        asserted = _claim_assertions(obligation, observed, produced, gaps)
        lines.extend(asserted.todos or asserted.assertions)
        if not asserted.todos:
            covered.add(oid)
    return lines


@dataclass(frozen=True)
class _HttpRequest:
    """One journey step's request: the verb, the path, and the `json_body=` it sends."""
    method: str
    path: str
    body_kw: str


@dataclass(frozen=True)
class _UnbuiltStep:
    """A journey step that compiled no request, and why its downstream captures are declined."""
    because: str


def _http_request(
    index: int, step: FlowStep, book: BookIndex, ids: list[str], gaps: list[Gap],
) -> _HttpRequest | _UnbuiltStep:
    """The request one journey step performs, gapping every claim when the book states none."""
    ref = step.ref
    step_locators = book.locators_by_node.get(ref, NO_LOCATORS)
    route = _route(step_locators)
    if route is None:
        bad_method = _invalid_method(step_locators)
        if bad_method is not None:
            gaps.extend(Gap(oid, "invalid-http-method",
                            f"step {index} ({step.href!r}) states `method: {bad_method}`, "
                            "not a recognized HTTP verb")
                        for oid in ids)
        else:
            gaps.extend(Gap(oid, "uncompilable-claim",
                            f"step {index} ({step.href!r}) states no `method:`/`path:` "
                            "for this journey to perform")
                        for oid in ids)
        return _UnbuiltStep("this journey could not compile the node this step names, so it "
                            "holds no response to capture the field from")
    method, path = route
    if method in _BODILESS_METHODS:
        return _HttpRequest(method, path, "")
    node_rows = book.acts_by_node.get(ref, [])
    fields = None if (ref in book.acts_refused or not node_rows) else _http_body(tuple(node_rows))
    if fields is None:
        gaps.extend(Gap(oid, "unarranged-request-body",
                        f"step {index} is a {method} and the book carries no request body")
                    for oid in ids)
        return _UnbuiltStep("this journey could not build this step's request body, so it "
                            "holds no response to capture the field from")
    return _HttpRequest(method, path, f", json_body={_lit_body(fields)}")


def _step_captures(
    observed: str, captures: list[OwnedCapture], sinks: PlanSinks, produced: set[str],
) -> list[str]:
    """Bind each capture a step's node declares out of *observed*, gapping one that names no response field."""
    lines: list[str] = []
    for capture in captures:
        name, source_path = capture.name, capture.source
        if not name:
            continue
        sinks.captured.add((capture.obligation_id, name))
        if source_path.startswith("$"):
            lines.append(
                f'    qa.capture_field({python_literal(name)}, {observed}.json(), '
                f'{python_literal(str(_rooted(source_path)))})'
            )
            produced.add(name)
            continue
        because = "names a UI locator, not a response field, and this builder holds a response"
        lines.append(f"    # TODO(arrange): capture {name!r} from {source_path!r} {because}")
        sinks.gaps.append(Gap(
            capture.obligation_id, "uncaptured-declaration",
            f"capture {name!r} from {source_path!r} is declared on this node and {because}",
        ))
    return lines


@dataclass(frozen=True)
class _HttpSteps:
    """What a journey's requests left: the lines that make them, the last response and path, and the captures."""
    lines: list[str]
    observed: str
    last_path: str
    produced: set[str]


def _http_steps(walk: JourneyWalk, sinks: PlanSinks) -> _HttpSteps | None:
    """Perform each `endpoint` step as a request, or `None` once one step builds no request."""
    book, gaps = walk.book, sinks.gaps
    lines: list[str] = []
    produced: set[str] = set()
    observed = last_path = ""
    for index, step in enumerate(walk.steps, start=1):
        request = _http_request(index, step, book, walk.ids, gaps)
        if isinstance(request, _UnbuiltStep):
            decline_captures_by_node([s.ref for s in walk.steps[index - 1:]], book.captures_by_node,
                                     gaps, sinks.captured, because=request.because)
            return None
        observed, last_path = f"observed_{index}", request.path
        lines.append(f"    {observed} = qa.http.{request.method.lower()}"
                     f"({python_literal(request.path)}{request.body_kw})")
        if "{" in request.path:
            lines.append("    # TODO(arrange): the path above still carries a template variable")
            gaps.extend(Gap(oid, "unresolved-precondition",
                            f"step {index}'s path still carries a template variable")
                        for oid in walk.ids)
        lines.extend(_step_captures(observed, book.captures_by_node.get(step.ref, []), sinks, produced))
    return _HttpSteps(lines, observed, last_path, produced)


def _journey_assertion(
    row: CallRow, oid: str, steps: _HttpSteps, gaps: list[Gap],
) -> str | ScenarioRefusal | None:
    """One flow check asserted on the journey's last response, or why not; `None` once its gaps are filed."""
    named = row.args.get("path")
    if isinstance(named, str) and named != steps.last_path and check_observes(row.name) == "response":
        return ScenarioRefusal(
            "uncompilable-claim",
            f"`{row.name}` names `path={named}`, and this journey ended on `{steps.last_path}` — a "
            "journey's claim is about the world its last step left, so there is no response here "
            "this check is about")
    unresolved = [
        ref for ref in references.find_references(json.dumps(row.args))
        if isinstance(ref, references.CaptureRef) and ref.name not in steps.produced
    ]
    if unresolved:
        gaps.extend(Gap(oid, "unresolved-precondition",
                        f"a verify argument references {ref!r}, not resolvable without running "
                        "the plan")
                    for ref in unresolved)
        return None
    operand = operand_for(row.name, steps.observed)
    if isinstance(operand, ScenarioRefusal):
        return operand
    return (f"    qa.verify({python_literal(row.name)}, {operand}{call_kwargs(row.args)}, "
            f"covers=[{python_literal(oid)}])")


def _http_journey_checks(
    obligations: list[Obligation], steps: _HttpSteps, gaps: list[Gap], covered: set[str],
) -> list[str]:
    """Assert every flow claim on the journey's last response, covering each one asserted whole."""
    lines: list[str] = []
    for obligation in obligations:
        oid = obligation.id
        assertions: list[str] = []
        whole = True
        for row in obligation.checks:
            asserted = _journey_assertion(row, oid, steps, gaps)
            if isinstance(asserted, ScenarioRefusal):
                lines.append(f"    # TODO(arrange): {asserted.detail}")
                gaps.append(Gap(oid, asserted.kind, asserted.detail))
            if not isinstance(asserted, str):
                whole = False
                continue
            assertions.append(asserted)
        if whole and assertions:
            lines.extend(["", f"    # {oid}", *assertions])
            covered.add(oid)
    return lines


def http_walk(walk: JourneyWalk, sinks: PlanSinks) -> WalkedJourney:
    """Perform each `endpoint` step as a request, then assert the flow's claims on the last one."""
    decline_captures(walk.obligations, sinks.gaps, sinks.captured, because=(
        "a journey performs its steps and asserts the flow's own claim; a capture declared on "
        "the flow node itself names no response this scenario ever holds"))
    steps = _http_steps(walk, sinks)
    if steps is None:
        return WalkedJourney([], frozenset())
    covered: set[str] = set()
    checks = _http_journey_checks(walk.obligations, steps, sinks.gaps, covered)
    return WalkedJourney([*steps.lines, *checks], frozenset(covered))
