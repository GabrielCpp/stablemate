"""`rpc-missing` and `rpc-phantom`: a grpc-server's rpc pages held against its proto contract."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write

SERVER = "docs/services/acme/grpc/ticket-service.md"
PROTO = """syntax = "proto3";
package ticket.v1;

service TicketService {
  rpc GetTicket(GetRequest) returns (Ticket);
  rpc ListTickets(ListRequest) returns (stream Ticket);
  rpc CloseTicket(CloseRequest) returns (Ticket);
}
"""
METHODS = ("GetTicket", "ListTickets", "CloseTicket")


def _server_text(contract: bool, pages: tuple[str, ...]) -> str:
    bullets = "- contract: proto\n" if contract else ""
    listing = "".join(f"- [{p}]({p}.md)\n" for p in pages) or "- none\n"
    return (f"---\ntype: grpc-server\ntitle: Ticket service\n---\n# Ticket service\n\n"
            f"- entry-url: grpc://localhost:50051\n- serves: ticket.v1.TicketService\n"
            f"{bullets}\n## RPCs\n\n{listing}")


def _rpc_text(name: str) -> str:
    return (f"---\ntype: rpc\ntitle: {name}\n---\n# {name}\n\n"
            f"- server: [Ticket service](ticket-service.md)\n"
            f"- name: ticket.v1.TicketService/{name}\n- streaming: unary\n")


def _book(repo: Path, names: tuple[str, ...], contract: bool = True) -> None:
    write(repo / "proto/ticket/v1/ticket.proto", PROTO)
    write(repo / SERVER, _server_text(contract, tuple(n.lower() for n in names)))
    for name in names:
        write(repo / f"docs/services/acme/grpc/{name.lower()}.md", _rpc_text(name))


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def test_each_declared_rpc_without_a_page_is_missing(repo: Path) -> None:
    _book(repo, ("GetTicket",))
    missing = _findings(repo, "rpc-missing")
    assert sorted(f.ref for f in missing) == [
        "ticket.v1.TicketService/CloseTicket", "ticket.v1.TicketService/ListTickets"]
    assert {f.path for f in missing} == {SERVER}
    assert all(f.severity == "error" for f in missing)
    assert "- name: ticket.v1.TicketService/CloseTicket" in missing[0].message + missing[1].message


def test_a_fully_booked_server_trips_neither_rule(repo: Path) -> None:
    _book(repo, METHODS)
    assert _findings(repo, "rpc-missing") == []
    assert _findings(repo, "rpc-phantom") == []


def test_a_misspelt_name_is_a_phantom_that_names_the_intended_spelling(repo: Path) -> None:
    _book(repo, ("GetTiket", "ListTickets", "CloseTicket"))
    [phantom] = _findings(repo, "rpc-phantom")
    assert phantom.ref == "ticket.v1.TicketService/GetTiket"
    assert phantom.path == "docs/services/acme/grpc/gettiket.md"
    assert phantom.severity == "error"
    [missing] = _findings(repo, "rpc-missing")
    assert missing.ref == "ticket.v1.TicketService/GetTicket"


def test_a_case_difference_is_a_phantom_that_names_the_declared_spelling(repo: Path) -> None:
    _book(repo, ("getTicket", "ListTickets", "CloseTicket"))
    [phantom] = _findings(repo, "rpc-phantom")
    assert "ticket.v1.TicketService/GetTicket" in phantom.message


def test_a_server_without_a_contract_gets_no_coverage_finding(repo: Path) -> None:
    _book(repo, ("GetTiket",), contract=False)
    assert _findings(repo, "rpc-missing") == []
    assert _findings(repo, "rpc-phantom") == []


def test_a_contract_folder_without_proto_files_gets_no_coverage_finding(repo: Path) -> None:
    _book(repo, ("GetTiket",))
    (repo / "proto/ticket/v1/ticket.proto").unlink()
    assert _findings(repo, "rpc-missing") == []
    assert _findings(repo, "rpc-phantom") == []
