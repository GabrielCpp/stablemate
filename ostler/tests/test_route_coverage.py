"""`route-missing` and `route-phantom`: a server's endpoint pages held against its proto's http routes."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write

SERVER = "docs/services/acme/server.md"
PROTO = """syntax = "proto3";
package acme.v1;

service AcmeService {
  rpc GetWidget(GetRequest) returns (Widget) {
    option (google.api.http) = { get: "/v1/widgets/{widget_id}" };
  }
  rpc ReadWidgets(ReadRequest) returns (Reply) {
    option (google.api.http) = { post: "/v1/widgets:read" body: "*" };
  }
  rpc ListWidgets(ListRequest) returns (Reply) {
    option (google.api.http) = { get: "/v1/widgets" };
  }
  rpc Ping(PingRequest) returns (Reply);
}
"""
ROUTES = (("GET", "/v1/widgets/{widget_id}"), ("POST", "/v1/widgets:read"), ("GET", "/v1/widgets"))


def _server_text(contract: bool, slugs: tuple[str, ...]) -> str:
    bullets = "- contract: proto\n" if contract else ""
    listing = "".join(f"- [{s}]({s}.md)\n" for s in slugs) or "- none\n"
    return (f"---\ntype: server\ntitle: Acme API\n---\n# Acme API\n\n"
            f"- url: http://localhost:8080\n{bullets}\n## Endpoints\n\n{listing}")


def _endpoint_text(method: str, path: str) -> str:
    return (f"---\ntype: endpoint\ntitle: {method} {path}\n---\n# {method} {path}\n\n"
            f"- server: [Acme API](server.md)\n- method: {method}\n- path: `{path}`\n")


def _book(repo: Path, routes: tuple[tuple[str, str], ...], contract: bool = True) -> None:
    write(repo / "proto/acme/v1/acme.proto", PROTO)
    slugs = tuple(f"endpoint-{i}" for i in range(len(routes)))
    write(repo / SERVER, _server_text(contract, slugs))
    for slug, (method, path) in zip(slugs, routes, strict=True):
        write(repo / f"docs/services/acme/{slug}.md", _endpoint_text(method, path))


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def test_an_annotated_route_without_a_page_is_missing(repo: Path) -> None:
    _book(repo, ROUTES[:1])
    missing = _findings(repo, "route-missing")
    assert sorted(f.ref for f in missing) == ["GET /v1/widgets", "POST /v1/widgets:read"]
    assert {f.path for f in missing} == {SERVER}
    assert all(f.severity == "error" for f in missing)
    text = " ".join(f.message for f in missing)
    assert "acme.v1.AcmeService/ReadWidgets" in text
    assert "- method: POST" in text
    assert "- path: /v1/widgets:read" in text


def test_a_fully_booked_server_trips_neither_rule(repo: Path) -> None:
    _book(repo, ROUTES)
    assert _findings(repo, "route-missing") == []
    assert _findings(repo, "route-phantom") == []


def test_a_route_the_proto_lacks_is_a_phantom(repo: Path) -> None:
    _book(repo, (*ROUTES, ("GET", "/v1/gadgets")))
    [phantom] = _findings(repo, "route-phantom")
    assert phantom.ref == "GET /v1/gadgets"
    assert phantom.path == "docs/services/acme/endpoint-3.md"
    assert phantom.severity == "error"


def test_a_phantom_with_the_wrong_method_names_the_annotated_route(repo: Path) -> None:
    _book(repo, (("DELETE", "/v1/widgets/{widget_id}"), *ROUTES[1:]))
    [phantom] = _findings(repo, "route-phantom")
    assert "GET /v1/widgets/{widget_id}" in phantom.message
    [missing] = _findings(repo, "route-missing")
    assert missing.ref == "GET /v1/widgets/{widget_id}"


def test_a_phantom_with_a_close_path_names_the_annotated_route(repo: Path) -> None:
    _book(repo, (("GET", "/v1/widget/{widget_id}"), *ROUTES[1:]))
    [phantom] = _findings(repo, "route-phantom")
    assert "/v1/widgets/{widget_id}" in phantom.message


def test_a_renamed_path_variable_is_the_same_route(repo: Path) -> None:
    _book(repo, (("GET", "/v1/widgets/{id}"), *ROUTES[1:]))
    assert _findings(repo, "route-missing") == []
    assert _findings(repo, "route-phantom") == []


def test_the_method_case_is_ignored(repo: Path) -> None:
    _book(repo, (("get", "/v1/widgets/{widget_id}"), ("Post", "/v1/widgets:read"), ROUTES[2]))
    assert _findings(repo, "route-missing") == []
    assert _findings(repo, "route-phantom") == []


def test_the_custom_verb_suffix_tells_two_routes_apart(repo: Path) -> None:
    _book(repo, (ROUTES[0], ("GET", "/v1/widgets"), ("POST", "/v1/widgets")))
    [missing] = _findings(repo, "route-missing")
    assert missing.ref == "POST /v1/widgets:read"
    [phantom] = _findings(repo, "route-phantom")
    assert phantom.ref == "POST /v1/widgets"


def test_a_server_without_a_contract_gets_no_route_finding(repo: Path) -> None:
    _book(repo, (("GET", "/v1/gadgets"),), contract=False)
    assert _findings(repo, "route-missing") == []
    assert _findings(repo, "route-phantom") == []
