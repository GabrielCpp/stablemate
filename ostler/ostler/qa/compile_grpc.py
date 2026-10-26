"""The rpc half of `compile-plan`: a unary or server-streaming call's claims as grpcurl calls."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ostler.checks import CheckValue
from ostler.qa import references
from ostler.qa.book_index import BookIndex
from ostler.qa.compile_http import Produced
from ostler.qa.compile_http import claim_assertions
from ostler.qa.compile_http import claim_captures
from ostler.qa.compile_http import nested_body_literal
from ostler.qa.compile_http import within_claim
from ostler.qa.compile_journey import api_target
from ostler.qa.compile_support import PYTHON
from ostler.qa.compile_support import bullet_value
from ostler.qa.compile_support import resolved_literal
from ostler.qa.compile_support import unarranged_scenario_gap
from ostler.qa.compile_support import unarranged_state_gap
from ostler.qa.obligation import CallRow
from ostler.qa.obligation import Obligation
from ostler.qa.plan_source import EmittedScenarios
from ostler.qa.plan_source import Gap
from ostler.qa.plan_source import PlanSinks
from ostler.qa.plan_source import SourceScenario
from ostler.qa.plan_source import arrangement_of
from ostler.qa.plan_source import by_source
from ostler.qa.plan_source import claim_scenario_function_name
from ostler.qa.plan_source import python_literal
from ostler.qa.plan_source import scenario_lines
from ostler.qa.plan_source import target_lines

_SECRET_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
_WHOLE_BODY = "$"
_REFUSED = ("UNAUTHENTICATED", "PERMISSION_DENIED")


@dataclass(frozen=True)
class GrpcScenarios:
    """The compiled rpc scenarios and the secrets their metadata names."""
    lines: list[str]
    secrets: list[str]


@dataclass(frozen=True)
class _Trigger:
    """The second call a claim makes while its stream is open."""
    method: str
    request: dict[str, object]


@dataclass(frozen=True)
class _Arrangement:
    """What a claim's acts put on the wire: the request members, whether it carries none, its metadata and the call made while its stream is open."""
    body: dict[str, CheckValue]
    metadata: dict[str, CheckValue]
    bodiless: bool
    trigger: _Trigger | None = None

    def states_body(self) -> bool:
        return bool(self.body) or self.bodiless

    def named_references(self) -> list[references.Reference]:
        values = [*self.body.values(), *self.metadata.values()]
        if self.trigger is not None:
            values.extend(_string_leaves(self.trigger.request))
        return [ref for value in values if isinstance(value, str) for ref in references.find_references(value)]


def _string_leaves(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [leaf for item in value.values() for leaf in _string_leaves(item)]
    if isinstance(value, list):
        return [leaf for item in value for leaf in _string_leaves(item)]
    return []


def _json_literal(value: object) -> str:
    """A trigger request member as Python source, each string leaf resolved through `qa.resolve_body` when it names a reference."""
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(key)}: {_json_literal(item)}" for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_json_literal(item) for item in value) + "]"
    if isinstance(value, str):
        return resolved_literal(value, "resolve_body")
    return python_literal(value)


def _node_credentials(obligations: list[Obligation], book: BookIndex) -> dict[str, tuple[CallRow, ...]]:
    nodes = dict.fromkeys(obligation.node for obligation in obligations)
    values: dict[str, dict[str, set[str]]] = {}
    rows: dict[str, dict[str, CallRow]] = {}
    for node in nodes:
        for claim in book.claims_by_node.get(node, []):
            if not node or expect_code(claim.checks) in _REFUSED:
                continue
            for row in claim.acts:
                if row.name != "header":
                    continue
                name = row.text_arg("name")
                values.setdefault(node, {}).setdefault(name, set()).add(row.text_arg("value"))
                rows.setdefault(node, {}).setdefault(name, row)
    return {node: tuple(row for name, row in by_name.items() if len(values[node][name]) == 1)
            for node, by_name in rows.items()}


