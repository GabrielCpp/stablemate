"""The endpoint half of `compile-plan`: a route's claims as HTTP calls, and a journey walked as requests."""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from typing import Any

from ostler import acts as acts_mod
from ostler.checks import CheckValue
from ostler.checks import _rooted
from ostler.qa import references
from ostler.qa.book_index import BookIndex
from ostler.qa.book_index import OwnedCapture
from ostler.qa.book_index import decline_captures_by_node
from ostler.qa.compile_journey import JourneyWalk
from ostler.qa.compile_journey import WalkedJourney
from ostler.qa.compile_journey import api_target
from ostler.qa.compile_support import PYTHON
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


def _request_path(template: str, rows: tuple[CallRow, ...]) -> str:
    """The path a claim requests: a declared check's real path, unless it drops a reference the route names and names no other in its place."""
    concrete = _concrete_path(rows)
    if concrete is None:
        return template
    routed, checked = set(references.find_references(template)), set(references.find_references(concrete))
    if routed - checked and not checked - routed:
        return template
    return concrete


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
    route = _route(obligation.locators)
    status = _expect_status(obligation.checks)
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
        status = _expect_status(obligation.checks)
        if obligation.node and status is not None:
            stated.setdefault(_request_key(obligation), set()).add(status)
    return {key: next(iter(codes)) for key, codes in stated.items() if len(codes) == 1}


def _claim_status(obligation: Obligation, stated: int | None) -> int | None:
    """The status a claim expects: its own `http_status`, else the one *stated* by the claims sending the same request."""
    own = _expect_status(obligation.checks)
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
    route = _route(obligation.locators)
    status = _expect_status(obligation.checks)
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
        operand = operand_for(row.name, observed, row.args)
        if isinstance(operand, ScenarioRefusal):
            todos.append(f"    # TODO(arrange): {operand.detail}")
            gaps.append(Gap(oid, operand.kind, operand.detail))
            continue
        assertions.append(
            f"    qa.verify({python_literal(row.name)}, {operand}{call_kwargs(row.args)}, covers=[{python_literal(oid)}])"
        )
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


@dataclass(frozen=True)
class _UnbuiltStep:
    """A journey step that compiled no request, and why its downstream captures are declined."""
    because: str


def _step_arrangement(ref: str, node_rows: list[CallRow], book: BookIndex) -> _HttpArrangement | None:
    """What one journey step sends: the acts of every claim on its node that expects no refusal, merged, else the first success claim's own acts when those claims arrange a field differently."""
    refusing = {row.call for claim in book.claims_by_node.get(ref, ()) if (_expect_status(claim.checks) or 0) >= 400
                for row in claim.acts}
    admitted = {row.call for claim in book.claims_by_node.get(ref, ()) if (_expect_status(claim.checks) or 0) < 400
                for row in claim.acts}
    merged = _http_arrangement(tuple(row for row in node_rows if row.call in admitted or row.call not in refusing))
    if merged is not None:
        return merged
    for claim in book.claims_by_node.get(ref, ()):
        status = _expect_status(claim.checks)
        if status is not None and 200 <= status < 300:
            return _http_arrangement(claim.acts, later_replaces=True)
    return None


def _http_request(
    index: int, step: FlowStep, book: BookIndex, ids: list[str], gaps: list[Gap], ended: str | None = None,
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
    if "*" in path:
        candidates = (ended, book.checked_paths_by_node.get(ref))
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
    query = "" if "?" in path else book.queries_by_node.get(ref, "")
    node_rows = book.acts_by_node.get(ref, [])
    arranged = (None if (ref in book.acts_refused or not node_rows)
                else _step_arrangement(ref, node_rows, book))
    sent_references = (*(arranged.named_references() if arranged else ()), *references.find_references(query))
    if method in _BODILESS_METHODS:
        return _HttpRequest(method, path, arranged.kwargs_source(with_body=False) if arranged else "", sent_references, query)
    if arranged is None or not arranged.states_body():
        gaps.extend(Gap(oid, "unarranged-request-body",
                        f"step {index} is a {method} and the book carries no request body")
                    for oid in ids)
        return _UnbuiltStep("this journey could not build this step's request body, so it "
                            "holds no response to capture the field from")
    return _HttpRequest(method, path, arranged.kwargs_source(with_body=True), sent_references, query)


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


_PATH_VARIABLE = re.compile(r"\{([a-zA-Z0-9][a-zA-Z0-9_-]*)\}(?![\w-])")


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
    return _PATH_VARIABLE.sub(bind, path)


def _refused_status(obligations: list[Obligation]) -> int | None:
    """The error status a flow's own `http_status` check expects its last step to answer with, when it expects one."""
    status = _expect_status(tuple(row for obligation in obligations for row in obligation.checks))
    return status if status is not None and status >= 400 else None


def _ended_path(obligations: list[Obligation]) -> str | None:
    """The address a flow's own response check names, without its query: the one its last step must request."""
    for obligation in obligations:
        for row in obligation.checks:
            named = row.args.get("path")
            if isinstance(named, str) and check_observes(row.name) == "response":
                return named.partition("?")[0]
    return None


def _http_steps(walk: JourneyWalk, sinks: PlanSinks) -> _HttpSteps | None:
    """Perform each `endpoint` step as a request, or `None` once one step builds no request."""
    book, gaps = walk.book, sinks.gaps
    lines: list[str] = []
    produced: set[str] = set()
    known = _Produced(captures=produced)
    for obligation in walk.obligations:
        known.record_fixtures(obligation)
    owners = _fixture_owners(walk.obligations)
    observed = last_path = ""
    refused_status = _refused_status(walk.obligations)
    ended = _ended_path(walk.obligations)
    for index, step in enumerate(walk.steps, start=1):
        request = _http_request(index, step, book, walk.ids, gaps,
                                ended=ended if index == len(walk.steps) else None)
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
        named = {ref.node for ref in request.sent_references if isinstance(ref, references.NodeRef)}
        bound = _bound_path(request.path, produced, owners, named) + (f"?{request.query}" if request.query else "")
        target = (f"qa.resolve({python_literal(bound)})" if references.find_references(bound)
                  else python_literal(bound))
        expect = f", expect_status={refused_status}" if refused_status is not None and index == len(walk.steps) else ""
        lines.append(f"    # okf:{step.ref}")
        lines.append(f"    {observed} = qa.http.{request.method.lower()}({target}{expect}{request.kwargs_source})")
        if "{" in bound:
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
    operand = operand_for(row.name, steps.observed, row.args)
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
