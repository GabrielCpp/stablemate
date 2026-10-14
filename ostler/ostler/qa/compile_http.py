"""The endpoint half of `compile-plan`: a route's claims as HTTP calls, and a journey walked as requests."""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from collections.abc import Callable
from typing import Any

from ostler import acts as acts_mod
from ostler import registry
from ostler.checks import CheckCall
from ostler.checks import CheckValue
from ostler.checks import parse_check
from ostler.checks import _rooted
from ostler.data_states import DataState
from ostler.data_states import anchor_of
from ostler.data_states import move_obligation_id
from ostler.data_states import siblings_of
from ostler.data_states import state_obligation_id
from ostler.qa import references
from ostler.qa.book_index import BookIndex
from ostler.qa.book_index import OwnedCapture
from ostler.qa.book_index import decline_captures_by_node
from ostler.qa.compile_journey import JourneyWalk
from ostler.qa.compile_journey import WalkedJourney
from ostler.qa.compile_journey import api_target
from ostler.qa.compile_support import PATH_VARIABLE
from ostler.qa.compile_support import PYTHON
from ostler.qa.compile_support import on_node
from ostler.qa.compile_support import bullet_value
from ostler.qa.compile_support import unarranged_scenario_gap
from ostler.qa.compile_support import unarranged_state_gap
from ostler.qa.obligation import CallRow
from ostler.qa.obligation import FlowStep
from ostler.qa.obligation import Locators
from ostler.qa.obligation import NO_LOCATORS
from ostler.qa.obligation import Obligation
from ostler.qa.plan_source import Arrangement
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
from ostler.qa.plan_source import probe_function_name
from ostler.qa.plan_source import python_literal
from ostler.qa.plan_source import scenario_lines
from ostler.qa.plan_source import target_lines



HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
_ROUTE = re.compile(rf"^\s*`?\s*({'|'.join(HTTP_METHODS)})\s+(\S+?)\s*`?\s*$", re.I)


def route_of(locators: Locators) -> tuple[str, str] | None:
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
    """An `endpoint`'s declared `method:` value, when it is not one of the HTTP verbs `route_of` (and `_ROUTE`, for the other node type's spelling) already hold every address to."""
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


def _request_path(template: str, rows: tuple[CallRow, ...]) -> str:
    """The path a claim requests: a declared check's real path, unless it drops a reference the route names and names no other in its place."""
    concrete = _concrete_path(rows)
    if concrete is None:
        return template
    routed, checked = set(references.find_references(template)), set(references.find_references(concrete))
    if routed - checked and not checked - routed:
        return template
    return concrete


def expect_status(rows: tuple[CallRow, ...]) -> int | None:
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
        arranging = _arranging(obligations, book)
        arrangement = _with_lent_fixtures(arrangement_of(declared), _credential_lenders(declared, arranging), declared)
        if arrangement.unstated:
            sinks.gaps.extend(unarranged_scenario_gap(o) for o in declared)
            continue
        covered: set[str] = set()
        body = _scenario_body(declared, arranging, book.fixture_pages, sinks.gaps, covered, sinks.captured)
        if not covered:
            continue
        emitted.covered.update(covered)
        target_var, base_url = api_target(obligations[0].surface, source, book)
        lines.extend(target_lines(target_var, PYTHON.name, f", base_url={python_literal(base_url)}", emitted))
        scenario = SourceScenario(
            source, target_var, [o.id for o in declared if o.id in covered],
            arrangement, body)
        lines.extend(scenario_lines(scenario, claim_scenario_function_name(scenario, emitted)))
    return lines


_REFUSED = (401, 403)


def probe_scenarios(http_owed: list[Obligation], book: BookIndex, emitted: EmittedScenarios) -> list[str]:
    """One scenario per fixture whose fact a claim sends as a credential: the fixture built on its own, then the first such claim's request, which must not be refused."""
    lines: list[str] = []
    probed: set[str] = set()
    for source, obligations in by_source(http_owed).items():
        ordered = sorted((o for o in obligations if o.checks), key=lambda o: o.doc_position)
        credentials = _node_credentials(_arranging(obligations, book))
        callers = _node_caller_headers(_arranging(obligations, book))
        for obligation in ordered:
            probe = _probe(obligation, credentials.get(obligation.node, ()), callers.get(obligation.node, frozenset()))
            if probe is None or probe.fixture in probed:
                continue
            probed.add(probe.fixture)
            target_var, base_url = api_target(obligation.surface, source, book)
            lines.extend(target_lines(target_var, PYTHON.name, f", base_url={python_literal(base_url)}", emitted))
            scenario = SourceScenario(
                source, target_var, [obligation.id], arrangement_of([obligation]), probe.body(obligation.id),
                objective=f"Whether {probe.fixture} builds on its own and a caller it signs in is answered on {probe.route}.")
            lines.extend(scenario_lines(scenario, probe_function_name(probe.fixture, emitted)))
    return lines


@dataclass(frozen=True)
class _Probe:
    """The fixture a claim's credential comes from, the route the claim asks, and the request it sends."""
    fixture: str
    route: str
    request: _ClaimRequest

    def body(self, oid: str) -> list[str]:
        """The claim's request, then the check that the fixture's credential was not refused."""
        label = f"{self.fixture} signs a caller in that {self.route} does not refuse"
        refused = python_literal(list(_REFUSED))
        check = (f"    qa.check({python_literal(label)}, observed.status not in {refused}, "
                 f"actual=observed.status, expected={python_literal(f'not {refused}')}, covers=[{python_literal(oid)}])")
        return ["", *_within_claim(oid, [self.request.call, check])]