def _claim_acts(obligation: Obligation, credentials: tuple[CallRow, ...]) -> tuple[CallRow, ...]:
    if expect_code(obligation.checks) == "UNAUTHENTICATED":
        return obligation.acts
    own = {row.text_arg("name") for row in obligation.acts if row.name == "header"}
    return (*obligation.acts, *(row for row in credentials if row.text_arg("name") not in own))


def _trigger(rows: list[CallRow]) -> _Trigger | str | None:
    """The call a claim's `while_open` row names, or why the claim cannot compile."""
    if not rows:
        return None
    if len(rows) > 1:
        return "the claim states more than one while_open, and a stream is opened with a single trigger"
    row = rows[0]
    method = bullet_value(row.text_arg("method"))
    if method is None:
        return "the while_open act names no method"
    try:
        request = json.loads(row.text_arg("request") or "{}")
    except json.JSONDecodeError as exc:
        return f"the while_open request is not valid JSON: {exc.msg}"
    if not isinstance(request, dict):
        return "the while_open request is not a JSON object"
    return _Trigger(method, request)


def _arrangement(rows: tuple[CallRow, ...]) -> _Arrangement | str | None:
    body: dict[str, CheckValue] = {}
    metadata: dict[str, CheckValue] = {}
    bodiless = False
    opened: list[CallRow] = []
    for row in rows:
        if row.name == "while_open":
            opened.append(row)
        elif row.name == "no_body":
            bodiless = True
        elif row.name == "header":
            metadata[row.text_arg("name")] = row.text_arg("value")
        elif row.name == "body":
            body[row.text_arg("field")] = row.args.get("value", "")
        else:
            return None
    if any(other.startswith(f"{key}.") for key in body for other in body):
        return None
    if _WHOLE_BODY in body and len(body) > 1:
        return None
    if bodiless and body:
        return None
    trigger = _trigger(opened)
    if isinstance(trigger, str):
        return trigger
    return _Arrangement(body, metadata, bodiless, trigger)


def expect_code(rows: tuple[CallRow, ...]) -> str | None:
    """The status name a declared `grpc_status` check expects."""
    for row in rows:
        if row.name == "grpc_status":
            code = row.args.get("code")
            if isinstance(code, str):
                return code
    return None


def _secret_names(arranged: _Arrangement, produced: Produced) -> list[str]:
    return [ref.name for ref in arranged.named_references()
            if isinstance(ref, references.CaptureRef) and ref.name not in produced.captures
            and _SECRET_NAME.match(ref.name)]


@dataclass(frozen=True)
class _Call:
    line: str
    secrets: list[str]


def _call(
    obligation: Obligation, observed: str, produced: Produced, gaps: list[Gap],
    credentials: tuple[CallRow, ...] = (),
) -> _Call | Gap:
    method = bullet_value(next(iter(obligation.locators.name), None))
    if method is None:
        return Gap(obligation.id, "uncompilable-claim", "the book gives this rpc no `name:` to call")
    status = expect_code(obligation.checks)
    rows = _claim_acts(obligation, credentials)
    arranged = None if (not rows or obligation.acts_unparsed) else _arrangement(rows)
    if isinstance(arranged, str):
        return Gap(obligation.id, "uncompilable-claim", arranged)
    if arranged is None or not arranged.states_body():
        return Gap(obligation.id, "unarranged-request-body", "the book carries no request body")
    streams = bullet_value(next(iter(obligation.locators.streaming), None)) == "server"
    if arranged.trigger is not None and not streams:
        return Gap(obligation.id, "uncompilable-claim", "the while_open act needs a server-streaming rpc")
    secrets = _secret_names(arranged, produced)
    gaps.extend(Gap(obligation.id, "unresolved-precondition",
                    f"the request references {ref!r}, not resolvable without running the plan")
                for ref in arranged.named_references()
                if not produced.resolves(ref) and not (isinstance(ref, references.CaptureRef) and ref.name in secrets))
    request = "None" if arranged.bodiless else nested_body_literal(arranged.body)
    expect = f", expect_status={python_literal(status)}" if status is not None else ""
    meta = ""
    if arranged.metadata:
        members = ", ".join(f"{python_literal(k)}: {resolved_literal(v)}" for k, v in arranged.metadata.items())
        meta = f", metadata={{{members}}}"
    if not streams:
        return _Call(f"    {observed} = qa.grpc.call({python_literal(method)}, {request}{expect}{meta})", secrets)
    during = ""
    if arranged.trigger is not None:
        during = (f", during=({python_literal(arranged.trigger.method)}, "
                  f"{_json_literal(arranged.trigger.request)})")
    return _Call(f"    {observed} = qa.grpc.stream({python_literal(method)}, {request}{during}{expect}{meta})", secrets)


