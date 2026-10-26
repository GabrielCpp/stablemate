from __future__ import annotations

import ast

from ostler.qa.compile import Plan
from ostler.qa.compile import compile_plan_gaps
from ostler.qa.dispatch import BUILT_TARGETS
from ostler.qa.dispatch import DISPATCH_TABLE

METHOD = "ticket.v1.TicketService/GetTicket"
SOURCE = "docs/services/tickets/rpcs/get-ticket.md"


def _obligation(oid: str, **extra: object) -> dict:
    base = {
        "id": oid, "source": SOURCE, "nodeType": "rpc", "requirement": "answers a ticket",
        "required": True, "locators": {"name": [METHOD]}, "checksDeclared": [],
        "fixturesDeclared": [{"name": "seeded-tickets", "args": [], "provides": "tickets"}],
        "arrangesNothing": True,
    }
    base.update(extra)
    return base


def _context(*obligations: dict, entry_url: str = "grpc://localhost:50051") -> dict:
    return {"story": {"slug": "demo"}, "obligations": list(obligations),
            "navigation": {"": {"driver": "http", "entryUrl": entry_url}}}


def _body(field: str, value: object) -> dict:
    return {"call": f"body(field={field!r}, value={value!r})", "name": "body",
            "args": {"field": field, "value": value}}


def _header(name: str, value: str) -> dict:
    return {"call": f"header(name={name!r}, value={value!r})", "name": "header",
            "args": {"name": name, "value": value}}


def _compile(*obligations: dict) -> tuple[str, list]:
    result = compile_plan_gaps(_context(*obligations), story="demo")
    assert isinstance(result, Plan)
    ast.parse(result.source)
    return result.source, result.gaps


def _kinds(gaps: list, oid: str) -> list[str]:
    return [gap.kind for gap in gaps if gap.obligation_id == oid]


def test_an_rpc_dispatches_to_the_grpc_lane() -> None:
    assert DISPATCH_TABLE["rpc"] == "grpc"
    assert "grpc" in BUILT_TARGETS


def test_a_status_claim_compiles_to_a_call_and_a_grpc_status_check() -> None:
    oid = "okf:tickets-rpc:status:1"
    source, gaps = _compile(_obligation(
        oid, checksDeclared=[{"call": "gone", "name": "grpc_status", "args": {"code": "NOT_FOUND"}}],
        actsDeclared=[_body("id", "t-404")]))
    assert _kinds(gaps, oid) == []
    assert f'qa.grpc.call("{METHOD}", {{"id": "t-404"}}, expect_status="NOT_FOUND")' in source
    assert f'qa.verify("grpc_status", observed_1, code="NOT_FOUND", covers=["{oid}"])' in source
    assert 'base_url="grpc://localhost:50051"' in source


def test_a_read_claim_compiles_to_a_json_path_check_on_the_reply() -> None:
    oid = "okf:tickets-rpc:read:1"
    source, gaps = _compile(_obligation(
        oid, checksDeclared=[{"call": "title", "name": "json_path", "args": {"path": "$.title", "equals": "Printer jam"}}],
        actsDeclared=[_body("id", "t-1")]))
    assert _kinds(gaps, oid) == []
    assert f'qa.grpc.call("{METHOD}", {{"id": "t-1"}})' in source
    assert "observed_1.json()" in source
    assert oid in source


def test_a_claim_with_no_stated_body_is_gapped() -> None:
    oid = "okf:tickets-rpc:nobody:1"
    result = compile_plan_gaps(_context(_obligation(
        oid, checksDeclared=[{"call": "gone", "name": "grpc_status", "args": {"code": "NOT_FOUND"}}])), story="demo")
    gaps = result.gaps
    assert "unarranged-request-body" in _kinds(gaps, oid)


def test_a_header_row_becomes_metadata_and_an_upper_case_reference_a_declared_secret() -> None:
    oid = "okf:tickets-rpc:auth:1"
    source, gaps = _compile(_obligation(
        oid, checksDeclared=[{"call": "gone", "name": "grpc_status", "args": {"code": "NOT_FOUND"}}],
        actsDeclared=[_body("id", "t-404"), _header("authorization", "Bearer $TICKET_TOKEN")]))
    assert _kinds(gaps, oid) == []
    assert 'metadata={"authorization": qa.resolve("Bearer $TICKET_TOKEN")}' in source
    assert 'secret("TICKET_TOKEN", from_env="TICKET_TOKEN")' in source
    assert "import Qa, plan, scenario, target, secret" in source


def test_a_lower_case_reference_nothing_captured_is_a_gap() -> None:
    oid = "okf:tickets-rpc:unbound:1"
    _, gaps = _compile(_obligation(
        oid, checksDeclared=[{"call": "gone", "name": "grpc_status", "args": {"code": "NOT_FOUND"}}],
        actsDeclared=[_body("id", "$ticket_id")]))
    assert "unresolved-precondition" in _kinds(gaps, oid)