def _probe(obligation: Obligation, credentials: tuple[CallRow, ...], caller: frozenset[tuple[str, str]]) -> _Probe | None:
    """The probe of the first fixture whose fact *obligation* sends in a header, when the claim is a GET that expects success on a path it can build."""
    route = route_of(obligation.locators)
    status = expect_status(obligation.checks)
    if route is None or route[0] != "GET" or status is None or status >= 400:
        return None
    sent = {ref.node for row in _claim_acts(obligation, credentials, caller) if row.name == "header"
            for ref in references.find_references(row.text_arg("value")) if isinstance(ref, references.NodeRef)}
    fixture = next((row.name for row in obligation.fixtures if row.name in sent), None)
    if fixture is None:
        return None
    produced = _Produced()
    produced.record_fixtures(obligation)
    gaps: list[Gap] = []
    request = _claim_request(obligation, "observed", produced, gaps, credentials, caller)
    if not isinstance(request, _ClaimRequest) or request.templated or gaps:
        return None
    return _Probe(fixture, f"{route[0]} {_request_path(route[1], obligation.checks)}", request)


_BODILESS_METHODS = frozenset({"GET", "DELETE", "HEAD", "OPTIONS"})
_SERVER_FAULT = 500
_WHOLE_BODY = "$"


@dataclass(frozen=True)
class _HttpArrangement:
    """What a step's acts put on the wire: the members of its body and the headers it sends."""
    body: dict[str, CheckValue]
    headers: dict[str, CheckValue]
    bodiless: bool = False

    def states_body(self) -> bool:
        """Whether the book said what the request carries: its members, or that it carries none."""
        return bool(self.body) or self.bodiless

    def named_references(self) -> list[references.Reference]:
        """Every `@node.key`/`$name` a body member or a header value names."""
        values = [*self.body.values(), *self.headers.values()]
        return [ref for value in values if isinstance(value, str)
                for ref in references.find_references(value)]

    def kwargs_source(self, *, with_body: bool) -> str:
        """The `json_body=`/`headers=` keywords of the call that sends this arrangement."""
        body = f", json_body={_nested_body_literal(self.body)}" if with_body and not self.bodiless else ""
        headers = f", headers={_resolved_dict_literal(self.headers)}" if self.headers else ""
        return body + headers


def _http_arrangement(rows: tuple[CallRow, ...], *, later_replaces: bool = False) -> _HttpArrangement | None:
    """The body and headers *rows* arrange, or `None` if any one of them cannot be sent over HTTP. Two values for one name cannot both be sent, unless *later_replaces*: a claim's own act comes after its node's and replaces it."""
    arranged = _HttpArrangement({}, {})
    for row in rows:
        spec = acts_mod.ACT_BY_NAME.get(row.name)
        if spec is None or acts_mod.HTTP not in spec.drivers:
            return None
        if spec.name == "no_body":
            arranged = replace(arranged, bodiless=True)
            continue
        if spec.name == "header":
            sink, key, value = arranged.headers, row.text_arg("name"), row.text_arg("value")
        else:
            sink, key, value = arranged.body, row.text_arg("field"), row.args.get("value", "")
        if key in sink and sink[key] != value and not later_replaces:
            return None
        sink[key] = value
    if any(other.startswith(f"{key}.") for key in arranged.body for other in arranged.body):
        return None
    if _WHOLE_BODY in arranged.body and len(arranged.body) > 1:
        return None
    if arranged.bodiless and arranged.body:
        return None
    return arranged


def _resolved_literal(value: CheckValue, resolver: str = "resolve") -> str:
    """One value as `python_literal` spells it, wrapped in `qa.<resolver>` when it names a reference."""
    literal = python_literal(value)
    if isinstance(value, str) and references.find_references(value):
        return f"qa.{resolver}({literal})"
    return literal


def _resolved_dict_literal(fields: dict[str, CheckValue]) -> str:
    """A `json_body=`/`headers=` dict literal, every value spelled by `_resolved_literal`."""
    return "{" + ", ".join(f"{json.dumps(k)}: {_resolved_literal(v)}" for k, v in fields.items()) + "}"


def _nested_body_literal(fields: dict[str, CheckValue]) -> str:
    """A `json_body=` literal: a dotted field such as `locales.fr` is a member of a nested object, and the lone field `$` is the whole body."""
    if list(fields) == [_WHOLE_BODY]:
        return _resolved_literal(fields[_WHOLE_BODY], "resolve_body")
    tree: dict[str, Any] = {}
    for path, value in fields.items():
        *parents, leaf = path.split(".")
        node = tree
        for parent in parents:
            node = node.setdefault(parent, {})
        node[leaf] = value
    return _tree_literal(tree)


def _tree_literal(tree: dict[str, Any]) -> str:
    """One level of a nested body, each leaf spelled by `_resolved_literal` through `qa.resolve_body`."""
    members = (f"{json.dumps(k)}: {_tree_literal(v) if isinstance(v, dict) else _resolved_literal(v, 'resolve_body')}"
               for k, v in tree.items())
    return "{" + ", ".join(members) + "}"


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


def _arranging(obligations: list[Obligation], book: BookIndex) -> list[Obligation]:
    """Every claim on these obligations' nodes that arranges an act, whether it checks anything or not."""
    nodes = dict.fromkeys(obligation.node for obligation in obligations)
    return [claim for node in nodes for claim in book.claims_by_node.get(node, [])]


def _node_credentials(obligations: list[Obligation]) -> dict[str, tuple[CallRow, ...]]:
    """Each endpoint's `header` acts, from every claim of it that arranges one and does not expect a refusal, less a name two claims set apart. A claim that expects a 401 or a 403 names the caller the endpoint refuses, which is its own to send."""
    values: dict[str, dict[str, set[str]]] = {}
    rows: dict[str, dict[str, CallRow]] = {}
    stated = _stated_statuses(obligations)
    for obligation in obligations:
        if _claim_status(obligation, stated.get(_request_key(obligation))) in _REFUSED:
            continue
        for row in obligation.acts:
            if row.name != "header" or not obligation.node:
                continue
            name = row.text_arg("name")
            values.setdefault(obligation.node, {}).setdefault(name, set()).add(row.text_arg("value"))
            rows.setdefault(obligation.node, {}).setdefault(name, row)
    return {node: tuple(row for name, row in by_name.items() if len(values[node][name]) == 1)
            for node, by_name in rows.items()}


