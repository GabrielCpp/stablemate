"""What a flow step may say and what an outcome must check: the rules `ostler doctor` holds a request's claims to."""

from __future__ import annotations

from collections.abc import Mapping

from ostler import markdown, refs as refs_mod, registry
from ostler.finding import Finding
from ostler.qa.compile_http import case_status, expect_status, route_of
from ostler.qa.context import node_obligations
from ostler.qa.obligation import Obligation, obligation_of
from ostler.qa.obligation_frame import BookNode, book_nodes

_MUTATING = ("POST", "PUT", "PATCH", "DELETE")
_BODYLESS = (204, 304)
_SHOWN = 80


def _page_of(node: BookNode) -> str:
    return node.id.split("#", 1)[0]


def _claims(node: BookNode, book: Mapping[str, BookNode]) -> list[Obligation]:
    return [claim for raw in node_obligations(node, [], journey=False, book=book)
            if (claim := obligation_of(raw)).node_type != "move"]


def _shown(text: str) -> str:
    return text if len(text) <= _SHOWN else text[:_SHOWN] + "..."


def _check_steps(flow: BookNode, f: list[Finding]) -> None:
    for number, child in enumerate(flow.bullets.get("steps", ()), start=1):
        left = markdown.text_beside_links(child)
        if not any(char.isalpha() for char in left):
            continue
        fix = "Move the sentence to a does: or verify: on the node the step links, and keep only the link."
        f.append(Finding(
            "error", "step-claim",
            f"{flow.id}: step {number} says \"{_shown(left)}\" beside its link. A step names what it performs and "
            f"states nothing about the result. {fix}",
            path=_page_of(flow), line=flow.line, ref=refs_mod.bullet_ref(flow.id, "steps"), suggestion=fix))


def _outcomes(claims: list[Obligation], node_type: str) -> dict[int | None, list[Obligation]]:
    refusing = registry.refusal_keys(node_type)
    stated = {status for claim in claims if (status := case_status(claim)) is not None}
    refused = {status for status in stated if status >= 400}
    unkeyed = next(iter(refused)) if node_type == "invocation" and len(refused) == len(stated) == 1 else None
    outcomes: dict[int | None, list[Obligation]] = {}
    for claim in claims:
        status = case_status(claim)
        if claim.kind in refusing and status is None:
            continue
        key = unkeyed if status is None or status < 400 else status
        outcomes.setdefault(key, []).append(claim)
    return outcomes


def _success_status(claims: list[Obligation]) -> int | None:
    stated = sorted({status for claim in claims if (status := case_status(claim)) is not None})
    return stated[0] if stated else None


def _check_outcomes(node: BookNode, claims: list[Obligation], f: list[Finding]) -> None:
    if not claims:
        return
    route = route_of(claims[0].locators)
    bodyless = route is not None and route[0] == "HEAD"
    for key, owned in _outcomes(claims, node.type).items():
        found = [row for claim in owned for row in claim.checks]
        status = _success_status(owned) if key is None else key
        if not found or any(row.name != "http_status" for row in found) or bodyless or status in _BODYLESS:
            continue
        shown = status if status is not None else expect_status(tuple(found))
        ref = refs_mod.bullet_ref(node.id, "verify") if "verify" in node.bullets else node.id
        fix = ("Add a verify: under it that reads the body, such as json_path(path=\"$.id\", matches=\"...\"), "
               "or a header it sets.")
        f.append(Finding(
            "error", "status-only-outcome",
            f"{node.id}: the {shown} outcome checks only its status code, so a wrong body passes. {fix}",
            path=_page_of(node), line=node.line, ref=ref, suggestion=fix))


def _method_of(node: BookNode, book: Mapping[str, BookNode]) -> str:
    claims = _claims(node, book)
    route = route_of(claims[0].locators) if claims else None
    return route[0] if route is not None else ""


def _check_moves(node: BookNode, claims: list[Obligation], book: Mapping[str, BookNode], f: list[Finding]) -> None:
    if "moves" in node.bullets:
        return
    if node.type == "endpoint":
        method = _method_of(node, book)
    else:
        methods = [_method_of(target, book) for target in node.targets("on", book) if target.type == "endpoint"]
        method = next((name for name in methods if name in _MUTATING), "")
        refusals = registry.refusal_keys("invocation")
        stated = [claim for claim in claims if claim.kind not in (*refusals, "contract", "when")]
        succeeds = any((status := case_status(claim)) is not None and status < 400 for claim in stated) or (
            bool(stated) and not any(claim.kind in refusals for claim in claims))
        if not succeeds:
            return
    if method not in _MUTATING:
        return
    fix = ("Add - moves: [from](#a) to [to](#b), - moves: to [to](#b), or - moves: none, because <reason>.")
    f.append(Finding(
        "error", "unstated-move",
        f"{node.id}: a {method} request changes what the server keeps, and the page names no moves:. {fix}",
        path=_page_of(node), line=node.line, ref=node.id, suggestion=fix))


def check_outcomes(data: dict, f: list[Finding]) -> None:
    """A flow step states no result, each outcome of a request checks more than its status, and each write names what it moves."""
    book = book_nodes({node["id"]: node for node in data["nodes"]})
    for node in book.values():
        if node.type == "flow":
            _check_steps(node, f)
        elif node.type in ("endpoint", "invocation"):
            claims = _claims(node, book)
            _check_outcomes(node, claims, f)
            _check_moves(node, claims, book, f)
