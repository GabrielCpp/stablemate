"""What every scenario builder in one plan reads off the whole book, and the base URLs this run resolved for it."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from ostler import registry
from ostler.qa.compile_support import on_href
from ostler.qa.obligation import CallRow
from ostler.qa.obligation import Locators
from ostler.qa.obligation import Obligation
from ostler.qa.plan_source import Gap


@dataclass(frozen=True)
class OwnedCapture:
    """One `capture:` a node declares, tagged with the obligation that owns it."""
    obligation_id: str
    name: str
    source: str


@dataclass(frozen=True)
class BookIndex:
    """The lookups every builder in one plan shares: the book's locators, routes, queries, acts, captures, binaries and fixture pages, and each surface's base URL as this run resolved it."""
    locators_by_node: dict[str, Locators]
    screen_routes: dict[str, str]
    acts_by_node: dict[str, list[CallRow]]
    acts_refused: set[str]
    captures_by_node: dict[str, list[OwnedCapture]]
    cli_binaries: dict[str, str]
    resolved_web_base_urls: dict[str, str]
    resolved_api_base_urls: dict[str, str]
    queries_by_node: dict[str, str] = field(default_factory=dict[str, str])
    claims_by_node: dict[str, list[Obligation]] = field(default_factory=dict[str, list[Obligation]])
    fixture_pages: dict[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])
    hop_acts: dict[tuple[str, str], list[CallRow]] = field(default_factory=dict[tuple[str, str], list[CallRow]])


@dataclass(frozen=True)
class NodeActs:
    """Every node's declared acts in book order, the claims that declare them, and the nodes whose act bullets were refused."""
    by_node: dict[str, list[CallRow]]
    refused: set[str]
    claims_by_node: dict[str, list[Obligation]] = field(default_factory=dict[str, list[Obligation]])


def _is_declared_claim(obligation: Obligation) -> bool:
    """Whether *obligation* is a claim whose node's acts and captures the book index reads."""
    return obligation.kind not in registry.refusal_keys(obligation.node_type)


def node_acts(obligations: list[Obligation]) -> NodeActs:
    """Every node's declared acts in book order, the claims that declare them, and the nodes whose act bullets were refused."""
    rows_by_node: dict[str, list[tuple[tuple[int, ...], int, CallRow]]] = {}
    claims_by_node: dict[str, list[Obligation]] = {}
    refused: set[str] = set()
    for obligation in obligations:
        if not _is_declared_claim(obligation):
            continue
        if obligation.acts_unparsed:
            refused.add(obligation.node)
        if obligation.acts:
            claims_by_node.setdefault(obligation.node, []).append(obligation)
        for index, row in enumerate(obligation.acts):
            rows_by_node.setdefault(obligation.node, []).append((obligation.doc_position, index, row))
    ordered = {
        node_id: list({row.call: row
                       for _, _, row in sorted(rows, key=lambda entry: entry[:2])}.values())
        for node_id, rows in rows_by_node.items()
    }
    claims = {node_id: sorted(owned, key=lambda claim: claim.doc_position) for node_id, owned in claims_by_node.items()}
    return NodeActs(ordered, refused, claims)


def hop_acts(
    obligations: list[Obligation], acts_by_node: dict[str, list[CallRow]],
) -> dict[tuple[str, str], list[CallRow]]:
    """The acts a navigation click needs first, keyed by the component clicked and the page it lands on: those of the first interaction on that component whose checks observe that page."""
    found: dict[tuple[str, str], list[CallRow]] = {}
    for obligation in sorted(obligations, key=lambda o: o.doc_position):
        acts = acts_by_node.get(obligation.node)
        href = on_href(next(iter(obligation.locators.on), ""))
        if obligation.node_type != "interaction" or not acts or not href:
            continue
        component = f"{obligation.source}#{href.lstrip('#')}"
        for row in obligation.checks:
            for target in row.locates.values():
                landed = target.node.split("#")[0]
                if landed and landed != obligation.source:
                    found.setdefault((component, landed), acts)
    return found


def fixture_pages(obligations: list[Obligation], *, rebuilt: frozenset[str] = frozenset()) -> dict[str, frozenset[str]]:
    """Each fixture one lap builds once, and every page whose claims name it; a fixture in *rebuilt* is built for each scenario, so no page shares it."""
    pages: dict[str, set[str]] = {}
    for obligation in obligations:
        if not _is_declared_claim(obligation):
            continue
        for row in obligation.fixtures:
            if row.name in rebuilt:
                continue
            pages.setdefault(row.name, set()).add(obligation.source)
    return {name: frozenset(sources) for name, sources in pages.items()}


def queries_by_node(obligations: list[Obligation]) -> dict[str, str]:
    """Each node's query string: the first one a `path=` check argument of its claims spells, in book order."""
    queries: dict[str, str] = {}
    for obligation in sorted(obligations, key=lambda o: o.doc_position):
        if not _is_declared_claim(obligation) or obligation.node in queries:
            continue
        for row in obligation.checks:
            path = row.args.get("path")
            if isinstance(path, str) and path.startswith("/") and "?" in path:
                queries[obligation.node] = path.partition("?")[2]
                break
    return queries


def captures_by_node(obligations: list[Obligation]) -> dict[str, list[OwnedCapture]]:
    """Every node's declared captures, each tagged with its owning obligation id, in book order."""
    rows_by_node: dict[str, list[tuple[tuple[int, ...], int, OwnedCapture]]] = {}
    for obligation in obligations:
        if not _is_declared_claim(obligation):
            continue
        for index, row in enumerate(obligation.captures):
            capture = OwnedCapture(obligation.id, row.name, row.source)
            rows_by_node.setdefault(obligation.node, []).append((obligation.doc_position, index, capture))
    return {
        node_id: [capture for _, _, capture in sorted(rows, key=lambda entry: entry[:2])]
        for node_id, rows in rows_by_node.items()
    }


def node_locator_index(obligations: list[Obligation]) -> dict[str, Locators]:
    """Every node's own `locators`, keyed by node id, including ones with no *required* claim."""
    index: dict[str, Locators] = {}
    for obligation in obligations:
        if obligation.node and obligation.node not in index:
            index[obligation.node] = obligation.locators
    return index


def decline_captures_by_node(
    node_ids: list[str],
    captures: dict[str, list[OwnedCapture]],
    gaps: list[Gap],
    captured: set[tuple[str, str]],
    *,
    because: str,
) -> None:
    """Gap the captures *captures* attaches to *node_ids*, by node rather than obligation."""
    for node_id in node_ids:
        for capture in captures.get(node_id, []):
            if not capture.name:
                continue
            captured.add((capture.obligation_id, capture.name))
            gaps.append(Gap(
                capture.obligation_id, "uncaptured-declaration",
                f"capture {capture.name!r} from {capture.source!r} is declared on "
                f"this node and {because}",
            ))