def _credential_lenders(declared: list[Obligation], arranging: list[Obligation]) -> list[Obligation]:
    """The claims that check nothing yet arrange a header their endpoint's checked claims send, so their fixtures have to be arranged too."""
    checked = {obligation.id for obligation in declared}
    nodes = {obligation.node for obligation in declared}
    return [claim for claim in arranging
            if claim.id not in checked and claim.node in nodes and claim.fixtures
            and any(row.name == "header" for row in claim.acts)]


def _with_lent_fixtures(arrangement: Arrangement, lenders: list[Obligation], declared: list[Obligation]) -> Arrangement:
    """*arrangement* plus each lender's fixtures, needed by every checked claim of the lender's endpoint."""
    if not lenders:
        return arrangement
    rows = {(row.name, row.args): row for row in arrangement.rows}
    needed_by = {key: list(ids) for key, ids in arrangement.needed_by.items()}
    for lender in lenders:
        borrowers = [obligation.id for obligation in declared if obligation.node == lender.node]
        for row in lender.fixtures:
            key = (row.name, row.args)
            rows.setdefault(key, row)
            needers = needed_by.setdefault(key, [])
            needers.extend(oid for oid in borrowers if oid not in needers)
    return Arrangement(list(rows.values()), arrangement.stated_none, needed_by)


def _header_pair(row: CallRow) -> tuple[str, str]:
    return row.text_arg("name"), row.text_arg("value")


def _node_caller_headers(obligations: list[Obligation]) -> dict[str, frozenset[tuple[str, str]]]:
    """Each endpoint's headers its claims send as the caller, from every claim of it that does not expect a 401."""
    sent: dict[str, set[tuple[str, str]]] = {}
    stated = _stated_statuses(obligations)
    for obligation in obligations:
        if not obligation.node or _claim_status(obligation, stated.get(_request_key(obligation))) == 401:
            continue
        pairs = sent.setdefault(obligation.node, set())
        pairs.update(_header_pair(row) for row in obligation.acts if row.name == "header")
    return {node: frozenset(pairs) for node, pairs in sent.items()}


def _request_key(obligation: Obligation) -> tuple[str, frozenset[str], frozenset[str]]:
    """The request a claim sends, as its node, its acts and the fixtures it builds."""
    return (obligation.node, frozenset(row.call for row in obligation.acts),
            frozenset(row.name for row in obligation.fixtures))


def _stated_statuses(obligations: list[Obligation]) -> dict[tuple[str, frozenset[str], frozenset[str]], int]:
    """The one status the claims sending each request state it is answered with, for each request whose claims state exactly one."""
    stated: dict[tuple[str, frozenset[str], frozenset[str]], set[int]] = {}
    for obligation in obligations:
        status = expect_status(obligation.checks)
        if obligation.node and status is not None:
            stated.setdefault(_request_key(obligation), set()).add(status)
    return {key: next(iter(codes)) for key, codes in stated.items() if len(codes) == 1}


def _claim_status(obligation: Obligation, stated: int | None) -> int | None:
    """The status a claim expects: its own `http_status`, else the one *stated* by the claims sending the same request."""
    own = expect_status(obligation.checks)
    return own if own is not None else stated


def _claim_acts(
    obligation: Obligation, credentials: tuple[CallRow, ...], caller: frozenset[tuple[str, str]] = frozenset(),
    stated: int | None = None,
) -> tuple[CallRow, ...]:
    """The acts a claim sends: its own, plus each endpoint header it does not set. A claim that expects a 401 is about the anonymous caller, so it sends none of the caller's headers, even one it repeats."""
    if _claim_status(obligation, stated) == 401:
        return tuple(row for row in obligation.acts if row.name != "header" or _header_pair(row) not in caller)
    own = {row.text_arg("name") for row in obligation.acts if row.name == "header"}
    return (*obligation.acts, *(row for row in credentials if row.text_arg("name") not in own))


def _claim_request(
    obligation: Obligation, observed: str, produced: _Produced, gaps: list[Gap],
    credentials: tuple[CallRow, ...] = (), caller: frozenset[tuple[str, str]] = frozenset(),
    stated: int | None = None,
) -> _ClaimRequest | _UnbuiltClaimRequest:
    """The request one endpoint claim makes into *observed*, or why the book gives it none. A claim that checks no status expects the one *stated* by the claims sending the same request."""
    route = route_of(obligation.locators)
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
    status = _claim_status(obligation, stated)
    if status is not None and status >= _SERVER_FAULT:
        why = f"no request a caller sends makes a healthy app answer {status}"
        return _UnbuiltClaimRequest(why, ScenarioRefusal("unarrangeable-server-fault", why))
    path = _request_path(template, rows)
    path_refs = references.find_references(path)
    gaps.extend(Gap(obligation.id, "unresolved-precondition",
                    f"the path references {ref!r}, not resolvable without running the plan")
                for ref in path_refs if not produced.resolves(ref))
    wants_body = method not in _BODILESS_METHODS
    act_rows = _claim_acts(obligation, credentials, caller, stated)
    arranged = None if (not act_rows or obligation.acts_unparsed) else _http_arrangement(act_rows, later_replaces=True)
    if wants_body and (arranged is None or not arranged.states_body()):
        why = "the book carries no request body"
        return _UnbuiltClaimRequest(why, ScenarioRefusal("unarranged-request-body", why))
    if arranged is not None:
        gaps.extend(Gap(obligation.id, "unresolved-precondition",
                        f"the request references {ref!r}, not resolvable without running the plan")
                    for ref in arranged.named_references() if not produced.resolves(ref))
    path_expr = f"qa.resolve({python_literal(path)})" if path_refs else python_literal(path)
    expect = f", expect_status={status}" if status is not None else ""
    kwargs_source = arranged.kwargs_source(with_body=wants_body) if arranged is not None else ""
    return _ClaimRequest(f"    {observed} = qa.http.{method.lower()}({path_expr}{expect}{kwargs_source})", "{" in path)


