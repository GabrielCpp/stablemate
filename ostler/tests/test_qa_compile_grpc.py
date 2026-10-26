from __future__ import annotations

import ast

import pytest

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


def _on_node(oid: str, **extra: object) -> dict:
    return _obligation(oid, node="okf:tickets-rpc:get-ticket", **extra)


def _refused(code: str) -> list:
    return [{"call": "refused", "name": "grpc_status", "args": {"code": code}}]


def test_a_header_one_claim_arranges_reaches_every_claim_of_the_rpc() -> None:
    first, second = "okf:tickets-rpc:one:1", "okf:tickets-rpc:two:2"
    source, gaps = _compile(
        _on_node(first, checksDeclared=[{"call": "x", "name": "json_path", "args": {"path": "$.title", "equals": "A"}}],
                 actsDeclared=[_body("id", "t-1"), _header("authorization", "Bearer $TICKET_TOKEN")]),
        _on_node(second, checksDeclared=_refused("NOT_FOUND"), actsDeclared=[_body("id", "t-0")]))
    assert _kinds(gaps, first) == [] and _kinds(gaps, second) == []
    assert source.count('metadata={"authorization": qa.resolve("Bearer $TICKET_TOKEN")}') == 2


def test_a_claim_expecting_unauthenticated_sends_none_of_the_shared_headers() -> None:
    first, second = "okf:tickets-rpc:one:1", "okf:tickets-rpc:two:2"
    source, _ = _compile(
        _on_node(first, checksDeclared=_refused("NOT_FOUND"),
                 actsDeclared=[_body("id", "t-0"), _header("authorization", "Bearer $TICKET_TOKEN")]),
        _on_node(second, checksDeclared=_refused("UNAUTHENTICATED"), actsDeclared=[_body("id", "t-1")]))
    assert source.count("metadata=") == 1


def test_a_header_two_claims_set_apart_is_not_shared() -> None:
    first, second, third = "okf:tickets-rpc:one:1", "okf:tickets-rpc:two:2", "okf:tickets-rpc:three:3"
    source, _ = _compile(
        _on_node(first, checksDeclared=_refused("NOT_FOUND"),
                 actsDeclared=[_body("id", "t-0"), _header("authorization", "Bearer $A_TOKEN")]),
        _on_node(second, checksDeclared=_refused("NOT_FOUND"),
                 actsDeclared=[_body("id", "t-1"), _header("authorization", "Bearer $B_TOKEN")]),
        _on_node(third, checksDeclared=_refused("NOT_FOUND"), actsDeclared=[_body("id", "t-2")]))
    assert source.count("metadata=") == 2


STREAM = "notes.v1.NoteService/Stream"
SEND = "notes.v1.NoteService/Send"


def _while_open(method: str = SEND, request: str | None = '{"title": "hi", "to": "@seed.user"}') -> dict:
    args = {"method": method} if request is None else {"method": method, "request": request}
    return {"call": f"while_open(method={method!r})", "name": "while_open", "args": args}


def _no_body() -> dict:
    return {"call": "no_body()", "name": "no_body", "args": {}}


def _stream_obligation(oid: str, *, streaming: str = "server", **extra: object) -> dict:
    return _obligation(
        oid, locators={"name": [STREAM], "streaming": [streaming]},
        fixturesDeclared=[{"name": "seeded", "args": [], "provides": "a user", "providesKeys": ["seed.user"]}], **extra)


def _gaps(*obligations: dict) -> list:
    return compile_plan_gaps(_context(*obligations), story="demo").gaps


def _delivered(count: int = 1) -> list[dict]:
    return [{"call": "n", "name": "message_count", "args": {"path": "note", "equals": count}}]


def test_a_server_stream_claim_with_a_trigger_compiles_to_a_stream_during_a_call() -> None:
    oid = "okf:notes-rpc:delivers:1"
    source, gaps = _compile(_stream_obligation(
        oid, checksDeclared=_delivered(), actsDeclared=[_no_body(), _while_open()]))
    assert _kinds(gaps, oid) == []
    assert (f'qa.grpc.stream("{STREAM}", None, during=("{SEND}", '
            '{"title": "hi", "to": qa.resolve_body("@seed.user")}))') in source
    assert f'qa.verify("message_count", observed_1, path="note", equals=1, covers=["{oid}"])' in source


