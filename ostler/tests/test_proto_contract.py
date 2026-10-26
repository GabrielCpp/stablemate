"""`proto_contract.read_contract`: services and RPCs read from `.proto` files without protobuf."""

from __future__ import annotations

from pathlib import Path


from conftest import present, write
from ostler import proto_contract

TICKET = '''
syntax = "proto3";
// package fake.ignored;
package ticket.v1;

option go_package = "https://example.com/gen;ticketv1";

/* service Commented { rpc Nope(A) returns (B); } */
service TicketService {
  // rpc Hidden(A) returns (B);
  rpc GetTicket(GetTicketRequest) returns (GetTicketResponse) {
    option (google.api.http) = { post: "/v1/x" body: "*" additional_bindings { get: "/v1/y" } };
  }
  rpc WatchTickets(stream WatchRequest) returns (stream other.v1.Event);
  rpc Upload(stream Chunk) returns (Receipt);
  rpc List(ListRequest) returns (stream ticket.v1.Row) {}
}

message GetTicketRequest { string id = 1; }
'''

BILLING = '''
package billing.v2;
service Billing { rpc Charge (ChargeRequest) returns (ChargeReply); }
'''

BARE = '''
service Greeter { rpc SayHello(HelloRequest) returns (HelloReply); }
'''


def _fixture(root: Path) -> Path:
    write(root / "ticket/v1/ticket.proto", TICKET)
    write(root / "billing.proto", BILLING)
    write(root / "bare/greeter.proto", BARE)
    return root


def test_services_sort_by_name_and_carry_their_package(tmp_path: Path) -> None:
    contract = proto_contract.read_contract(_fixture(tmp_path))
    assert [s.name for s in contract.services] == [
        "Greeter", "billing.v2.Billing", "ticket.v1.TicketService"]


def test_rpcs_keep_file_order_and_ignore_commented_declarations(tmp_path: Path) -> None:
    service = present(proto_contract.read_contract(_fixture(tmp_path)).service("ticket.v1.TicketService"))
    assert [r.name for r in service.rpcs] == ["GetTicket", "WatchTickets", "Upload", "List"]


def test_a_slash_slash_inside_a_string_is_not_a_comment(tmp_path: Path) -> None:
    service = present(proto_contract.read_contract(_fixture(tmp_path)).service("ticket.v1.TicketService"))
    assert service.rpcs[0].full_name == "ticket.v1.TicketService/GetTicket"


def test_an_option_block_with_nested_braces_does_not_end_the_service(tmp_path: Path) -> None:
    service = present(proto_contract.read_contract(_fixture(tmp_path)).service("ticket.v1.TicketService"))
    assert len(service.rpcs) == 4


def test_streaming_shape_and_message_names_are_kept_as_written(tmp_path: Path) -> None:
    service = present(proto_contract.read_contract(_fixture(tmp_path)).service("ticket.v1.TicketService"))
    get, watch, upload, listing = service.rpcs
    assert (get.request, get.response) == ("GetTicketRequest", "GetTicketResponse")
    assert (get.client_streaming, get.server_streaming) == (False, False)
    assert (watch.request, watch.response) == ("WatchRequest", "other.v1.Event")
    assert (watch.client_streaming, watch.server_streaming) == (True, True)
    assert (upload.client_streaming, upload.server_streaming) == (True, False)
    assert (listing.response, listing.client_streaming, listing.server_streaming) == (
        "ticket.v1.Row", False, True)


def test_a_file_without_a_package_names_the_bare_service(tmp_path: Path) -> None:
    service = present(proto_contract.read_contract(_fixture(tmp_path)).service("Greeter"))
    assert service.rpcs[0].full_name == "Greeter/SayHello"


def test_an_unknown_service_is_none(tmp_path: Path) -> None:
    assert proto_contract.read_contract(_fixture(tmp_path)).service("ticket.v1.Nope") is None


def test_a_malformed_file_yields_what_it_parsed_before_the_break(tmp_path: Path) -> None:
    write(tmp_path / "bad.proto", "package p;\nservice S {\n rpc A(X) returns (Y);\n rpc B(X) returns")
    service = present(proto_contract.read_contract(tmp_path).service("p.S"))
    assert [r.name for r in service.rpcs] == ["A"]


def test_an_unreadable_file_is_skipped(tmp_path: Path) -> None:
    write(tmp_path / "good.proto", BILLING)
    (tmp_path / "bin.proto").write_bytes(b"\xff\xfe\x00service")
    assert [s.name for s in proto_contract.read_contract(tmp_path).services] == ["billing.v2.Billing"]


def test_a_missing_folder_reads_as_an_empty_contract(tmp_path: Path) -> None:
    assert proto_contract.read_contract(tmp_path / "absent").services == ()


GATEWAY = '''
package acme.v1;

service AcmeService {
  rpc GetWidget(GetWidgetRequest) returns (Widget) {
    option (google.api.http) = {
      get: "/v1/widgets/{widget_id}"
    };
  }
  rpc CreateWidget(CreateWidgetRequest) returns (Widget) {
    option (google.api.http) = {
      post: "/v1/widgets"
      body: "*"
    };
  }
  rpc UpdateWidget(UpdateWidgetRequest) returns (Widget) {
    option (google.api.http) = {
      put: "/v1/widgets/{widget.id}"
      body: "widget"
    };
  }
  rpc ReopenWidget(ReopenWidgetRequest) returns (Widget) {
    option (google.api.http) = {
      post: "/v1/widgets/{widget_id}:reopen"
      body: "*"
    };
  }
  rpc Ping(PingRequest) returns (PingReply);
  rpc Audit(AuditRequest) returns (AuditReply) {
    option deprecated = true;
  }
  rpc Many(ManyRequest) returns (ManyReply) {
    option (google.api.http) = {
      delete: "/v1/many/{id}"
      additional_bindings { get: "/v1/other/{id}" }
      additional_bindings { custom { kind: "HEAD" path: "/v1/head" } }
    };
  }
}
'''


def _gateway(tmp_path: Path) -> dict[str, proto_contract.Rpc]:
    write(tmp_path / "gateway.proto", GATEWAY)
    service = present(proto_contract.read_contract(tmp_path).service("acme.v1.AcmeService"))
    return {r.name: r for r in service.rpcs}


def test_an_http_option_becomes_a_binding_with_method_path_and_body(tmp_path: Path) -> None:
    rpcs = _gateway(tmp_path)
    assert rpcs["GetWidget"].http == proto_contract.HttpBinding("GET", "/v1/widgets/{widget_id}", "")
    assert rpcs["CreateWidget"].http == proto_contract.HttpBinding("POST", "/v1/widgets", "*")
    assert rpcs["UpdateWidget"].http == proto_contract.HttpBinding("PUT", "/v1/widgets/{widget.id}", "widget")


def test_a_custom_verb_stays_in_the_path(tmp_path: Path) -> None:
    binding = present(_gateway(tmp_path)["ReopenWidget"].http)
    assert binding.path == "/v1/widgets/{widget_id}:reopen"


def test_an_rpc_without_the_option_has_no_binding(tmp_path: Path) -> None:
    rpcs = _gateway(tmp_path)
    assert rpcs["Ping"].http is None
    assert rpcs["Audit"].http is None


def test_additional_bindings_and_custom_are_ignored(tmp_path: Path) -> None:
    assert _gateway(tmp_path)["Many"].http == proto_contract.HttpBinding("DELETE", "/v1/many/{id}", "")
    assert len(_gateway(tmp_path)) == 7