def _deletes_shared_fixture(obligation: Obligation, fixture_pages: dict[str, frozenset[str]]) -> ScenarioRefusal | None:
    """Why a DELETE claim that succeeds must not run: its path names a fact of a fixture other pages name too, and every page of a lap reuses that fixture's one build."""
    route = route_of(obligation.locators)
    status = expect_status(obligation.checks)
    if route is None or route[0] != "DELETE" or (status is not None and status >= 400):
        return None
    for ref in references.find_references(_request_path(route[1], obligation.checks)):
        if not isinstance(ref, references.NodeRef):
            continue
        others = sorted(fixture_pages.get(ref.node, frozenset()) - {obligation.source})
        if others:
            named = ", ".join(others[:3]) + (", ..." if len(others) > 3 else "")
            return ScenarioRefusal("deletes-shared-fixture", (
                f"this DELETE removes `@{ref.node}.{ref.key}`, and fixture `{ref.node}` is built once per run "
                f"and shared with {named}. Give this claim its own fixture that creates the resource it deletes, "
                f"named on this page only"))
    return None


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


def _verify_line(oid: str, row: CallRow, observed: str) -> str | ScenarioRefusal:
    """The `qa.verify` line that asserts *row* on *observed* covering *oid*, or why no operand observes it."""
    operand = operand_for(row.name, observed, row.args)
    if isinstance(operand, ScenarioRefusal):
        return operand
    return f"    qa.verify({python_literal(row.name)}, {operand}{call_kwargs(row.args)}, covers=[{python_literal(oid)}])"


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
        line = _verify_line(oid, row, observed)
        if isinstance(line, ScenarioRefusal):
            todos.append(f"    # TODO(arrange): {line.detail}")
            gaps.append(Gap(oid, line.kind, line.detail))
            continue
        assertions.append(line)
    return _ClaimAssertions(assertions, todos)


def _scenario_body(obligations: list[Obligation], arranging: list[Obligation], fixture_pages: dict[str, frozenset[str]],
                   gaps: list[Gap], covered: set[str], captured: set[tuple[str, str]]) -> list[str]:
    """Compile every claim's request, captures and assertions, in book order, sending each node's credentials from every claim that arranges one, checked or not."""
    lines: list[str] = []
    produced = _Produced()
    ordered = sorted(obligations, key=lambda o: o.doc_position)
    credentials = _node_credentials(arranging)
    callers = _node_caller_headers(arranging)
    statuses = _stated_statuses(arranging)
    for lender in _credential_lenders(obligations, arranging):
        produced.record_fixtures(lender)
    for index, obligation in enumerate(ordered, start=1):
        oid = obligation.id
        observed = f"observed_{index}"
        lines.extend(["", f"    # {oid}", f"    # {' '.join(obligation.requirement.split())}"])
        produced.record_fixtures(obligation)
        refusal = _deletes_shared_fixture(obligation, fixture_pages)
        request = (_UnbuiltClaimRequest(refusal.detail, refusal) if refusal is not None
                   else _claim_request(obligation, observed, produced, gaps,
                                       credentials.get(obligation.node, ()), callers.get(obligation.node, frozenset()),
                                       statuses.get(_request_key(obligation))))
        claim_lines = _request_lines(oid, request, observed, gaps)
        responded = observed if isinstance(request, _ClaimRequest) else None
        claim_lines.extend(_claim_captures(obligation, responded, produced, gaps, captured))
        if responded is None:
            lines.extend(claim_lines)
            continue
        asserted = _claim_assertions(obligation, observed, produced, gaps)
        claim_lines.extend(asserted.todos or asserted.assertions)
        lines.extend(_within_claim(oid, claim_lines))
        if not asserted.todos:
            covered.add(oid)
    return lines


def _within_claim(oid: str, lines: list[str]) -> list[str]:
    """*lines* inside the claim's `qa.claim` block, so a claim that fails is recorded against it and the scenario goes on to the next."""
    indented = [f"    {line}" if line else line for text in lines for line in text.split("\n")]
    return [f"    with qa.claim([{python_literal(oid)}]):", *indented]


@dataclass(frozen=True)
class _HttpRequest:
    """One journey step's request: the verb, the path, the query its node's claims spell, and the `json_body=`/`headers=` it sends."""
    method: str
    path: str
    kwargs_source: str
    sent_references: tuple[references.Reference, ...] = ()
    query: str = ""
    sent_headers: dict[str, CheckValue] = field(default_factory=dict[str, CheckValue])


@dataclass(frozen=True)
class _UnbuiltStep:
    """A journey step that compiled no request, and why its downstream captures are declined."""
    because: str


@dataclass(frozen=True)
class _Outcome:
    """The one case an invocation step expects: its status, the claims that judge it, and the acts, query and address its own rows spell."""
    status: int | None
    claims: tuple[Obligation, ...]
    acts: tuple[CallRow, ...]
    query: str
    checked_path: str | None
    acts_unparsed: bool


def case_status(claim: Obligation) -> int | None:
    """The status one invocation claim expects: its `http_status` code, else the code its `status:` or refusal bullet states."""
    status = expect_status(claim.checks)
    if status is None and claim.kind in (*registry.refusal_keys(claim.node_type), "status"):
        stated = claim.requirement.strip()
        if stated.isdigit():
            return int(stated)
    return status


def _invocation_outcome(claims: list[Obligation]) -> _Outcome | list[int]:
    """The one outcome an invocation's *claims* expect, or every distinct status when they expect more than one."""
    owned = [claim for claim in claims if claim.checks or claim.acts or case_status(claim) is not None]
    statuses = sorted({status for claim in owned if (status := case_status(claim)) is not None})
    if len(statuses) > 1:
        return statuses
    named = [row.args.get("path") for claim in owned for row in claim.checks]
    paths = [path for path in named if isinstance(path, str) and path.startswith("/")]
    query = next((path.partition("?")[2] for path in paths if "?" in path), "")
    return _Outcome(
        status=statuses[0] if statuses else None,
        claims=tuple(owned),
        acts=tuple(row for claim in owned for row in claim.acts),
        query=query,
        checked_path=paths[0].partition("?")[0] if paths else None,
        acts_unparsed=any(claim.acts_unparsed for claim in owned),
    )