def _scenario_body(
    obligations: list[Obligation], gaps: list[Gap], covered: set[str], captured: set[tuple[str, str]],
    secrets: list[str], credentials: dict[str, tuple[CallRow, ...]],
) -> list[str]:
    lines: list[str] = []
    produced = Produced()
    for index, obligation in enumerate(sorted(obligations, key=lambda o: o.doc_position), start=1):
        oid = obligation.id
        observed = f"observed_{index}"
        lines.extend(["", f"    # {oid}", f"    # {' '.join(obligation.requirement.split())}"])
        produced.record_fixtures(obligation)
        built = _call(obligation, observed, produced, gaps, credentials.get(obligation.node, ()))
        if isinstance(built, Gap):
            gaps.append(built)
            lines.extend([f"    # TODO(arrange): {built.detail}"])
            continue
        secrets.extend(name for name in built.secrets if name not in secrets)
        claim_lines = [built.line]
        claim_lines.extend(claim_captures(obligation, observed, produced, gaps, captured))
        asserted = claim_assertions(obligation, observed, produced, gaps)
        claim_lines.extend(asserted.todos or asserted.assertions)
        lines.extend(within_claim(oid, claim_lines))
        if not asserted.todos:
            covered.add(oid)
    return lines


def grpc_scenarios(
    owed: list[Obligation], book: BookIndex, sinks: PlanSinks, emitted: EmittedScenarios,
) -> GrpcScenarios:
    """One scenario per book page whose rpcs owe live evidence, each called through grpcurl."""
    lines: list[str] = []
    secrets: list[str] = []
    credentials = _node_credentials(owed, book)
    for source, obligations in by_source(owed).items():
        sinks.gaps.extend(unarranged_state_gap(o) for o in obligations if not o.checks)
        declared = [o for o in obligations if o.checks]
        if not declared:
            continue
        arrangement = arrangement_of(declared)
        if arrangement.unstated:
            sinks.gaps.extend(unarranged_scenario_gap(o) for o in declared)
            continue
        covered: set[str] = set()
        body = _scenario_body(declared, sinks.gaps, covered, sinks.captured, secrets, credentials)
        if not covered:
            continue
        emitted.covered.update(covered)
        target_var, base_url = api_target(obligations[0].surface, source, book)
        target_var = _grpc_var(target_var)
        lines.extend(target_lines(target_var, PYTHON.name, f", base_url={python_literal(base_url)}", emitted))
        scenario = SourceScenario(
            source, target_var, [o.id for o in declared if o.id in covered], arrangement, body)
        lines.extend(scenario_lines(scenario, claim_scenario_function_name(scenario, emitted)))
    return GrpcScenarios(lines, secrets)


def _grpc_var(target_var: str) -> str:
    return target_var.removesuffix("_api") + "_grpc" if target_var.endswith("_api") else target_var


__all__ = ["GrpcScenarios", "expect_code", "grpc_scenarios"]
