"""`ostler doctor`'s check that a grpc-server's rpc pages book exactly the RPCs its proto contract declares."""

from __future__ import annotations

import re
from pathlib import Path

from ostler import refs as refs_mod, registry
from ostler.finding import Finding
from ostler.links import LinkResolver
from ostler.model import Graph, UINode
from ostler.path import services_root
from ostler.proto_contract import Contract, Service, read_contract
from ostler.provenance import code_ref_root, effective_checkouts
from ostler.server_membership import host_servers
from ostler.source_snapshots import book_repository

_NAME = re.compile(r"[\w.]+(?:/\w+)?")


def _values(node: UINode, key: str) -> list[str]:
    return [name for k, value, _p in node.bullet_order if k == key
            for name in _NAME.findall(value)]


def resolve_contract(graph: Graph, node: UINode, checkouts: dict[str, Path], own_repository: str) -> Contract | None:
    """The contract the page's `contract:` bullet names, or `None` when it names no folder holding a `.proto`."""
    services: list[Service] = []
    found = False
    for ref in refs_mod.code_refs(node.meta.get("contract")):
        try:
            parsed = refs_mod.parse_code_ref(ref)
        except ValueError:
            continue
        root = code_ref_root(graph, parsed, checkouts, own_repository)
        if root is None or not (root / parsed.path).is_dir():
            continue
        contract = read_contract(root / parsed.path)
        found = found or any((root / parsed.path).rglob("*.proto"))
        services.extend(contract.services)
    return Contract(tuple(sorted(services, key=lambda s: s.name))) if found else None


def _intended(name: str, declared: list[str]) -> str:
    """The declared spelling *name* was most likely meant to be, or an empty string."""
    folded = name.casefold()
    for full in declared:
        if full.casefold() == folded:
            return full
    method = name.rpartition("/")[2]
    matches = [full for full in declared if full.rpartition("/")[2] == method]
    return matches[0] if len(matches) == 1 else ""


def check_rpc_coverage(graph: Graph, f: list[Finding], resolver: LinkResolver,
                       checkouts: dict[str, Path] | None = None) -> None:
    """Each declared RPC of a served service has an rpc page, and each rpc page names a declared RPC."""
    servers = graph.ui_nodes_of_type("grpc-server")
    if not servers:
        return
    rpc_type = registry.UI_TYPES_BY_NAME["rpc"]
    hosted: dict[Path, list[UINode]] = {}
    for rpc in graph.ui_nodes_of_type("rpc"):
        if rpc.kind != "file":
            continue
        for host in host_servers(rpc, rpc_type, resolver)[:1]:
            hosted.setdefault(host, []).append(rpc)
    checkout_map = effective_checkouts(checkouts)
    own_repository = book_repository(services_root(graph))
    for server in servers:
        if server.kind != "file":
            continue
        contract = resolve_contract(graph, server, checkout_map, own_repository)
        if contract is None:
            continue
        served = [s for name in _values(server, "serves") if (s := contract.service(name)) is not None]
        declared = [rpc.full_name for s in served for rpc in s.rpcs]
        pages = hosted.get(server.path.resolve(), [])
        booked = {name for page in pages for name in _values(page, "name")}
        for full in declared:
            if full in booked:
                continue
            f.append(Finding(
                "error", "rpc-missing",
                f"{server.id}: the contract declares {full} and no rpc page books it. Write an "
                f"`rpc` page with `- name: {full}` and `- server: [{server.title}]"
                f"({server.path.name})`, and list it under `## RPCs`",
                path=server.id, line=server.line, ref=full))
        for page in pages:
            for name in _values(page, "name"):
                if name in declared:
                    continue
                intended = _intended(name, declared)
                hint = f", the contract spells it {intended}" if intended else ""
                f.append(Finding(
                    "error", "rpc-phantom",
                    f"{page.id}: `name: {name}` is no RPC of the services {server.id} serves"
                    f"{hint}. The name is the full method name exactly as the contract spells it",
                    path=page.id, line=page.line, ref=name))