def _step_arrangement(ref: str, node_rows: list[CallRow], book: BookIndex) -> _HttpArrangement | None:
    """What one journey step sends: the acts of every claim on its node that expects no refusal, merged, else the first success claim's own acts when those claims arrange a field differently."""
    refusing = {row.call for claim in book.claims_by_node.get(ref, ()) if (expect_status(claim.checks) or 0) >= 400
                for row in claim.acts}
    admitted = {row.call for claim in book.claims_by_node.get(ref, ()) if (expect_status(claim.checks) or 0) < 400
                for row in claim.acts}
    merged = _http_arrangement(tuple(row for row in node_rows if row.call in admitted or row.call not in refusing))
    if merged is not None:
        return merged
    for claim in book.claims_by_node.get(ref, ()):
        status = expect_status(claim.checks)
        if status is not None and 200 <= status < 300:
            return _http_arrangement(claim.acts, later_replaces=True)
    return None


def _http_request(
    index: int, step: FlowStep, book: BookIndex, ids: list[str], gaps: list[Gap], ended: str | None = None,
    outcome: _Outcome | None = None, rewire: Callable[[CheckValue], CheckValue] | None = None,
) -> _HttpRequest | _UnbuiltStep:
    """The request one journey step performs, gapping every claim when the book states none."""
    ref = step.ref
    step_locators = book.locators_by_node.get(ref, NO_LOCATORS)
    route = route_of(step_locators)
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
    if "*" in path:
        candidates = (ended, outcome.checked_path if outcome else book.checked_paths_by_node.get(ref))
        member = next((c for c in candidates if c is not None and fnmatch.fnmatchcase(c, path)), None)
        if member is None:
            gaps.extend(Gap(oid, "uncompilable-claim",
                            f"step {index} ({step.href!r}) states the pattern `{path}`, and no check on that "
                            "node or on this journey's end names one address it matches for this journey to "
                            "request")
                        for oid in ids)
            return _UnbuiltStep("this journey could not pick an address for this step, so it holds no "
                                "response to capture the field from")
        path = member
    if outcome is not None:
        query = "" if "?" in path else outcome.query
        arranged = (None if (outcome.acts_unparsed or not outcome.acts)
                    else _http_arrangement(outcome.acts, later_replaces=True))
    else:
        query = "" if "?" in path else book.queries_by_node.get(ref, "")
        node_rows = book.acts_by_node.get(ref, [])
        arranged = (None if (ref in book.acts_refused or not node_rows)
                    else _step_arrangement(ref, node_rows, book))
    if rewire is not None and arranged and arranged.headers and _own_record(ref, book):
        arranged = replace(arranged, headers={name: rewire(value) for name, value in arranged.headers.items()})
    sent_references = (*(arranged.named_references() if arranged else ()), *references.find_references(query))
    if method in _BODILESS_METHODS:
        return _HttpRequest(method, path, arranged.kwargs_source(with_body=False) if arranged else "", sent_references, query,
                            dict(arranged.headers) if arranged else {})
    if arranged is None or not arranged.states_body():
        gaps.extend(Gap(oid, "unarranged-request-body",
                        f"step {index} is a {method} and the book carries no request body")
                    for oid in ids)
        return _UnbuiltStep("this journey could not build this step's request body, so it "
                            "holds no response to capture the field from")
    return _HttpRequest(method, path, arranged.kwargs_source(with_body=True), sent_references, query, dict(arranged.headers))


def _book_spelling(ref: references.Reference) -> str:
    """*ref* as the book spells it: `@node.key` or `$name`."""
    return f"@{ref.node}.{ref.key}" if isinstance(ref, references.NodeRef) else f"${ref.name}"


def _unprovided_references(request: _HttpRequest, known: _Produced) -> list[references.Reference]:
    """Every reference *request* sends that no journey fixture or earlier step provides."""
    return [ref for ref in request.sent_references if not known.resolves(ref)]


def _unprovided_reference_gaps(index: int, unprovided: list[references.Reference], ids: list[str]) -> list[Gap]:
    """One gap per obligation for each reference step *index* sends that nothing provides."""
    return [Gap(oid, "unresolved-precondition",
                f"step {index} sends `{_book_spelling(ref)}`, and neither a fixture the flow's "
                "`fixture:` names nor an earlier step provides it — name the fixture that "
                "provides it on the flow, or arrange the step from a fact the flow's "
                "fixture provides")
            for ref in unprovided for oid in ids]


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
    reached: frozenset[str] = frozenset()
    first_headers: dict[str, CheckValue] = field(default_factory=dict[str, CheckValue])


def _fixture_owners(obligations: list[Obligation]) -> dict[str, set[str]]:
    """Each key the journey's fixtures provide, and the fixtures that provide it."""
    owners: dict[str, set[str]] = {}
    for obligation in obligations:
        for fixture_row in obligation.fixtures:
            for qualified in fixture_row.provides_keys:
                owner, sep, key = qualified.rpartition(".")
                if sep:
                    owners.setdefault(key, set()).add(owner)
    return owners


