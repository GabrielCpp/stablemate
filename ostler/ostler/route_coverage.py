"""`ostler doctor`'s check that a server's endpoint pages book exactly the routes its proto contract annotates."""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from ostler import registry
from ostler.finding import Finding
from ostler.links import LinkResolver
from ostler.model import Graph, UINode
from ostler.path import services_root
from ostler.provenance import effective_checkouts
from ostler.rpc_coverage import resolve_contract
from ostler.server_membership import host_servers
from ostler.source_snapshots import book_repository

_VARIABLE = re.compile(r"\{[^{}]*\}")
_CLOSE = 0.8


def _route(method: str, path: str) -> tuple[str, str]:
    """The comparable form of a route: upper-case method, every `{...}` variable as `{}`."""
    return method.strip().upper(), _VARIABLE.sub("{}", path.strip())


def _value(node: UINode, key: str) -> str:
    """The first value of the page's *key* bullet, a backticked span read whole."""
    for k, value, _p in node.bullet_order:
        if k != key:
            continue
        span = re.search(r"`([^`]*)`", value)
        if span:
            return span.group(1).strip()
        words = value.split()
        return words[0] if words else ""
    return ""


def _intended(route: tuple[str, str], declared: dict[tuple[str, str], str]) -> str:
    """The annotated route *route* was most likely meant to be, as the proto spells it, or an empty string."""
    method, path = route
    same_path = [spelt for (m, p), spelt in declared.items() if p == path and m != method]
    if len(same_path) == 1:
        return same_path[0]
    paths = sorted({p for _m, p in declared})
    close = difflib.get_close_matches(path, paths, n=1, cutoff=_CLOSE)
    if not close:
        return ""
    matches = [spelt for (m, p), spelt in declared.items() if p == close[0]]
    same_method = [spelt for (m, p), spelt in declared.items() if p == close[0] and m == method]
    return (same_method or matches)[0]


def check_route_coverage(graph: Graph, f: list[Finding], resolver: LinkResolver,
                         checkouts: dict[str, Path] | None = None) -> None:
    """Each annotated route of a server's contract has an endpoint page, and each endpoint page books an annotated route."""
    servers = [s for s in graph.ui_nodes_of_type("server") if s.kind == "file" and s.meta.get("contract")]
    if not servers:
        return
    endpoint_type = registry.UI_TYPES_BY_NAME["endpoint"]
    hosted: dict[Path, list[UINode]] = {}
    for endpoint in graph.ui_nodes_of_type("endpoint"):
        if endpoint.kind != "file":
            continue
        for host in host_servers(endpoint, endpoint_type, resolver)[:1]:
            hosted.setdefault(host, []).append(endpoint)
    checkout_map = effective_checkouts(checkouts)
    own_repository = book_repository(services_root(graph))
    for server in servers:
        contract = resolve_contract(graph, server, checkout_map, own_repository)
        if contract is None:
            continue
        declared: dict[tuple[str, str], str] = {}
        origin: dict[tuple[str, str], str] = {}
        for service in contract.services:
            for rpc in service.rpcs:
                if rpc.http is None:
                    continue
                key = _route(rpc.http.method, rpc.http.path)
                declared.setdefault(key, f"{rpc.http.method} {rpc.http.path}")
                origin.setdefault(key, rpc.full_name)
        pages = hosted.get(server.path.resolve(), [])
        booked: set[tuple[str, str]] = set()
        for page in pages:
            method, path = _value(page, "method"), _value(page, "path")
            if method and path:
                booked.add(_route(method, path))
        for key, spelt in declared.items():
            if key in booked:
                continue
            method, _, path = spelt.partition(" ")
            f.append(Finding(
                "error", "route-missing",
                f"{server.id}: the contract annotates {spelt} on {origin[key]} and no endpoint page "
                f"books it. Write an `endpoint` page with `- method: {method}` and `- path: {path}` "
                f"and `- server: [{server.title}]({server.path.name})`, and list it under `## Endpoints`",
                path=server.id, line=server.line, ref=spelt))
        for page in pages:
            method, path = _value(page, "method"), _value(page, "path")
            if not method or not path or _route(method, path) in declared:
                continue
            intended = _intended(_route(method, path), declared)
            hint = f", the contract annotates {intended}" if intended else ""
            f.append(Finding(
                "error", "route-phantom",
                f"{page.id}: `{method} {path}` is no route {server.id}'s contract annotates{hint}. "
                f"The method and the path are the `google.api.http` option exactly as the contract spells them",
                path=page.id, line=page.line, ref=f"{method.upper()} {path}"))
