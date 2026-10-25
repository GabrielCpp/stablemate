"""The `grpc-server` and `rpc` node types, their value kinds and their membership checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import doctor, registry, values
from ostler.model import load

from conftest import write

SERVER = "docs/services/acme/grpc/ticket-service.md"
RPC = "docs/services/acme/grpc/get-ticket.md"

SERVER_TEXT = """---
type: grpc-server
title: Ticket service
---
# Ticket service

- entry-url: grpc://localhost:50051
- serves: ticket.v1.TicketService

## RPCs

- [get-ticket](get-ticket.md)
"""

RPC_TEXT = """---
type: rpc
title: get-ticket
---
# get-ticket

- server: [Ticket service](ticket-service.md)
- name: ticket.v1.TicketService/GetTicket
- streaming: unary
- status: NOT_FOUND
"""


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


@pytest.mark.parametrize("name", [
    "OK", "CANCELLED", "UNKNOWN", "INVALID_ARGUMENT", "DEADLINE_EXCEEDED", "NOT_FOUND",
    "ALREADY_EXISTS", "PERMISSION_DENIED", "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION",
    "ABORTED", "OUT_OF_RANGE", "UNIMPLEMENTED", "INTERNAL", "UNAVAILABLE", "DATA_LOSS",
    "UNAUTHENTICATED"])
def test_grpc_code_accepts_each_canonical_name(name: str) -> None:
    assert values.VALUE_KINDS["grpc-code"](name) == ""


@pytest.mark.parametrize("text", ["404", "not_found", "NOT FOUND", "Teapot"])
def test_grpc_code_refuses_anything_else(text: str) -> None:
    assert "canonical" in values.VALUE_KINDS["grpc-code"](text)


def test_grpc_code_reads_the_first_word_of_a_status_claim() -> None:
    assert values.VALUE_KINDS["grpc-code"]("NOT_FOUND when the ticket is unknown") == ""


@pytest.mark.parametrize("text", [
    "ticket.v1.TicketService/GetTicket", "Greeter/SayHello", "a.b_c.v2.Svc/Do"])
def test_rpc_name_accepts_package_service_method(text: str) -> None:
    assert values.VALUE_KINDS["rpc-name"](text) == ""


@pytest.mark.parametrize("text", [
    "ticket.v1.TicketService", "ticket.v1.TicketService/getTicket",
    "Ticket.v1.TicketService/GetTicket", "ticket.v1.ticketService/GetTicket", "/GetTicket"])
def test_rpc_name_refuses_a_malformed_name(text: str) -> None:
    assert values.VALUE_KINDS["rpc-name"](text) != ""


@pytest.mark.parametrize("text", ["grpc://localhost:50051", "grpc://10.0.0.2:9"])
def test_grpc_url_accepts_a_host_and_port(text: str) -> None:
    assert values.VALUE_KINDS["grpc-url"](text) == ""


@pytest.mark.parametrize("text", ["http://localhost:50051", "localhost:50051", "grpc://localhost"])
def test_grpc_url_refuses_the_rest(text: str) -> None:
    assert values.VALUE_KINDS["grpc-url"](text) != ""


def test_the_two_types_are_registered_with_their_shapes() -> None:
    server = registry.UI_TYPES_BY_NAME["grpc-server"]
    rpc = registry.UI_TYPES_BY_NAME["rpc"]
    assert server.context == "grpc"
    assert [s.heading for s in server.required_sections] == ["RPCs"]
    assert rpc.host_page_types == ("grpc-server",)
    assert rpc.heading == "RPCs"
    assert rpc.bullet_keys[0].key == "server"
    launch = {"launch", "entry-url", "health-path", "working-directory", "identity", "stop",
              "boot-timeout"}
    assert launch <= {b.key for b in server.bullet_keys}
    assert registry.LAUNCHABLE_TYPES == frozenset({"server", "grpc-server"})


def test_a_clean_pair_trips_no_membership_finding(repo: Path) -> None:
    write(repo / SERVER, SERVER_TEXT)
    write(repo / RPC, RPC_TEXT)
    for code in ("endpoint-without-server", "unlisted-endpoint", "inline-endpoint",
                 "unparsable-bullet-value", "missing-required-bullet",
                 "missing-required-section"):
        assert _findings(repo, code) == [], code


def test_an_rpc_the_server_does_not_list_is_reported(repo: Path) -> None:
    write(repo / SERVER, SERVER_TEXT.replace("- [get-ticket](get-ticket.md)\n", "- none\n"))
    write(repo / RPC, RPC_TEXT)
    assert len(_findings(repo, "unlisted-endpoint")) == 1


def test_an_rpc_without_a_server_link_is_reported(repo: Path) -> None:
    write(repo / SERVER, SERVER_TEXT)
    write(repo / RPC, RPC_TEXT.replace("- server: [Ticket service](ticket-service.md)\n", ""))
    assert len(_findings(repo, "endpoint-without-server")) == 1


def test_an_rpc_written_inline_is_reported(repo: Path) -> None:
    write(repo / SERVER, SERVER_TEXT.replace(
        "- [get-ticket](get-ticket.md)\n",
        "### get-ticket\n- name: ticket.v1.TicketService/GetTicket\n- streaming: unary\n"))
    assert len(_findings(repo, "inline-endpoint")) == 1


def test_a_bad_status_code_name_is_reported(repo: Path) -> None:
    write(repo / SERVER, SERVER_TEXT)
    write(repo / RPC, RPC_TEXT.replace("NOT_FOUND", "404"))
    found = _findings(repo, "unparsable-bullet-value")
    assert [("#status:" in f.ref) for f in found] == [True]


def test_a_bad_rpc_name_is_reported(repo: Path) -> None:
    write(repo / SERVER, SERVER_TEXT)
    write(repo / RPC, RPC_TEXT.replace("ticket.v1.TicketService/GetTicket", "GetTicket"))
    found = _findings(repo, "unparsable-bullet-value")
    assert [("#name:" in f.ref) for f in found] == [True]


def test_a_server_without_serves_is_reported(repo: Path) -> None:
    write(repo / SERVER, SERVER_TEXT.replace("- serves: ticket.v1.TicketService\n", ""))
    assert len(_findings(repo, "missing-required-bullet")) == 1


def test_an_rpc_without_streaming_is_reported(repo: Path) -> None:
    write(repo / SERVER, SERVER_TEXT)
    write(repo / RPC, RPC_TEXT.replace("- streaming: unary\n", ""))
    assert len(_findings(repo, "missing-required-bullet")) == 1


def test_a_server_without_an_rpcs_section_is_reported(repo: Path) -> None:
    write(repo / SERVER, SERVER_TEXT.split("## RPCs")[0])
    assert len(_findings(repo, "missing-required-section")) == 1