def _bound_path(path: str, produced: set[str], owners: dict[str, set[str]], named: set[str]) -> str:
    """*path* with each `{name}` an earlier step captured or one fixture provides spelled as that reference.

    Where several of the journey's fixtures provide the key, the one the step's own request names is the one meant.
    """
    def bind(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in produced:
            return f"${name}"
        provided = owners.get(name, set())
        if len(provided) > 1:
            provided = provided & named
        if len(provided) == 1:
            return f"@{next(iter(provided))}.{name}"
        return match.group(0)
    return PATH_VARIABLE.sub(bind, path)


_FLOW_REFUSAL = (
    "a flow's verify: reads the response its last step gets, and a step expects success unless it links a refusal "
    "case. Link the case that answers {code}, such as an invocation with errors:, as the step, and drop the flow's "
    "http_status.")


def _ended_path(obligations: list[Obligation]) -> str | None:
    """The address a flow's own response check names, without its query: the one its last step must request."""
    for obligation in obligations:
        for row in obligation.checks:
            named = row.args.get("path")
            if isinstance(named, str) and check_observes(row.name) == "response":
                return named.partition("?")[0]
    return None


def _route_pattern(path: str) -> re.Pattern[str]:
    """The addresses a step requesting the route *path* answers, where a `{variable}` matches any one segment and a `*` any run."""
    pieces = re.split(r"(\{[^/{}]+\}|\*)", path.partition("?")[0])
    return re.compile("".join(
        ("[^/]+" if piece.startswith("{") else ".*" if piece == "*" else re.escape(piece)) for piece in pieces))


def _step_success_checks(
    index: int, step: FlowStep, request: _HttpRequest, observed: str, walk: JourneyWalk, known: _Produced,
    gaps: list[Gap], claims: tuple[Obligation, ...] | list[Obligation],
) -> list[str]:
    """Every check of the *claims* the step expects, asserted on *observed* straight after the request that earned it."""
    pattern = _route_pattern(request.path)
    lines: list[str] = []
    for claim in claims:
        for row in claim.checks:
            named = row.args.get("path")
            if (isinstance(named, str) and check_observes(row.name) == "response"
                    and not pattern.fullmatch(named.partition("?")[0])):
                continue
            unresolved = [ref for ref in references.find_references(json.dumps(row.args)) if not known.resolves(ref)]
            if unresolved:
                gaps.extend(Gap(oid, "unresolved-precondition",
                                f"step {index} ({step.ref}) checks `{row.name}` with `{_book_spelling(ref)}`, "
                                "and neither a fixture the flow's `fixture:` names nor an earlier step provides it")
                            for ref in unresolved for oid in walk.ids)
                continue
            line = _verify_line(claim.id, row, observed)
            if not isinstance(line, ScenarioRefusal):
                lines.append(line)
    if not lines:
        return []
    return [f"    with qa.at_node({python_literal(step.ref)}):", *(f"    {line}" for line in lines)]


def _state_rows(state: DataState, observed: str) -> list[str] | ScenarioRefusal:
    """The `(check, operand, args)` tuples that assert *state* on the response held in *observed*, or why no operand observes one."""
    rows: list[str] = []
    for text in state.verify:
        call = parse_check(text)
        if not isinstance(call, CheckCall):
            continue
        operand = operand_for(call.name, observed, call.args)
        if isinstance(operand, ScenarioRefusal):
            return operand
        args = "{" + ", ".join(f"{python_literal(key)}: {_resolved_literal(value)}" for key, value in call.args.items()) + "}"
        rows.append(f"({python_literal(call.name)}, {operand}, {args})")
    return rows


_FIXTURE_FACT = re.compile(r"(?<![\w.])@([a-zA-Z0-9][a-zA-Z0-9_-]*)\.([a-zA-Z0-9][a-zA-Z0-9_-]*)")


def _rewired(value: CheckValue, known: _Produced, owners: frozenset[str] = frozenset()) -> CheckValue:
    """*value* with each `@fixture.fact` sent from the one fixture of *owners* that provides that fact when there is exactly one, else from the one fixture the walk arranges that provides it when the named fixture is not arranged."""
    if not isinstance(value, str):
        return value
    arranged = {node for node, _key in known.facts}

    def swap(matched: re.Match[str]) -> str:
        node, key = matched.group(1), matched.group(2)
        if owners:
            held = {owner for owner in owners if (owner, key) in known.facts}
            if len(held) == 1:
                return matched.group(0) if node in owners else f"@{next(iter(held))}.{key}"
        providers = {owner for owner, fact in known.facts if fact == key}
        if node in arranged or len(providers) != 1:
            return matched.group(0)
        return f"@{next(iter(providers))}.{key}"

    return _FIXTURE_FACT.sub(swap, value)


def read_back(
    where: str, observed: str, target: DataState, book: BookIndex, known: _Produced, produced: set[str],
    owners: dict[str, set[str]], step_headers: dict[str, CheckValue] | None = None, rewire: bool = False,
    record_fixtures: frozenset[str] = frozenset(),
) -> list[str] | str:
    """The lines that request *target*'s observing endpoint as a step would and hold its checks on the answer, naming the sibling state that holds when they fail, or why the walk cannot read it. With *step_headers*, the headers the moving step sent replace the observing endpoint's own of the same name."""
    arranged = None
    node_rows = book.acts_by_node.get(target.observe, [])
    if node_rows and target.observe not in book.acts_refused:
        arranged = _step_arrangement(target.observe, node_rows, book)
    if rewire and arranged and arranged.headers and _own_record(target.observe, book):
        arranged = replace(arranged, headers={name: _rewired(value, known, record_fixtures) for name, value in arranged.headers.items()})
    stepped: list[references.Reference] = []
    if step_headers:
        replaced = {name.lower() for name in step_headers}
        kept = {name: value for name, value in (arranged.headers if arranged else {}).items() if name.lower() not in replaced}
        arranged = _HttpArrangement(arranged.body if arranged else {}, {**kept, **step_headers}, arranged.bodiless if arranged else False)
        stepped = [ref for value in step_headers.values() if isinstance(value, str) for ref in references.find_references(value)]
    sent = tuple(arranged.named_references()) if arranged else ()
    unprovided = [ref for ref in sent if ref not in stepped and not known.resolves(ref)]
    bound = _bound_path(target.path, produced, owners, set())
    problem = (f"{where} of `{anchor_of(target.node)}` sends `{_book_spelling(unprovided[0])}`, "
               "and nothing the walk runs provides it" if unprovided
               else f"{where} of `{anchor_of(target.node)}` requests `{bound}`, and the walk "
                    "holds no value for its template variable" if "{" in bound
               else f"{where} of `{anchor_of(target.node)}` requests `{target.method} "
                    f"{target.path}`, which is no HTTP request" if target.method not in HTTP_METHODS else "")
    states = {target.node: _state_rows(target, observed)}
    states.update({other.node: _state_rows(other, observed) for other in siblings_of(target, book.data_states)})
    refused = next((rows for rows in states.values() if isinstance(rows, ScenarioRefusal)), None)
    if isinstance(refused, ScenarioRefusal):
        problem = problem or f"{where} of `{anchor_of(target.node)}`: {refused.detail}"
    if problem:
        return problem
    target_path = f"qa.resolve({python_literal(bound)})" if references.find_references(bound) else python_literal(bound)
    kwargs = arranged.kwargs_source(with_body=False) if arranged else ""
    held = ", ".join(f"{python_literal(anchor_of(node))}: [{', '.join(rows)}]"
                     for node, rows in states.items() if not isinstance(rows, ScenarioRefusal))
    return [
        f"    {observed} = qa.http.{target.method.lower()}({target_path}{kwargs})",
        f"    qa.holds({python_literal(anchor_of(target.node))}, {{{held}}})",
    ]


def _own_record(ref: str, book: BookIndex) -> bool:
    """Whether node *ref* addresses the caller's own record: neither its route nor, for an invocation, its `on:` endpoint's route carries a path variable."""

    def spelled(node: str) -> str:
        locators = book.locators_by_node.get(node, NO_LOCATORS)
        return " ".join(bullet_value(value) or "" for value in (*locators.route, *locators.path))

    text = spelled(ref)
    if not text.strip():
        on_value = next(iter(book.locators_by_node.get(ref, NO_LOCATORS).on), "")
        text = spelled(on_node(ref.split("#", 1)[0], on_value)) if on_value else ""
    return PATH_VARIABLE.search(text) is None


def _move_lines(
    index: int, step: FlowStep, walk: JourneyWalk, known: _Produced, produced: set[str],
    owners: dict[str, set[str]], gaps: list[Gap], reached: set[str], sent_headers: dict[str, CheckValue],
) -> list[str]:
    """The read-back after a step that moves a record: the target state's endpoint requested as a step would be, then the target's checks on its answer, naming the sibling state that holds when they fail."""
    book = walk.book
    lines: list[str] = []
    credentials = sent_headers if _own_record(step.ref, book) else None
    for number, move in enumerate(book.moves.get(step.ref, ()), start=1):
        target = book.data_states.get(move.end)
        if target is None:
            continue
        observed = f"moved_{index}" if number == 1 else f"moved_{index}_{number}"
        found = read_back(f"step {index}'s read-back", observed, target, book, known, produced, owners, credentials)
        if isinstance(found, str):
            gaps.extend(Gap(oid, "unresolved-precondition", found) for oid in walk.ids)
            continue
        lines.extend(found)
        reached.update((move_obligation_id(step.ref, move.index), state_obligation_id(move.end)))
    return lines


def _checked_with_moves(step: FlowStep, checks: list[str], moves: list[str]) -> list[str]:
    """The step's checks and its read-backs in one `qa.at_node` block, so a failed read-back is recorded against the step and stops the walk there."""
    if not moves:
        return checks
    header = checks[:1] or [f"    with qa.at_node({python_literal(step.ref)}):"]
    return [*header, *checks[1:], *(f"    {line}" for line in moves)]


def _success_claims(ref: str, book: BookIndex) -> list[Obligation]:
    """The claims on *ref* that answer success, the outcome an endpoint step expects."""
    return [claim for claim in book.outcomes_by_node.get(ref, ())
            if (expect_status(claim.checks) or 0) < 400]


def _expanded_steps(walk: JourneyWalk, gaps: list[Gap]) -> tuple[FlowStep, ...] | None:
    """The walk's steps with each passage replaced by the endpoints and cases it runs, or `None` once one passage is not a run of steps."""
    steps: list[FlowStep] = []
    for index, step in enumerate(walk.steps, start=1):
        if step.node_type != "passage":
            steps.append(step)
            continue
        passage = walk.book.passages.get(step.ref)
        if passage is None or passage.start:
            gaps.extend(Gap(oid, "uncompilable-claim",
                            f"step {index} links passage `{step.ref}`, which the packet does not carry as a run of "
                            "endpoints and cases")
                        for oid in walk.ids)
            return None
        steps.extend(FlowStep(ref, "", "invocation" if ref in walk.book.invocation_claims else "endpoint", step.surface)
                     for ref in passage.steps)
    return tuple(steps)


def _http_steps(
    walk: JourneyWalk, sinks: PlanSinks, record_fixtures: frozenset[str] = frozenset(),
) -> _HttpSteps | None:
    """Perform each `endpoint` step as a request, or `None` once one step builds no request."""
    expanded = _expanded_steps(walk, sinks.gaps)
    if expanded is None:
        decline_captures_by_node([s.ref for s in walk.steps], walk.book.captures_by_node, sinks.gaps, sinks.captured,
                                 because="this journey links a passage that is not a run of endpoints and cases")
        return None
    walk = replace(walk, steps=expanded)
    book, gaps = walk.book, sinks.gaps
    lines: list[str] = []
    produced: set[str] = set()
    reached: set[str] = set()
    known = _Produced(captures=produced)
    for obligation in walk.obligations:
        known.record_fixtures(obligation)
    owners = _fixture_owners(walk.obligations)
    observed = last_path = ""
    first_headers: dict[str, CheckValue] | None = None
    refused = expect_status(tuple(row for obligation in walk.obligations for row in obligation.checks))
    if refused is not None and refused >= 400:
        gaps.extend(Gap(oid, "uncompilable-claim", _FLOW_REFUSAL.format(code=refused)) for oid in walk.ids)
        decline_captures_by_node([s.ref for s in walk.steps], book.captures_by_node, gaps, sinks.captured,
                                 because="this journey's own verify: expects a refusal no step links")
        return None
    ended = _ended_path(walk.obligations)
    for index, step in enumerate(walk.steps, start=1):
        outcome = None
        if step.node_type == "invocation" and step.ref in book.invocation_claims:
            found = _invocation_outcome(book.invocation_claims[step.ref])
            if isinstance(found, list):
                gaps.extend(Gap(oid, "uncompilable-claim",
                                f"step {index} links invocation {step.ref}, whose claims expect more than one "
                                f"outcome: statuses {', '.join(str(code) for code in found)}. Link one case per step")
                            for oid in walk.ids)
                decline_captures_by_node([s.ref for s in walk.steps[index - 1:]], book.captures_by_node,
                                         gaps, sinks.captured,
                                         because="this journey links an invocation that expects more than one outcome")
                return None
            outcome = found
        request = _http_request(index, step, book, walk.ids, gaps,
                                ended=ended if index == len(walk.steps) else None, outcome=outcome,
                                rewire=((lambda value: _rewired(value, known, record_fixtures))
                                        if record_fixtures and index == 1 else None))
        unprovided = [] if isinstance(request, _UnbuiltStep) else _unprovided_references(request, known)
        if unprovided:
            gaps.extend(_unprovided_reference_gaps(index, unprovided, walk.ids))
            request = _UnbuiltStep("this journey sends a fact at this step that nothing it runs "
                                   "provides, so it holds no response to capture the field from")
        if isinstance(request, _UnbuiltStep):
            decline_captures_by_node([s.ref for s in walk.steps[index - 1:]], book.captures_by_node,
                                     gaps, sinks.captured, because=request.because)
            return None
        observed, last_path = f"observed_{index}", request.path
        if first_headers is None:
            first_headers = request.sent_headers
        named = {ref.node for ref in request.sent_references if isinstance(ref, references.NodeRef)}
        bound = _bound_path(request.path, produced, owners, named) + (f"?{request.query}" if request.query else "")
        target = (f"qa.resolve({python_literal(bound)})" if references.find_references(bound)
                  else python_literal(bound))
        if outcome is not None:
            expect = f", expect_status={outcome.status}" if outcome.status is not None else ""
        else:
            expect = ""
        lines.append(f"    # okf:{step.ref}")
        call = f"{observed} = qa.http.{request.method.lower()}({target}{expect}{request.kwargs_source})"
        if outcome is not None and outcome.status is not None:
            lines.extend([f"    with qa.at_node({python_literal(step.ref)}):", f"        {call}"])
        else:
            lines.append(f"    {call}")
        if "{" in bound:
            lines.append("    # TODO(arrange): the path above still carries a template variable")
            gaps.extend(Gap(oid, "unresolved-precondition",
                            f"step {index}'s path still carries a template variable")
                        for oid in walk.ids)
        if outcome is not None:
            captures = [OwnedCapture(claim.id, row.name, row.source) for claim in outcome.claims for row in claim.captures]
            lines.extend(_step_captures(observed, captures, sinks, produced))
            lines.extend(_checked_with_moves(
                step, _step_success_checks(index, step, request, observed, walk, known, gaps, outcome.claims),
                _move_lines(index, step, walk, known, produced, owners, gaps, reached, request.sent_headers)))
            continue
        lines.extend(_step_captures(observed, book.captures_by_node.get(step.ref, []), sinks, produced))
        if not expect:
            lines.extend(_checked_with_moves(
                step, _step_success_checks(index, step, request, observed, walk, known, gaps,
                                           _success_claims(step.ref, book)),
                _move_lines(index, step, walk, known, produced, owners, gaps, reached, request.sent_headers)))
    return _HttpSteps(lines, observed, last_path, produced, frozenset(reached), first_headers or {})


def _journey_assertion(
    row: CallRow, oid: str, steps: _HttpSteps, gaps: list[Gap],
) -> str | ScenarioRefusal | None:
    """One flow check asserted on the journey's last response, or why not; `None` once its gaps are filed."""
    named = row.args.get("path")
    if isinstance(named, str) and named.partition("?")[0] != steps.last_path and check_observes(row.name) == "response":
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
    return _verify_line(oid, row, steps.observed)


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
    if not covered:
        return WalkedJourney([*steps.lines, *checks], frozenset())
    return WalkedJourney([*steps.lines, *checks], frozenset(covered | steps.reached), steps.reached)


def move_walk(
    walk: JourneyWalk, start: DataState, sinks: PlanSinks, record_fixtures: frozenset[str] = frozenset(),
) -> WalkedJourney | None:
    """Read the record in *start*, send the one step of *walk*, and hold the state its `moves:` row lands on, or `None` once a gap says why the walk cannot be built."""
    book = walk.book
    known = _Produced()
    for obligation in walk.obligations:
        known.record_fixtures(obligation)
    steps = _http_steps(walk, sinks, record_fixtures)
    if steps is None or not set(walk.ids) <= steps.reached:
        return None
    own = bool(walk.steps) and _own_record(walk.steps[0].ref, book)
    before = read_back("the read of the starting state", "before_move", start, book, known, set(),
                       _fixture_owners(walk.obligations), steps.first_headers if own else None)
    if isinstance(before, str):
        sinks.gaps.extend(Gap(oid, "unresolved-precondition", before) for oid in walk.ids)
        return None
    reached = steps.reached | {state_obligation_id(start.node)}
    lines = [f"    with qa.at_node({python_literal(start.node)}):", *(f"    {line}" for line in before), *steps.lines]
    return WalkedJourney(lines, frozenset(reached), frozenset(reached))


def observe_walk(
    walk_obligations: list[Obligation], state: DataState, book: BookIndex, sinks: PlanSinks,
    record_fixtures: frozenset[str] = frozenset(),
) -> WalkedJourney | None:
    """Read the record the fixtures of *walk_obligations* arrange in *state*, or `None` once a gap says why the walk cannot read it."""
    known = _Produced()
    for obligation in walk_obligations:
        known.record_fixtures(obligation)
    read = read_back("the read of the state", "observed", state, book, known, set(), _fixture_owners(walk_obligations),
                     rewire=True, record_fixtures=record_fixtures)
    if isinstance(read, str):
        sinks.gaps.extend(Gap(obligation.id, "unresolved-precondition", read) for obligation in walk_obligations)
        return None
    lines = [f"    with qa.at_node({python_literal(state.node)}):", *(f"    {line}" for line in read)]
    covered = frozenset({state_obligation_id(state.node)})
    return WalkedJourney(lines, covered, covered)