def test_a_server_stream_claim_without_a_trigger_compiles_to_a_plain_stream() -> None:
    oid = "okf:notes-rpc:refused:1"
    source, gaps = _compile(_stream_obligation(
        oid, checksDeclared=[{"call": "gone", "name": "grpc_status", "args": {"code": "UNAUTHENTICATED"}}],
        actsDeclared=[_no_body()]))
    assert _kinds(gaps, oid) == []
    assert f'qa.grpc.stream("{STREAM}", None, expect_status="UNAUTHENTICATED")' in source
    assert "during=" not in source


def test_a_stream_trigger_carries_the_metadata_of_the_claim() -> None:
    oid = "okf:notes-rpc:auth:1"
    source, _ = _compile(_stream_obligation(
        oid, checksDeclared=_delivered(),
        actsDeclared=[_no_body(), _while_open(request=None), _header("authorization", "Bearer $NOTE_TOKEN")]))
    assert (f'qa.grpc.stream("{STREAM}", None, during=("{SEND}", {{}}), '
            'metadata={"authorization": qa.resolve("Bearer $NOTE_TOKEN")})') in source
    assert 'secret("NOTE_TOKEN", from_env="NOTE_TOKEN")' in source


def test_a_unary_rpc_still_compiles_to_a_call_whatever_its_streaming_bullet_says() -> None:
    oid = "okf:tickets-rpc:unary:1"
    source, _ = _compile(_obligation(
        oid, locators={"name": [METHOD], "streaming": ["unary"]},
        checksDeclared=[{"call": "gone", "name": "grpc_status", "args": {"code": "NOT_FOUND"}}],
        actsDeclared=[_body("id", "t-404")]))
    assert f'qa.grpc.call("{METHOD}", {{"id": "t-404"}}, expect_status="NOT_FOUND")' in source
    assert "qa.grpc.stream" not in source


def test_two_while_open_rows_are_an_uncompilable_claim() -> None:
    oid = "okf:notes-rpc:two:1"
    gaps = _gaps(_stream_obligation(
        oid, checksDeclared=_delivered(), actsDeclared=[_no_body(), _while_open(), _while_open()]))
    assert "uncompilable-claim" in _kinds(gaps, oid)


@pytest.mark.parametrize("request_text", ["{not json", "[1, 2]", '"text"'])
def test_a_trigger_request_that_is_not_a_json_object_is_an_uncompilable_claim(request_text: str) -> None:
    oid = "okf:notes-rpc:badjson:1"
    gaps = _gaps(_stream_obligation(
        oid, checksDeclared=_delivered(), actsDeclared=[_no_body(), _while_open(request=request_text)]))
    assert "uncompilable-claim" in _kinds(gaps, oid)


def test_while_open_on_a_unary_rpc_is_an_uncompilable_claim_that_names_the_stream() -> None:
    oid = "okf:tickets-rpc:wrong:1"
    result = compile_plan_gaps(_context(_obligation(
        oid, locators={"name": [METHOD], "streaming": ["unary"]},
        checksDeclared=[{"call": "gone", "name": "grpc_status", "args": {"code": "NOT_FOUND"}}],
        actsDeclared=[_body("id", "t-1"), _while_open()])), story="demo")
    gap = next(g for g in result.gaps if g.obligation_id == oid and g.kind == "uncompilable-claim")
    assert "server-streaming" in gap.detail


def test_an_unresolvable_reference_in_a_trigger_request_is_a_gap() -> None:
    oid = "okf:notes-rpc:unbound:1"
    _, gaps = _compile(_stream_obligation(
        oid, checksDeclared=_delivered(),
        actsDeclared=[_no_body(), _while_open(request='{"to": "$user_id"}')]))
    assert "unresolved-precondition" in _kinds(gaps, oid)


def test_a_secret_in_a_trigger_request_is_declared() -> None:
    oid = "okf:notes-rpc:secret:1"
    source, gaps = _compile(_stream_obligation(
        oid, checksDeclared=_delivered(),
        actsDeclared=[_no_body(), _while_open(request='{"key": "$NOTE_KEY"}')]))
    assert _kinds(gaps, oid) == []
    assert 'secret("NOTE_KEY", from_env="NOTE_KEY")' in source
