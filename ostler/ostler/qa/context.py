"""Deterministic changed-code to OKF obligation mapping."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter
from unidiff.patch import PatchSet
from unidiff.errors import UnidiffParseError

from ostler import graph as graph_mod
from ostler import locators as locators_mod
from ostler import acts as acts_mod
from ostler import checks as checks_mod
from ostler import inventory, markdown, path as path_mod, refs as refs_mod, registry, syntax
from ostler.model import Graph, _parse_ui_nodes, load
from ostler.pages import files_in_book
from ostler import reach
from ostler import routes as routes_mod
from ostler.qa import captures as captures_mod
from ostler.qa.dispatch import owes_live_evidence
from ostler.qa.fixture_browser import BROWSER_KEYS
from ostler.qa import fixtures as fixtures_mod
from ostler.qa.compile import annotate_deferred_obligations
from ostler.qa.obligation_frame import (
    BookNode,
    RepeatContract,
    book_nodes,
    declared_locators,
    linked_surface,
    obligation_frame,
    resolve_extends,
)
from ostler.qa.outcome import QaOutcome
from ostler.qa.grounding_health import HealthRow, relation_fanout_warnings, resolve_groundings
from ostler.qa.runbook import bullet_text
from ostler.qa.owners import (
    ChangedUnit,
    OwnerNode,
    Reason,
    ReasonKind,
    SharedCitations,
    citing_family_counts,
    map_changes,
    no_demotion,
    relation_reason_kind,
    shared_citations,
    source_ref,
    surface_owner,
)
from ostler.qa.source_context import SourceRepository
from ostler.source_snapshots import source_fingerprint

_SYMBOL_RE = re.compile(
    r"^\s*(?:async\s+)?(?:def|class|function|func|fn)\s+([A-Za-z_$][\w$]*)"
    r"|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="
)
_AC_RE = re.compile(r"^(?:AC\s*)?(\d+)\s*[:.)-]\s*(.+)$", re.IGNORECASE)
_CITABLE_SUFFIXES = frozenset(
    f".{ext}"
    for ext in (
        "py tsx ts jsx js go mjs cjs yaml yml dart java kt kts rs sh bash sql rb php cs swift"
        " feature"
    ).split()
)

RELATION_KEYS = (
    "consistency",
    "consistency rule",
    "consistency group",
    "persistence",
    "event",
    "concurrency",
    "idempotency",
)

_RELATION_REASON_KINDS = frozenset(relation_reason_kind(key) for key in RELATION_KEYS)

_EVENT_KEYS = ("emits", "consumes")

_SHARED_INVARIANT_KEYS = frozenset(RELATION_KEYS) | frozenset(_EVENT_KEYS)

_RELATION_SUBJECT_RE = re.compile(r"^([a-z0-9][a-z0-9._-]*)\s+—\s+(\S.*)$", re.DOTALL)

_CLOSURE_REASON_KINDS = frozenset(
    {
        ReasonKind.CONTAINS_IMPACTED_NODE,
        ReasonKind.FLOW_LINKS_CONTRACT,
        ReasonKind.FLOW_CONTRACT_CLOSURE,
        ReasonKind.GRAPH_CLOSURE,
        ReasonKind.JUDGMENT_CONTEXT,
    }
)

_COBINDING_REASON_KINDS = frozenset({ReasonKind.EVENT_CONSUMER, ReasonKind.EVENT_PRODUCER}) | _RELATION_REASON_KINDS

_CONTEXT_ONLY_REASON_KINDS = _CLOSURE_REASON_KINDS | _COBINDING_REASON_KINDS



def _sort_key(obligation_id: str) -> list[tuple[int, int | str]]:
    """Order obligation ids so `…:raises:10` follows `…:raises:2`."""
    return [(1, int(part)) if part.isdigit() else (0, part) for part in obligation_id.split(":")]


def _book_root(root: Path, features_root: str) -> str:
    """The book's own root, relative to *root*, when `--features-root` names a nested book."""
    return path_mod.book_prefix_in(root, features_root)


def book_files(root: Path, features_root: str) -> list[dict[str, str]]:
    """Every `*.md` file under the book at *features_root*, with its path and sha256."""
    book_dir = root / features_root if features_root else root
    files: list[dict[str, str]] = []
    if not book_dir.is_dir():
        return files
    for path in files_in_book(book_dir):
        rel = path.relative_to(book_dir).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"path": rel, "sha256": digest})
    files.sort(key=lambda item: item["path"])
    return files


def story_file_record(root: Path, story_file: Path | None) -> dict[str, str] | None:
    """The packet's record of the story file its `story` and `acceptanceCriteria` keys were derived from — `None` when there was no story file to derive them from."""
    if story_file is None or not story_file.is_file():
        return None
    try:
        rel = story_file.resolve().relative_to(root).as_posix()
    except ValueError:
        rel = story_file.resolve().as_posix()
    digest = hashlib.sha256(story_file.read_bytes()).hexdigest()
    return {"path": rel, "sha256": digest}


EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def book_context(
    root: Path,
    *,
    source_roots: dict[str, list[str]] | None = None,
    features_root: str = "",
    repositories: Sequence[SourceRepository] = (),
    books: Sequence[str] = (),
) -> dict[str, Any]:
    """Every obligation the book currently owns — no story, no diff, nothing to be proportional to.

    *books* names the repo-relative directories whose pages owe obligations, every page's when
    empty. The other pages still inform the context.
    """
    return build_context(
        root,
        base=EMPTY_TREE_SHA,
        head="WORKTREE",
        source_roots=source_roots,
        features_root=features_root,
        repositories=repositories,
        whole_book=True,
        books=books,
    )


def _changed_code_rows(changes: Sequence[ChangedUnit]) -> list[dict[str, Any]]:
    """Each changed unit as the packet lists it."""
    return [
        {
            "path": change.path,
            "repository": change.repository,
            "id": source_ref(change.repository, change.path),
            "basePath": change.base_path,
            "headPath": change.head_path,
            "status": change.status,
            "baseLines": list(change.base_lines),
            "headLines": list(change.head_lines),
            "baseSymbols": list(change.base_symbols),
            "headSymbols": list(change.head_symbols),
        }
        for change in changes
    ]


def _navigation(dump: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every surface's derived screen reachability in *dump*, the head graph's, keyed by surface (Option C, Amendment 1)."""
    surfaces = sorted({n["surface"] for n in dump["nodes"] if n.get("surface")})
    navigation: dict[str, dict[str, Any]] = {}
    for surface in surfaces:
        surface_dump = graph_mod.subset(dump, surface)
        driver = reach.surface_driver(dump, surface)
        bundle_id = reach.surface_bundle_id(dump, surface)
        launch_screen = reach.surface_launch_screen(dump, surface)
        root_path, _server = reach.root_path(surface_dump, driver)
        screens = reach.screens_of(surface_dump)
        entry_url = reach.entry_origin(dump, surface)
        if not screens:
            navigation[surface] = {
                "start": "",
                "surface": surface,
                "rootPath": root_path,
                "entryUrl": entry_url,
                "driver": driver,
                "bundleId": bundle_id,
                "launchScreen": launch_screen,
                "counts": {
                    "screens": 0, "reachable": 0, "unreachable": 0, "undeclared": 0, "nav_edges": 0,
                },
                "routes": {},
                "unreachable": [],
                "undeclared": [],
            }
            continue
        try:
            navigation[surface] = reach.reachability_in(surface_dump, surface=surface, driver=driver)
            navigation[surface]["rootPath"] = root_path
            navigation[surface]["entryUrl"] = entry_url
            navigation[surface]["driver"] = driver
            navigation[surface]["bundleId"] = bundle_id
            navigation[surface]["launchScreen"] = launch_screen
        except reach.UnknownStart as exc:
            navigation[surface] = {
                "start": "",
                "surface": surface,
                "rootPath": root_path,
                "entryUrl": entry_url,
                "driver": driver,
                "bundleId": bundle_id,
                "launchScreen": launch_screen,
                "counts": {
                    "screens": len(screens), "reachable": 0,
                    "unreachable": len(screens), "undeclared": 0, "nav_edges": 0,
                },
                "routes": {},
                "unreachable": sorted(screens),
                "undeclared": [],
                "error": str(exc),
            }
    return navigation


@dataclass(frozen=True, slots=True)
class _BookSnapshot:
    """The book at base and head merged into one node set, with the edges either side resolves."""

    head_graph: Graph
    head_dump: dict[str, Any]
    nodes_by_id: dict[str, dict[str, Any]]
    book: dict[str, BookNode]
    owner_nodes: dict[str, OwnerNode]
    node_scopes: dict[str, tuple[str, ...]]
    edges: set[tuple[str, str]]
    end_edges: set[tuple[str, str]]
    detail_edges: set[tuple[str, str]]
    declared_config: set[str]
    excluded_doc_roots: set[str]


@dataclass(frozen=True, slots=True)
class _ChangeSet:
    """The changed units the packet maps, and the row each source repository contributes."""

    changes: list[ChangedUnit]
    repository_rows: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class _DirectMapping:
    """Each node's direct reasons, the changes nothing owns, and the citations shared too widely to be owed."""

    reasons: dict[str, list[Reason]]
    unmapped: list[dict[str, Any]]
    shared: SharedCitations


@dataclass(frozen=True, slots=True)
class _Selection:
    """The contracts and journeys the change reaches, with every node's reasons and its judgment context."""

    direct_reasons: dict[str, list[Reason]]
    contracts: set[str]
    journeys: set[str]
    judgment_by_node: dict[str, list[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class _Grounding:
    """The selected nodes whose citations resolve, and the health rows about the ones that do not."""

    grounded: set[str]
    health: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class _Requirement:
    """The contracts owed live evidence, the ones the diff itself reached, and the health rows deciding them raised."""

    required_contracts: set[str]
    reached_by_the_diff: set[str]
    health: list[dict[str, Any]]


def build_context(
    root: Path,
    *,
    base: str,
    head: str = "WORKTREE",
    source_roots: dict[str, list[str]] | None = None,
    features_root: str = "",
    story_file: Path | None = None,
    exclude_paths: Iterable[str] = (),
    repositories: Sequence[SourceRepository] = (),
    whole_book: bool = False,
    books: Sequence[str] = (),
) -> dict[str, Any]:
    """Map a `base..head` code diff onto the OKF graph and return the obligation packet.

    *whole_book* holds every node to its own claims, with no citation demoted to context,
    because a whole book has no change to be proportional to. *books* names the repo-relative
    directories whose pages owe obligations, every page's when empty.
    """
    root = root.resolve()
    features_root = path_mod.resolve_features_root(features_root, root)
    source_roots = source_roots or {}
    book_root = _book_root(root, features_root)
    snapshot = _book_snapshot(root, base, head, features_root)
    change_set = _change_set(root, base, head, source_roots, repositories)
    changes = _production_changes(root, change_set.changes, snapshot, {str(path) for path in exclude_paths})
    mapping = _direct_mapping(changes, snapshot, book_root, source_roots, whole_book=whole_book)
    selection = _selection(snapshot, mapping.reasons)
    verification_index = _verification_index(snapshot.book, selection.contracts | selection.journeys)
    repositories_by_id = {repository.id: repository for repository in repositories}
    grounding = _grounding(
        snapshot.book,
        selection.contracts | selection.journeys,
        lambda ref: _grounding_for_ref(root, base, head, ref, repositories_by_id, book_root),
    )
    requirement = _requirement(snapshot.book, selection, grounding.grounded, mapping.shared)
    changed_code = _changed_code_rows(changes)
    navigation = _navigation(snapshot.head_dump)
    return {
        "version": 2 if repositories else 1,
        "available": bool(snapshot.nodes_by_id),
        "base": base,
        "head": head,
        "featuresRoot": features_root,
        "bookFiles": book_files(root, features_root),
        "storyFile": story_file_record(root, story_file),
        "changedCode": changed_code,
        **({"changedUnits": changed_code, "repositories": change_set.repository_rows} if repositories else {}),
        "directNodes": [
            {"node": node_id, "reasons": [reason.row() for reason in selection.direct_reasons[node_id]]}
            for node_id in sorted(selection.direct_reasons)
        ],
        "contracts": sorted(selection.contracts),
        "journeys": sorted(selection.journeys),
        "journeyNodes": sorted(selection.journeys),
        "verificationRefs": [
            {"node": item["node"], "ref": item["ref"], "path": item["path"]}
            for item in verification_index
            if item["impacted"]
        ],
        "verificationIndex": verification_index,
        "navigation": navigation,
        "cliBinaries": _run_binaries_by_path(snapshot.book),
        "serverOrigins": _server_origins(snapshot.book),
        "scenarioFixtures": _scenario_fixtures(snapshot.book),
        "browserFixtures": _browser_fixtures(snapshot.book),
        "fixtureScreens": _fixture_screens(snapshot.book),
        "fragmentHosts": _fragment_hosts(snapshot.book),
        "screenRoutes": routes_mod.screen_routes(snapshot.head_graph),
        "healthFindings": [*mapping.unmapped, *grounding.health, *requirement.health],
        "story": _story_identity(story_file),
        "acceptanceCriteria": _acceptance_criteria(story_file),
        "obligations": _minted_obligations(snapshot, selection, requirement, books, walks=_walks(navigation)),
    }


def _book_snapshot(root: Path, base: str, head: str, features_root: str) -> _BookSnapshot:
    """The book at *base* and at *head*, merged so a node either side holds is in it."""
    current = load(root, root_overrides={"features": features_root})
    base_graph = _graph_at_revision(root, base, features_root, current)
    head_graph = current if head == "WORKTREE" else _graph_at_revision(root, head, features_root, current)
    head_dump = graph_mod.build(head_graph)
    base_dump = graph_mod.build(base_graph)
    base_nodes, base_edges, base_ends, base_details = _serialized_graph(base_dump)
    head_nodes, head_edges, head_ends, head_details = _serialized_graph(head_dump)
    nodes_by_id = _merge_snapshot_nodes(base_nodes, head_nodes)
    book = book_nodes(nodes_by_id)
    head_book = {node_id: book[node_id] for node_id in head_nodes}
    return _BookSnapshot(
        head_graph=head_graph,
        head_dump=head_dump,
        nodes_by_id=nodes_by_id,
        book=book,
        owner_nodes={node_id: _owner_node(node) for node_id, node in nodes_by_id.items()},
        node_scopes={
            **locators_mod.LocatorBook.parse(base_dump).scopes,
            **locators_mod.LocatorBook.parse(head_dump, head_book).scopes,
        },
        edges=base_edges | head_edges,
        end_edges=base_ends | head_ends,
        detail_edges=base_details | head_details,
        declared_config={
            item
            for node in nodes_by_id.values()
            for item in refs_mod.code_refs(node.get("bullets", {}).get("config"))
        },
        excluded_doc_roots={
            path.resolve().relative_to(root).as_posix()
            for path in current.doc_roots.values()
            if path.resolve().is_relative_to(root)
        },
    )


def _change_set(
    root: Path,
    base: str,
    head: str,
    source_roots: dict[str, list[str]],
    repositories: Sequence[SourceRepository],
) -> _ChangeSet:
    """Every changed unit, across the named source repositories when there are any, else in *root*."""
    if not repositories:
        return _ChangeSet(changes=_changed_units(root, base, head, source_roots), repository_rows=[])
    changes: list[ChangedUnit] = []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for repository in repositories:
        if repository.id in seen:
            raise ValueError(f"duplicate source repository id {repository.id!r}")
        seen.add(repository.id)
        changes.extend(_repository_changes(repository))
        rows.append(_repository_row(repository))
    return _ChangeSet(changes=changes, repository_rows=rows)


def _repository_changes(repository: SourceRepository) -> list[ChangedUnit]:
    """The changed units of one source repository, each tagged with the repository and surface that own it."""
    checkout = Path(repository.checkout).resolve()
    roots: dict[str, list[str]] = {}
    for scope in repository.scopes:
        roots.setdefault(scope.surface, []).append(scope.root)
    return [
        replace(
            change,
            repository=repository.id,
            surface=surface_owner(change.path, roots),
            source_root=str(checkout),
        )
        for change in _changed_units(checkout, repository.base, repository.head, roots)
    ]


def _repository_row(repository: SourceRepository) -> dict[str, Any]:
    """One source repository as the packet lists it, with the commits its revisions resolve to."""
    checkout = Path(repository.checkout).resolve()
    return {
        "id": repository.id,
        "base": repository.base,
        "baseSha": _git(checkout, "rev-parse", "--verify", f"{repository.base}^{{commit}}").strip(),
        "head": repository.head,
        "headSha": (None if repository.head == "WORKTREE" else
                    _git(checkout, "rev-parse", "--verify", f"{repository.head}^{{commit}}").strip()),
        "headAnchorSha": (_git(checkout, "rev-parse", "HEAD").strip()
                          if repository.head == "WORKTREE" else None),
        "sourceFingerprint": source_fingerprint(repository),
        "scopes": [scope.model_dump(mode="json") for scope in repository.scopes],
    }


def _production_changes(
    root: Path, changes: Sequence[ChangedUnit], snapshot: _BookSnapshot, excluded_paths: set[str]
) -> list[ChangedUnit]:
    """The changes that are production code or declared config, outside the excluded paths and the book itself."""
    return [
        change
        for change in changes
        if change.path not in excluded_paths
        and (change.repository or not any(
            change.path == prefix or change.path.startswith(prefix.rstrip("/") + "/")
            for prefix in snapshot.excluded_doc_roots
        ))
        and (
            source_ref(change.repository, change.path) in snapshot.declared_config
            or (
                not _is_non_production_path(change.path)
                and not _is_generated_unit(Path(change.source_root) if change.source_root else root,
                                           change)
            )
        )
    ]


def _direct_mapping(
    changes: Sequence[ChangedUnit],
    snapshot: _BookSnapshot,
    book_root: str,
    source_roots: dict[str, list[str]],
    *,
    whole_book: bool,
) -> _DirectMapping:
    """Each node the changes name directly, or every node when the whole book is owed."""
    mapped = map_changes(changes, snapshot.owner_nodes, book_root, source_roots)
    reasons = mapped.reasons
    if whole_book:
        for node_id in snapshot.nodes_by_id:
            reasons.setdefault(node_id, []).append(Reason(ReasonKind.BOOK_CLAIM, node_id))
    demote = no_demotion if whole_book else shared_citations
    shared = demote(
        citing_family_counts(
            mapped.file_owners,
            mapped.symbol_owners,
            lambda node_id, family_members: _family_root(node_id, family_members, snapshot.book),
        )
    )
    return _DirectMapping(reasons=reasons, unmapped=[change.row() for change in mapped.unmapped], shared=shared)


def _selection(snapshot: _BookSnapshot, direct_reasons: dict[str, list[Reason]]) -> _Selection:
    """The contracts and journeys the direct reasons reach, closed over parents, flows, shared subjects and judgment."""
    impacted = _impacted_with_parents(snapshot.nodes_by_id, direct_reasons)
    flows = {node_id for node_id, node in snapshot.nodes_by_id.items() if node.get("type") == "flow"}
    journeys = set(impacted & flows)
    for source, target in snapshot.edges:
        if source in flows and target in impacted:
            journeys.add(source)
            direct_reasons.setdefault(source, []).append(Reason(ReasonKind.FLOW_LINKS_CONTRACT, target))
    contracts = impacted - flows
    for source, target in snapshot.edges:
        if source in journeys and target in snapshot.nodes_by_id and target not in flows:
            contracts.add(target)
            direct_reasons.setdefault(target, []).append(Reason(ReasonKind.FLOW_CONTRACT_CLOSURE, source))
    _close_over_shared_subjects(snapshot.book, contracts, journeys, direct_reasons)
    judgment_by_node = _judgment_context(snapshot, contracts, journeys, direct_reasons)
    return _Selection(
        direct_reasons=direct_reasons,
        contracts=contracts,
        journeys=journeys,
        judgment_by_node=judgment_by_node,
    )


def _impacted_with_parents(
    nodes_by_id: Mapping[str, Mapping[str, Any]], direct_reasons: dict[str, list[Reason]]
) -> set[str]:
    """The directly impacted nodes and every ancestor of one, each ancestor given its reason."""
    impacted = set(direct_reasons)
    for node_id in list(impacted):
        parent = nodes_by_id.get(node_id, {}).get("parent")
        while parent and parent in nodes_by_id:
            if parent not in impacted:
                direct_reasons.setdefault(parent, []).append(Reason(ReasonKind.CONTAINS_IMPACTED_NODE, node_id))
            impacted.add(parent)
            parent = nodes_by_id[parent].get("parent")
    return impacted


def _close_over_shared_subjects(
    book: Mapping[str, BookNode],
    contracts: set[str],
    journeys: set[str],
    direct_reasons: dict[str, list[Reason]],
) -> None:
    """Add every node that shares an event or a relation with the selection, until none is left to add."""
    related = True
    while related:
        related = False
        selected = contracts | journeys
        emitted = {value for node_id in selected for value in book[node_id].bullets.get("emits", ())}
        consumed = {value for node_id in selected for value in book[node_id].bullets.get("consumes", ())}
        relation_values = {
            _relation_join_key(value)
            for node_id in selected
            for key in RELATION_KEYS
            for value in book[node_id].bullets.get(key, ())
        }
        for node_id, node in book.items():
            if node_id in selected:
                continue
            reasons = _shared_subject_reasons(node, emitted, consumed, relation_values)
            if reasons:
                (journeys if node.type == "flow" else contracts).add(node_id)
                direct_reasons.setdefault(node_id, []).extend(reasons)
                related = True


def _shared_subject_reasons(
    node: BookNode, emitted: set[str], consumed: set[str], relation_values: set[str]
) -> list[Reason]:
    """Why *node* shares an event or a relation with the selection, empty when it shares none."""
    reasons = [
        Reason(ReasonKind.EVENT_CONSUMER, value)
        for value in node.bullets.get("consumes", ())
        if value in emitted
    ]
    reasons.extend(
        Reason(ReasonKind.EVENT_PRODUCER, value)
        for value in node.bullets.get("emits", ())
        if value in consumed
    )
    for key in RELATION_KEYS:
        for value in node.bullets.get(key, ()):
            join = _relation_join_key(value)
            if join in relation_values:
                reasons.append(Reason(relation_reason_kind(key), join))
    return reasons


def _judgment_context(
    snapshot: _BookSnapshot,
    contracts: set[str],
    journeys: set[str],
    direct_reasons: dict[str, list[Reason]],
) -> dict[str, list[dict[str, Any]]]:
    """Each selected node's `detail:` concepts, each concept joining the selection as context."""
    judgment_by_node: dict[str, list[dict[str, Any]]] = {}
    for source, target in sorted(snapshot.detail_edges):
        if source not in contracts and source not in journeys:
            continue
        concept = snapshot.book.get(target)
        if concept is None or concept.type != "concept":
            continue
        judgment_by_node.setdefault(source, []).append(
            {
                "concept": target,
                "title": concept.title or target,
                "rules": list(concept.bullets.get("rule", ())),
                "prefers": list(concept.bullets.get("prefers", ())),
                "deprecates": list(concept.bullets.get("deprecates", ())),
            }
        )
        if target not in contracts and target not in journeys:
            contracts.add(target)
            direct_reasons.setdefault(target, []).append(Reason(ReasonKind.JUDGMENT_CONTEXT, source))
    return judgment_by_node


def _verification_index(book: Mapping[str, BookNode], selected: set[str]) -> list[dict[str, Any]]:
    """Every verification reference the book declares, marked impacted when its node is selected."""
    return [
        {"node": node_id, "ref": ref, "path": _code_path(ref), "impacted": node_id in selected}
        for node_id, node in sorted(book.items())
        for ref in _verification_refs(node)
    ]


def _grounding(
    book: Mapping[str, BookNode], selected: set[str], resolves: Callable[[str], bool]
) -> _Grounding:
    """Which selected nodes cite code that resolves, with a health row per dangling citation and missing check."""
    selected_nodes = {node_id: book[node_id] for node_id in sorted(selected)}
    grounded, dangling = resolve_groundings(
        {node_id: tuple(refs_mod.code_refs(list(node.bullets.get("code", ())))) for node_id, node in selected_nodes.items()},
        resolves,
    )
    health = [row.row() for row in dangling]
    for node in selected_nodes.values():
        health.extend(row.row() for row in _missing_declared_checks(node))
    return _Grounding(grounded=grounded, health=health)


def _requirement(
    book: Mapping[str, BookNode], selection: _Selection, grounded: set[str], shared: SharedCitations
) -> _Requirement:
    """The contracts owed live evidence, widened to the ones naming a required contract's relation subject."""
    health: list[dict[str, Any]] = []
    demoted_symbols: frozenset[str] = shared.symbols
    required_contracts = _required_contracts(selection, grounded, shared.files, demoted_symbols)
    if not required_contracts:
        floored = _required_contracts(selection, grounded, shared.files, frozenset())
        if floored:
            required_contracts = floored
            demoted_symbols = frozenset()
            health.append(_SHARED_SYMBOL_FLOOR.row())
    reached_by_the_diff = set(required_contracts)
    subjects_by_node = {node_id: _named_subjects(node) for node_id, node in book.items()}
    required_subjects = {
        subject for node_id in required_contracts for subject in subjects_by_node[node_id]
    }
    if required_subjects:
        hopped = False
        for node_id in sorted(selection.contracts - required_contracts):
            for subject in sorted(subjects_by_node[node_id] & required_subjects):
                selection.direct_reasons.setdefault(node_id, []).append(
                    Reason(ReasonKind.RELATION_OF_REQUIRED, subject)
                )
                hopped = True
        if hopped:
            required_contracts = _required_contracts(selection, grounded, shared.files, demoted_symbols)
        health.extend(row.row() for row in relation_fanout_warnings(subjects_by_node, required_subjects))
    return _Requirement(required_contracts=required_contracts, reached_by_the_diff=reached_by_the_diff, health=health)


_SHARED_SYMBOL_FLOOR = HealthRow(
    kind="shared-symbol-floor",
    severity="warning",
    message=(
        "every changed symbol is cited by enough nodes to be demoted, which"
        " would leave this change owing no live evidence at all; the"
        " demotion was dropped and the changed-code reasons kept"
    ),
)


def _required_contracts(
    selection: _Selection, grounded: set[str], shared_files: frozenset[str], demoted_symbols: frozenset[str]
) -> set[str]:
    """The selected contracts owed live evidence with *demoted_symbols* counted as context."""
    return {
        node_id
        for node_id in selection.contracts
        if _is_required(node_id, selection.direct_reasons, grounded, shared_files, demoted_symbols)
    }


def _minted_obligations(
    snapshot: _BookSnapshot,
    selection: _Selection,
    requirement: _Requirement,
    books: Sequence[str] = (),
    *,
    walks: Mapping[str, tuple[str, ...]] | None = None,
) -> list[dict[str, Any]]:
    """Every selected contract's and journey's obligations on a page under *books*, in id order, each id once."""
    book = snapshot.book
    prefixes = tuple(f"{directory.rstrip('/')}/" for directory in books)
    owing = {node_id for node_id in selection.contracts | selection.journeys if not prefixes or book[node_id].path.startswith(prefixes)}
    fixture_provides = _fixture_provides_index(book)
    fixture_undetermined = _fixture_undetermined_index(book)
    fixture_needs = _fixture_needs_index(book)

    def mint(node_id: str, *, journey: bool, required: bool, owed_keys: frozenset[str] | None) -> list[dict[str, Any]]:
        return _obligations(
            book[node_id],
            selection.direct_reasons.get(node_id, []),
            journey=journey,
            required=required,
            owed_keys=owed_keys,
            scope=snapshot.node_scopes.get(node_id, ()),
            judgment=selection.judgment_by_node.get(node_id),
            fixture_provides=fixture_provides,
            fixture_undetermined=fixture_undetermined,
            fixture_needs=fixture_needs,
            resolve_locator=_locator_resolver(snapshot.head_graph, book, book[node_id]),
            book=book,
            walks=walks or {},
        )

    obligations = [
        obligation
        for node_id in sorted(selection.contracts & owing)
        for obligation in mint(
            node_id,
            journey=False,
            required=node_id in requirement.required_contracts,
            owed_keys=None if node_id in requirement.reached_by_the_diff else _SHARED_INVARIANT_KEYS,
        )
    ] + [
        obligation
        for node_id in sorted(selection.journeys & owing)
        for obligation in mint(
            node_id,
            journey=True,
            required=_journey_is_required(
                node_id, selection.direct_reasons, requirement.required_contracts, snapshot.end_edges
            ),
            owed_keys=None,
        )
    ]
    obligations.sort(key=lambda item: _sort_key(str(item["id"])))
    deduped: dict[str, dict[str, Any]] = {}
    for obligation in obligations:
        deduped.setdefault(str(obligation["id"]), obligation)
    minted = list(deduped.values())
    _discharge_states_an_interaction_reaches(minted, _fragment_hosts(book))
    return minted


_REACHED_BY_INTERACTION_KEYS = frozenset({"states", "role", "name"})


def _discharge_states_an_interaction_reaches(minted: list[dict[str, Any]], hosts: Mapping[str, str]) -> None:
    """Stop owing an arrival check on a component that comes and goes when an interaction on its page proves it visible.

    A fragment's components are shown on its host, so an interaction on the host proves them.
    """

    def page(obligation: dict[str, Any]) -> str:
        source = str(obligation["source"])
        return hosts.get(source, source)

    proven = {
        (page(obligation), str(target["node"]))
        for obligation in minted
        if obligation["nodeType"] == "interaction"
        for check in obligation.get("checksDeclared", ())
        if check["name"] == "visible"
        for target in check.get("locates", {}).values()
    }
    comes_and_goes = {
        str(obligation["node"])
        for obligation in minted
        if obligation["nodeType"] == "component" and obligation["kind"] == "states"
    }
    for obligation in minted:
        if obligation["nodeType"] != "component" or obligation["kind"] not in _REACHED_BY_INTERACTION_KEYS:
            continue
        if obligation["node"] not in comes_and_goes or (page(obligation), str(obligation["node"])) not in proven:
            continue
        if obligation.get("checksDeclared") or obligation.get("fixturesDeclared"):
            continue
        obligation["required"] = False
        obligation["evidenceRequired"] = "context"


VERIFICATION_INDEX_FILE = "qa-okf-verification-index.json"


_JSON: TypeAdapter[Any] = TypeAdapter(Any)


def write_context(packet: dict[str, Any], spec_dir: Path) -> tuple[Path, Path]:
    spec_dir.mkdir(parents=True, exist_ok=True)
    json_path = spec_dir / "qa-okf-context.json"
    md_path = spec_dir / "qa-okf-context.md"
    reader_packet = {key: value for key, value in packet.items() if key != "verificationIndex"}
    (spec_dir / VERIFICATION_INDEX_FILE).write_bytes(_JSON.dump_json(packet.get("verificationIndex", []), indent=2) + b"\n")
    json_path.write_bytes(_JSON.dump_json(reader_packet, indent=2) + b"\n")
    md_path.write_text(render_context(reader_packet), encoding="utf-8")
    return json_path, md_path


OWED_HEADING = "## Obligations — owed live evidence"
CONTEXT_HEADING = "## Context — reached by closure, not owed evidence"


def render_obligations(
    obligations: Sequence[dict[str, Any]], *, locators: bool = True
) -> list[str]:
    """Render one obligation section, or `- (none)` when it is empty."""
    if not obligations:
        return ["- (none)"]
    lines: list[str] = []
    for obligation in obligations:
        lines.append(f"- `{obligation['id']}`: {obligation['requirement']}")
        if locators:
            for key, values in sorted(obligation.get("locators", {}).items()):
                lines.append(f"  - {key}: {'; '.join(values)}")
            if obligation.get("repeat"):
                lines.append(f"  - repeated: {_render_repeat(RepeatContract.parse(obligation['repeat']))}")
        for entry in obligation.get("judgment", []):
            rules = "; ".join(entry.get("rules", []))
            lines.append(f"  - judgment: `{entry['concept']}`" + (f" — {rules}" if rules else ""))
            for preferred in entry.get("prefers", []):
                lines.append(f"    - prefers: {preferred}")
            for deprecated in entry.get("deprecates", []):
                lines.append(f"    - deprecates: {deprecated}")
        for entry in obligation.get("unspecified", []):
            lines.append(f"  - unspecified (resolved by design): {entry['text']}")
    return lines


def _render_repeat(repeat: RepeatContract) -> str:
    """One line naming what a repeated obligation repeats over, binds, is unique by and varies over."""
    parts = [f"one per `{repeat.one_per}`"]
    if repeat.binds:
        parts.append("binds " + ", ".join(f"`{bind}`" for bind in repeat.binds))
    if repeat.unique_by:
        parts.append(f"unique by `{repeat.unique_by}`")
    if repeat.variants is not None:
        parts.append(f"variants `{repeat.variants.path}` = " + " | ".join(repeat.variants.values))
    return "; ".join(parts)


def select_obligations(
    packet: dict[str, Any],
    *,
    required: bool | None = None,
    node: str = "",
    kind: str = "",
    offset: int = 0,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Filter and page the obligation list, returning `(page, total_matched)`."""
    matched = [
        item
        for item in packet.get("obligations", [])
        if (required is None or bool(item.get("required", True)) is required)
        and (not node or node in str(item.get("node", "")))
        and (not kind or str(item.get("kind", "")) == kind)
    ]
    window = matched[offset:] if limit is None else matched[offset : offset + limit]
    return window, len(matched)


def render_context(packet: dict[str, Any]) -> str:
    lines = [
        "---",
        f"type: {registry.spec_type_for('qa-okf-context.md')}",
        "---",
        "# QA OKF Context",
        "",
        f"- Base: `{packet.get('base', '')}`",
        f"- Head: `{packet.get('head', '')}`",
        f"- Available: `{str(packet.get('available', False)).lower()}`",
        "",
        "## Changed Code",
        "",
    ]
    for change in packet.get("changedCode", []):
        symbols = sorted(set(change.get("baseSymbols", []) + change.get("headSymbols", [])))
        lines.append(f"- `{change['path']}` ({change['status']}): {', '.join(symbols) or 'file scope'}")
    if not packet.get("changedCode"):
        lines.append("- (none)")
    obligations = packet.get("obligations", [])
    owed = [item for item in obligations if item.get("required", True)]
    context_only = [item for item in obligations if not item.get("required", True)]
    lines.extend(["", OWED_HEADING, ""])
    lines.extend(render_obligations(owed))
    lines.extend(["", CONTEXT_HEADING, ""])
    lines.extend(render_obligations(context_only))
    lines.extend(["", "## Health Findings", ""])
    for finding in packet.get("healthFindings", []):
        lines.append(f"- **{finding['kind']}** `{finding.get('path', '')}`: {finding['message']}")
    if not packet.get("healthFindings"):
        lines.append("- (none)")
    return "\n".join(lines) + "\n"


def validate_context(packet: Any) -> list[str]:
    if not isinstance(packet, dict):
        return ["context must be a JSON object"]
    problems: list[str] = []
    version = packet.get("version")
    if version not in (1, 2):
        problems.append("context.version must be 1 or 2")
    if not isinstance(packet.get("available"), bool):
        problems.append("context.available must be boolean")
    for field in ("changedCode", "directNodes", "contracts", "journeys", "journeyNodes", "verificationRefs", "healthFindings", "obligations"):
        if not isinstance(packet.get(field), list):
            problems.append(f"context.{field} must be a list")
    if version == 2:
        for field in ("changedUnits", "repositories"):
            if not isinstance(packet.get(field), list):
                problems.append(f"context.{field} must be a list")
    if "verificationIndex" in packet and not isinstance(packet["verificationIndex"], list):
        problems.append("context.verificationIndex must be a list")
    if "navigation" in packet and not isinstance(packet["navigation"], dict):
        problems.append("context.navigation must be an object")
    seen: set[str] = set()
    for item in packet.get("obligations", []):
        if not isinstance(item, dict) or not item.get("id"):
            problems.append("every obligation must be an object with an id")
            continue
        if item["id"] in seen:
            problems.append(f"duplicate obligation id '{item['id']}'")
        seen.add(item["id"])
    return problems


def cmd_context(
    root: Path,
    spec_dir: Path,
    *,
    base: str,
    head: str = "WORKTREE",
    source_roots: dict[str, list[str]] | None = None,
    features_root: str = "",
    story_file: Path | None = None,
    exclude_paths: Iterable[str] = (),
    repositories: Sequence[SourceRepository] = (),
) -> QaOutcome:
    """Build the obligation packet, write it into *spec_dir*, and report the outcome."""
    try:
        packet = build_context(
            root,
            base=base,
            head=head,
            source_roots=source_roots or {},
            features_root=features_root,
            story_file=story_file,
            exclude_paths=exclude_paths,
            repositories=repositories,
        )
        annotate_deferred_obligations(packet)
        json_path, md_path = write_context(packet, spec_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        return QaOutcome(ok=False, message=str(exc), status="invalid",
                         data={"status": "invalid", "message": str(exc)})
    ok = not any(f.get("severity") == "error" for f in packet.get("healthFindings", []))
    return QaOutcome(ok=ok, message=f"wrote {json_path} and {md_path}", data=packet)


def cmd_context_validate(spec_dir: Path) -> QaOutcome:
    """Read `qa-okf-context.json` out of *spec_dir* and validate it."""
    context_file = spec_dir / "qa-okf-context.json"
    try:
        packet = json.loads(context_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems = [str(exc)]
    else:
        problems = validate_context(packet)
    status = "passed" if not problems else "invalid"
    return QaOutcome(
        ok=not problems,
        message=("Context is valid." if not problems
                 else "Context validation failed:\n"
                      + "\n".join(f"  - {p}" for p in problems)),
        status=status,
        data={"status": status, "problems": problems},
    )


def _revision_path_arg(revision: str, path: str) -> str:
    """The `<rev>:<path>` argument for `git show` / `git cat-file`, forced into the CWD frame."""
    if not path or path == "/dev/null":
        return f"{revision}:{path}"
    if path.startswith("./"):
        return f"{revision}:{path}"
    return f"{revision}:./{path}"


def _graph_at_revision(root: Path, revision: str, features_root: str, current: Graph | None = None) -> Graph:
    """The base-side graph at `revision`, built from every `.md` file under `features_root`, on the org, profile and doc roots of `current`, the worktree's graph, which is loaded when not given."""
    current = current if current is not None else load(root)
    graph = Graph(
        root=root,
        org_name=current.org_name,
        profile=current.profile,
        doc_roots={**current.doc_roots, "features": root / features_root},
    )
    if not _revision_holds(root, revision, features_root):
        return graph
    result = _git(root, "ls-tree", "-r", "-z", "--name-only", revision, "--", features_root)
    entries = [entry for entry in result.split("\0") if entry]
    for rel in sorted(entry for entry in entries if entry.endswith(".md")):
        try:
            text = _git(root, "show", _revision_path_arg(revision, rel))
        except RuntimeError as exc:
            raise RuntimeError(
                f"{revision} lists {rel} under {features_root} but its blob is unreadable: {exc}"
            ) from exc
        graph.ui_nodes.extend(_parse_ui_nodes(markdown.split(text), root / rel, root))
    return graph


def _serialized_graph(
    data: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    set[tuple[str, str]],
    set[tuple[str, str]],
    set[tuple[str, str]],
]:
    """The nodes of *data*, a built graph, with every resolved edge, the flow destinations, and the `detail:` edges."""
    nodes = {item["id"]: item for item in data["nodes"]}
    edges = {(item["from"], item["to"]) for item in data["edges"] if item.get("to")}
    details = {
        (item["from"], item["to"])
        for item in data["edges"]
        if item.get("to") and item.get("via") == "detail"
    }
    ends: set[tuple[str, str]] = set()
    for item in data["nodes"]:
        if item.get("type") != "flow":
            continue
        walked = [edge for edge in item.get("edges", []) if edge.get("to")]
        end = item.get("bullets", {}).get("end")
        values = end if isinstance(end, list) else [end]
        hrefs = {
            href
            for value in values
            if value
            for _text, href in markdown.extract_refs(str(value)).links
        }
        named = [edge for edge in walked if edge.get("href") in hrefs]
        ends.update((item["id"], edge["to"]) for edge in named or walked[-1:])
    return nodes, edges, ends, details


def _in_book(path: str, offset: str) -> str | None:
    """*path*, spelled from the repository top level, rebased onto the book root *offset* names — or `None` when *path* falls outside the book root entirely."""
    if not offset:
        return path
    return path[len(offset):] if path.startswith(offset) else None


def _changed_units(
    root: Path,
    base: str,
    head: str,
    source_roots: dict[str, list[str]],
) -> list[ChangedUnit]:
    toplevel = Path(_git(root, "rev-parse", "--show-toplevel").strip()).resolve()
    resolved_root = root.resolve()
    offset = (
        "" if resolved_root == toplevel
        else f"{resolved_root.relative_to(toplevel).as_posix()}/"
    )
    args = ["diff", "--find-renames", "--unified=0", base]
    if head != "WORKTREE":
        args.append(head)
    configured = sorted({path for paths in source_roots.values() for path in paths})
    if configured:
        args.extend(["--", *configured])
    diff = _git(root, *args)
    units: dict[str, dict[str, Any]] = {}
    for patched in _patch_set(diff):
        old_top = patched.source_file.removeprefix("a/")
        new_top = patched.target_file.removeprefix("b/")
        book_path = _in_book(new_top if new_top != "/dev/null" else old_top, offset)
        if book_path is None:
            continue
        unit = units.setdefault(
            book_path, {"base": set(), "head": set(), "old": old_top, "new": new_top}
        )
        for hunk in patched:
            unit["base"].update(range(hunk.source_start, hunk.source_start + hunk.source_length))
            unit["head"].update(range(hunk.target_start, hunk.target_start + hunk.target_length))
    name_args = ["diff", "--find-renames", "--name-status", base]
    if head != "WORKTREE":
        name_args.append(head)
    if configured:
        name_args.extend(["--", *configured])
    for line in _git(root, *name_args).splitlines():
        fields = line.split("\t")
        status_code = fields[0]
        if status_code.startswith("R") and len(fields) >= 3:
            old_top, new_top = fields[1], fields[2]
        elif len(fields) >= 2:
            old_top = "/dev/null" if status_code == "A" else fields[1]
            new_top = "/dev/null" if status_code == "D" else fields[1]
        else:
            continue
        book_path = _in_book(new_top if new_top != "/dev/null" else old_top, offset)
        if book_path is None:
            continue
        units.setdefault(book_path, {"base": set(), "head": set(), "old": old_top, "new": new_top})
    if head == "WORKTREE":
        untracked_args = ["ls-files", "--others", "--exclude-standard"]
        if configured:
            untracked_args.extend(["--", *configured])
        for book_path in _git(root, *untracked_args).splitlines():
            top_path = f"{offset}{book_path}"
            text = _working_text(toplevel, top_path)
            units.setdefault(
                book_path,
                {
                    "base": set(),
                    "head": set(range(1, len(text.splitlines()) + 1)),
                    "old": "/dev/null",
                    "new": top_path,
                },
            )
    output: list[ChangedUnit] = []
    for book_path, item in sorted(units.items()):
        base_text = _revision_text(toplevel, base, item["old"])
        head_text = (
            _working_text(toplevel, item["new"])
            if head == "WORKTREE"
            else _revision_text(toplevel, head, item["new"])
        )
        base_missing = item["old"] not in ("", "/dev/null") and not _revision_holds(
            toplevel, base, item["old"]
        )
        head_missing = item["new"] not in ("", "/dev/null") and not (
            (toplevel / item["new"]).is_file()
            if head == "WORKTREE"
            else _revision_holds(toplevel, head, item["new"])
        )
        if not base_text and not head_text and not base_missing and not head_missing:
            continue
        status = "modified"
        if item["old"] == "/dev/null":
            status = "added"
        elif item["new"] == "/dev/null":
            status = "deleted"
        elif item["old"] != item["new"]:
            status = "renamed"
        book_old = "" if item["old"] == "/dev/null" else (_in_book(item["old"], offset) or "")
        book_new = "" if item["new"] == "/dev/null" else (_in_book(item["new"], offset) or "")
        output.append(
            ChangedUnit(
                path=book_path,
                base_path=book_old,
                head_path=book_new,
                status=status,
                base_lines=tuple(sorted(item["base"])),
                head_lines=tuple(sorted(item["head"])),
                base_symbols=tuple(_symbols_for_lines(base_text, item["base"], book_old)),
                head_symbols=tuple(_symbols_for_lines(head_text, item["head"], book_new)),
            )
        )
    return output


def _patch_set(diff: str) -> PatchSet:
    """The diff, parsed."""
    try:
        return PatchSet(diff)
    except UnidiffParseError:
        return PatchSet("")


def _symbols_for_lines(text: str, lines: set[int], path: str = "") -> list[str]:
    """The symbols whose bodies span any of *lines* — the diff's changed units."""
    if not text or not lines:
        return []
    suffix = Path(path).suffix
    grammar = syntax.language_for(path) or ("python" if suffix == "" else None)
    if grammar is not None:
        symbols = inventory.extents(path, text, language=grammar)
    else:
        text_lines = text.splitlines()
        declarations = [
            (number, match.group(1) or match.group(2) or "")
            for number, line in enumerate(text_lines, start=1)
            if (match := _SYMBOL_RE.match(line))
        ]
        symbols = [
            (
                start,
                declarations[index + 1][0] - 1
                if index + 1 < len(declarations)
                else len(text_lines),
                name,
            )
            for index, (start, name) in enumerate(declarations)
        ]
    found: set[str] = set()
    for line in lines:
        containing = [item for item in symbols if item[0] <= line <= item[1]]
        if containing:
            found.add(max(containing, key=lambda item: item[0])[2])
    return sorted(found)


def _revision_text(root: Path, revision: str, path: str) -> str:
    """The blob's text at `revision`, or "" — the same answer `_working_text` gives for a file it cannot decode, so the two sides of a diff agree about what "unreadable" means."""
    if not path or path == "/dev/null" or revision == EMPTY_TREE_SHA:
        return ""
    try:
        blob = _git_bytes(root, "show", _revision_path_arg(revision, path))
    except RuntimeError:
        return ""
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def _working_text(root: Path, path: str) -> str:
    """The working tree's text at `path`, or "" when it is absent or not decodable as UTF-8."""
    candidate = root / path
    try:
        return candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _revision_holds(root: Path, revision: str, path: str) -> bool:
    """Whether `revision` has a blob at `path` — asked of the bytes, never of their decoding."""
    if not path or path == "/dev/null" or revision == EMPTY_TREE_SHA:
        return False
    try:
        _git_bytes(root, "cat-file", "-e", _revision_path_arg(revision, path))
    except RuntimeError:
        return False
    return True


def _grounding_exists(root: Path, base: str, head: str, ref: refs_mod.CodeRef) -> bool:
    path, symbol = ref.path, ref.symbol
    present = _revision_holds(root, base, path) or (
        (root / path).is_file() if head == "WORKTREE" else _revision_holds(root, head, path)
    )
    if not present:
        return False
    if not symbol or not path.endswith(".py"):
        return True
    texts = [
        text
        for text in (
            _revision_text(root, base, path),
            _working_text(root, path) if head == "WORKTREE" else _revision_text(root, head, path),
        )
        if text
    ]
    return any(inventory.declares(path, text, symbol) for text in texts)


def _grounding_for_ref(
    root: Path,
    base: str,
    head: str,
    ref: str,
    repositories: dict[str, SourceRepository],
    book_root: str = "",
) -> bool:
    """Ground one citation in the docs repository or its named source repository."""
    try:
        parsed = refs_mod.parse_code_ref(ref)
    except ValueError:
        return False
    if not parsed.repository:
        if book_root:
            parsed = replace(parsed, path=f"{book_root}/{parsed.path}")
        return _grounding_exists(root, base, head, parsed)
    repository = repositories.get(parsed.repository)
    if repository is None:
        return False
    local_ref = replace(parsed, repository="")
    return _grounding_exists(
        Path(repository.checkout).resolve(),
        repository.base,
        repository.head,
        local_ref,
    )


def _git_bytes(root: Path, *args: str) -> bytes:
    """Raw stdout."""
    result = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if result.returncode:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed")
    return result.stdout


def _git(root: Path, *args: str) -> str:
    """Decoded leniently: every caller but `_revision_text` wants path lists or hunk headers, which are ASCII, and would rather see a replacement character inside one line of a diff than lose the whole listing."""
    return _git_bytes(root, *args).decode("utf-8", errors="replace")


def relation_subject(value: str) -> tuple[str | None, str]:
    """Split a relation bullet into the subject it names and the claim it makes."""
    match = _RELATION_SUBJECT_RE.match(value.strip())
    if match is None:
        return None, value.strip()
    return match.group(1), match.group(2).strip()


def _relation_join_key(value: str) -> str:
    """What the fixpoint compares two relation bullets on: the subject, or the whole value."""
    subject, _ = relation_subject(value)
    return subject if subject is not None else value.strip()


def _owner_node(node: dict[str, Any]) -> OwnerNode:
    bullets = node.get("bullets", {})
    return OwnerNode(
        str(node.get("surface") or ""),
        {key: tuple(refs_mod.code_refs(bullets.get(key))) for key in registry.owning_keys(str(node.get("type", "")))},
    )


def _cli_binaries(book: Mapping[str, BookNode]) -> dict[str, str]:
    """Every `cli` file node's declared `binary:`, keyed by the file `path` its `command` sections share."""
    binaries: dict[str, str] = {}
    for node in book.values():
        if node.type != "cli" or node.kind != "file":
            continue
        values = node.bullets.get("binary", ())
        binary = bullet_text(values[0]) if values else ""
        if binary:
            binaries[node.path] = binary
    return binaries


def _server_origins(book: Mapping[str, BookNode]) -> dict[str, str]:
    """The origin a page's HTTP claims are sent to, keyed by file `path`: a `server` file's own `entry-url:`, and the same for every page whose `server:` links that file."""
    origins: dict[str, str] = {}
    for node in book.values():
        if node.type != "server" or node.kind != "file":
            continue
        values = node.bullets.get(reach.ENTRY_URL_BULLET, ())
        origin = reach.url_origin(bullet_text(values[0])) if values else ""
        if origin:
            origins[node.path] = origin
    linked: dict[str, str] = {}
    for node in book.values():
        for edge in node.edges:
            origin = origins.get(edge.to.split("#", 1)[0]) if edge.via == "server" else None
            if origin and node.path not in origins:
                linked[node.path] = origin
    return origins | linked


def _scenario_fixtures(book: Mapping[str, BookNode]) -> list[str]:
    """Every `fixture` file that states `lifetime: scenario`, by the name a `fixture:` bullet calls it."""
    names: set[str] = set()
    for node in book.values():
        if node.type != "fixture" or node.kind != "file":
            continue
        values = node.bullets.get("lifetime", ())
        if values and bullet_text(values[0]) == "scenario":
            names.add(Path(node.path).stem)
    return sorted(names)


def _browser_fixtures(book: Mapping[str, BookNode]) -> list[str]:
    """Every `fixture` file that signs a browser in, by its own step or a fixture it `needs:`."""
    fixtures = {node.path: node for node in book.values() if node.type == "fixture" and node.kind == "file"}
    signing = {
        node.path for node in book.values()
        if node.type == "step" and node.path in fixtures and any(node.bullets.get(key) for key in BROWSER_KEYS)
    }
    grew = True
    while grew:
        needing = {
            path for path, node in fixtures.items()
            if any(edge.via == "needs" and edge.to.split("#", 1)[0] in signing for edge in node.edges)
        }
        grew = not needing <= signing
        signing |= needing
    return sorted(Path(path).stem for path in signing)


def _fixture_screens(book: Mapping[str, BookNode]) -> dict[str, str]:
    """The screen each `fixture` file leaves the scenario's browser on: the one its own last `open:` links when each scenario builds it, else the one the last fixture it `needs:` leaves."""
    fixtures = {node.path: node for node in book.values() if node.type == "fixture" and node.kind == "file"}
    per_scenario = set(_scenario_fixtures(book))
    opened: dict[str, tuple[int, str]] = {}
    for node in book.values():
        if node.type != "step" or node.path not in fixtures or Path(node.path).stem not in per_scenario:
            continue
        screens = [edge.to.split("#", 1)[0] for edge in node.edges if edge.via == "open" and edge.to]
        if screens and node.line >= opened.get(node.path, (-1, ""))[0]:
            opened[node.path] = (node.line, screens[0])

    def left_on(path: str, seen: frozenset[str]) -> str | None:
        if path in opened:
            return opened[path][1]
        needs = [edge.to for edge in fixtures[path].edges if edge.via == "needs" and edge.to in fixtures and edge.to not in seen]
        return next((screen for need in reversed(needs) if (screen := left_on(need, seen | {path}))), None)

    return {Path(path).stem: screen for path in sorted(fixtures) if (screen := left_on(path, frozenset({path})))}


def _fragment_hosts(book: Mapping[str, BookNode]) -> dict[str, str]:
    """The page each `fragment` page continues, by the fragment's file `path`: the one its `host:` bullet links."""
    hosts: dict[str, str] = {}
    for node in book.values():
        if node.type != "fragment" or node.kind != "file":
            continue
        linked = sorted({edge.to.split("#", 1)[0] for edge in node.edges if edge.via == "host" and edge.to})
        if len(linked) == 1:
            hosts[node.path] = linked[0]
    return hosts


def _run_binaries_by_path(book: Mapping[str, BookNode]) -> dict[str, str]:
    """The executable a page's `run:` resolves to, keyed by the page's file `path`.

    A `cli` file resolves to its own declared binary. Any other file of a surface with exactly one
    `cli` file borrows that file's binary, so a format's field that states a `run:` names the same
    executable the surface's commands do.
    """
    declared = _cli_binaries(book)
    files = [node for node in book.values() if node.kind == "file"]
    cli_paths_by_surface: dict[str, list[str]] = {}
    for node in files:
        if node.type == "cli":
            cli_paths_by_surface.setdefault(node.surface, []).append(node.path)
    binaries = dict(declared)
    for node in files:
        surface_cli_paths = cli_paths_by_surface.get(node.surface, [])
        if node.type != "cli" and len(surface_cli_paths) == 1 and surface_cli_paths[0] in declared:
            binaries[node.path] = declared[surface_cli_paths[0]]
    return binaries


def _named_subjects(node: BookNode) -> set[str]:
    """Every subject this node names, pooled across the relation and event bullets."""
    subjects = {
        subject
        for key in RELATION_KEYS
        for value in node.bullets.get(key, ())
        if (subject := relation_subject(value)[0]) is not None
    }
    for key in _EVENT_KEYS:
        for value in node.bullets.get(key, ()):
            subject, _ = relation_subject(value)
            subjects.add(subject if subject is not None else value.strip())
    return {subject for subject in subjects if subject}


def _missing_declared_checks(node: BookNode) -> list[HealthRow]:
    """A health row per normative claim of a checked node type that declares no check to fulfil it."""
    if not registry.check_keys(node.type):
        return []
    _, checks_per_bullet = registry.attributed_checks(node.type, node.bullet_order, node.combiners)
    return [
        HealthRow(
            kind="missing-declared-check",
            severity="warning",
            node=node.id,
            key=key,
            message=f"impacted contract's `{key}:` claim declares no `verify:` check to fulfil it",
        )
        for key in registry.normative_keys(node.type)
        for index in range(1, len(node.bullets.get(key, ())) + 1)
        if not checks_per_bullet.get((key, index))
    ]


def _merge_snapshot_nodes(
    base: dict[str, dict[str, Any]],
    head: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Head wins; base contributes only the nodes head no longer has."""
    merged = {node_id: {**node, "bullets": dict(node.get("bullets", {}))} for node_id, node in base.items()}
    for node_id, node in head.items():
        combined = {**merged.get(node_id, {}), **node}
        combined["bullets"] = dict(node.get("bullets", {}))
        merged[node_id] = combined
    return merged


def _code_path(value: str) -> str:
    return refs_mod.ref_path(refs_mod.normalize_ref(value))


def _as_ref(candidate: str) -> str:
    """``path`` or ``path::name`` when ``candidate`` opens with a citable file, else ``""``."""
    path, separator, symbol = candidate.strip().partition("::")
    path, symbol = path.strip(), symbol.strip()
    if not path or path.split() != [path] or Path(path).suffix.lower() not in _CITABLE_SUFFIXES:
        return ""
    return f"{path}::{symbol}" if separator and symbol else path


def _verification_refs(node: BookNode) -> list[str]:
    """Every test a node's ``tests:`` bullets cite, as ``path`` or ``path::name``."""
    refs: list[str] = []
    for value in node.bullets.get("tests", ()):
        spans = markdown.all_code_spans(value)
        if spans:
            found = [_as_ref(span) for span in spans]
        else:
            found = []
            for chunk in value.split(","):
                words = chunk.split()
                starts = (i for i, w in enumerate(words) if _as_ref(w.partition("::")[0]))
                index = next(starts, None)
                found.append("" if index is None else _as_ref(" ".join(words[index:])))
        refs.extend(ref for ref in found if ref)
    return list(dict.fromkeys(refs))


def _is_non_production_path(path: str) -> bool:
    candidate = path.lower()
    parts = Path(candidate).parts
    non_production_dirs = {
        "test",
        "tests",
        "__tests__",
        "testdata",
        "__snapshots__",
        "snapshots",
        "fixtures",
        "fixture",
        "golden",
        "goldens",
        "mocks",
        "__mocks__",
        "stubs",
        "harness",
        "harnesses",
    }
    if any(part in non_production_dirs for part in parts[:-1]):
        return True
    if any(
        part.startswith(("qa-mock", "mock-", "mock_", "qa-fixture", "fake-", "fake_"))
        or part.endswith(("-mocks", "-mock-backends", "-fixtures"))
        for part in parts[:-1]
    ):
        return True
    name = parts[-1] if parts else candidate
    if name.startswith("test_") or name.endswith(("_test.py", "_test.go")):
        return True
    if any(token in name for token in (".test.", ".spec.")):
        return True
    if name.endswith(".md") and not any(part in {"prompts", "templates"} for part in parts[:-1]):
        return True
    if name.endswith((".lock", ".rst")) or name in {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "uv.lock",
        "readme.md",
        "changelog.md",
        "license.md",
    }:
        return True
    build_config_names = {
        "makefile",
        "dockerfile",
        ".gitignore",
        ".dockerignore",
        "go.mod",
        "go.sum",
        "go.work",
        "go.work.sum",
        "package.json",
        "tsconfig.json",
        "vite.config.ts",
        "pubspec.yaml",
        "pubspec.lock",
        "analysis_options.yaml",
        ".mockery.yaml",
    }
    if name in build_config_names:
        return True
    if name.startswith("pulumi.") and name.endswith((".yaml", ".yml")):
        return True
    if name.endswith(".log"):
        return True
    if len(parts) == 1 and name in {"agents.yml", "qa-stack.yml"}:
        return True
    if name == ".source-inventory.json":
        return True
    return bool(
        parts and parts[0] in {".github", ".gitlab", ".agents", ".opencode", ".claude", ".githooks"}
    )


_GENERATED_MARKER = re.compile(r"^\s*(?://|#|/\*|--|<!--)\s*Code generated .*DO NOT EDIT", re.M)

_GENERATED_SUFFIXES = (
    ".gen.go",
    ".pb.go",
    ".pb.gw.go",
    ".gen.ts",
    ".gen.tsx",
    ".generated.ts",
    ".g.dart",
    ".gr.dart",
    ".gen.dart",
    ".freezed.dart",
    "_pb2.py",
    "_pb2_grpc.py",
    "_generated.go",
    "_generated.py",
    "_generated.ts",
)

_GENERATED_DIRS = {"mocks", "__mocks__", "generated", "node_modules", "vendor"}

_MARKER_SCAN_BYTES = 4096


def _is_generated_unit(root: Path, change: ChangedUnit) -> bool:
    """Is this changed unit machine-authored, and therefore owned by its generator?"""
    lowered = change.path.lower()
    parts = Path(lowered).parts
    if any(part in _GENERATED_DIRS for part in parts[:-1]):
        return True
    if lowered.endswith(_GENERATED_SUFFIXES):
        return True
    if not change.head_path or Path(change.head_path).is_absolute():
        return False
    try:
        with (root / change.head_path).open("rb") as handle:
            head = handle.read(_MARKER_SCAN_BYTES).decode("utf-8", "replace")
    except OSError:
        return False
    return bool(_GENERATED_MARKER.search(head))


def _is_required(
    node_id: str,
    direct_reasons: dict[str, list[Reason]],
    grounded: set[str],
    shared_files: frozenset[str] | set[str] = frozenset(),
    shared_symbols: frozenset[str] | set[str] = frozenset(),
) -> bool:
    """Whether this node's obligations are owed live evidence, or are only context."""
    kinds = {
        reason.kind
        for reason in direct_reasons.get(node_id, [])
        if not (reason.kind == ReasonKind.FILE_OWNER and reason.ref in shared_files)
        and not (reason.kind == ReasonKind.CHANGED_CODE and reason.ref in shared_symbols)
    }
    grounded_here = node_id in grounded or ReasonKind.BOOK_CLAIM in kinds
    return grounded_here and bool(kinds - _CONTEXT_ONLY_REASON_KINDS)


def _journey_is_required(
    node_id: str,
    direct_reasons: dict[str, list[Reason]],
    required_contracts: set[str],
    end_edges: set[tuple[str, str]],
) -> bool:
    """Whether this flow is owed live evidence, or is only context. A whole book owes every one of its flows."""
    if any(reason.kind == ReasonKind.BOOK_CLAIM for reason in direct_reasons.get(node_id, [])):
        return True
    reasons = [
        reason
        for reason in direct_reasons.get(node_id, [])
        if reason.kind == ReasonKind.FLOW_LINKS_CONTRACT
        and _reaches_a_required_contract(reason.ref, required_contracts)
    ]
    reaches_the_end = any((node_id, reason.ref) in end_edges for reason in reasons)
    walks_the_route = any((node_id, reason.ref) not in end_edges for reason in reasons)
    return reaches_the_end and walks_the_route


def _reaches_a_required_contract(ref: str, required_contracts: set[str]) -> bool:
    """The linked node is required, or — for a whole document — some section of it is."""
    if ref in required_contracts:
        return True
    if "#" in ref:
        return False
    return any(contract.startswith(f"{ref}#") for contract in required_contracts)


LocatorTarget = dict[str, Any]


def _parse_checks(
    values: list[str],
    resolve: Callable[[str], LocatorTarget] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = checks_mod.parse_check(value)
        if not isinstance(parsed, checks_mod.CheckCall):
            continue
        row: dict[str, Any] = {"call": parsed.text(), "name": parsed.name, "args": parsed.args}
        if resolve is not None:
            located = {
                param.name: resolve(str(parsed.args[param.name]))
                for param in checks_mod.CHECK_BY_NAME[parsed.name].params
                if param.locator and param.name in parsed.args
            }
            if located:
                row["locates"] = located
        rows.append(row)
    return rows


def _unparsed_checks(values: list[str]) -> list[dict[str, Any]]:
    """The `verify:` bullets among *values* the parser read and refused, with its own account."""
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = checks_mod.parse_check(value)
        if isinstance(parsed, checks_mod.Refusal):
            rows.append({"value": value, "kind": parsed.kind, "problem": parsed.message})
    return list({row["value"]: row for row in rows}.values())


def _locator_resolver(
    graph: Graph, book: Mapping[str, BookNode], node: BookNode
) -> Callable[[str], LocatorTarget]:
    """Resolve this node's check locators against the book, the way `doctor` resolves them."""
    origin = graph.root / node.path

    def resolve(value: str) -> LocatorTarget:
        located = locators_mod.located_node(graph, value, origin)
        if located is None:
            return {"node": "", "locators": {}}
        serialized = book.get(located.id)
        return {
            "node": located.id,
            "locators": declared_locators(serialized) if serialized is not None else {},
        }

    return resolve


def _dedup_checks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list({row["call"]: row for row in rows}.values())


def _fixture_provides_index(book: Mapping[str, BookNode]) -> dict[str, list[str]]:
    """Every book fixture's own `provides:` keys, plus every one reachable through `needs:`."""
    resolved = _fixture_provides_closure(book)
    return {name: sorted(ref for ref, _ in pairs) for name, pairs in resolved.items()}


def _fixture_undetermined_index(book: Mapping[str, BookNode]) -> dict[str, list[str]]:
    """Every reachable `provides:` key whose *source* the book left undetermined, by fixture stem."""
    resolved = _fixture_provides_closure(book)
    return {name: sorted(ref for ref, bad in pairs if bad) for name, pairs in resolved.items()}


def _fixture_needs_index(book: Mapping[str, BookNode]) -> dict[str, frozenset[str]]:
    """Every book fixture's stem, with the stem of each fixture it reaches through `needs:`."""
    fixtures = {node_id: node for node_id, node in book.items() if node.type == "fixture"}
    direct = {node_id: [edge.to for edge in node.edges if edge.via == "needs" and edge.to in fixtures]
              for node_id, node in fixtures.items()}
    index: dict[str, frozenset[str]] = {}
    for start in fixtures:
        reached: set[str] = set()
        pending = list(direct[start])
        while pending:
            node_id = pending.pop()
            if node_id not in reached:
                reached.add(node_id)
                pending.extend(direct[node_id])
        index[Path(start).stem] = frozenset(Path(node_id).stem for node_id in reached - {start})
    return index


def _needs_first(rows: list[dict[str, Any]], needs: Mapping[str, frozenset[str]] | None) -> list[dict[str, Any]]:
    """*rows* in the order stated, except that each fixture follows every listed fixture it needs."""
    pending = list(rows)
    ordered: list[dict[str, Any]] = []
    while pending:
        row = next((row for row in pending
                    if not any(other["name"] in (needs or {}).get(row["name"], ()) for other in pending if other is not row)),
                   pending[0])
        pending = [other for other in pending if other is not row]
        ordered.append(row)
    return ordered


def _fixture_provides_closure(
    book: Mapping[str, BookNode],
) -> dict[str, set[tuple[str, bool]]]:
    """`{fixture stem: {(`<owner>.<key>`, source-undetermined), ...}}` over the `needs:` closure."""
    fixtures = {node_id: node for node_id, node in book.items() if node.type == "fixture"}
    provides: dict[str, set[tuple[str, bool]]] = {}
    needs: dict[str, set[str]] = {}
    for node_id, node in fixtures.items():
        keys: set[tuple[str, bool]] = set()
        stated: dict[str, Mapping[str, str]] = {}
        for entry in node.entries.get("provides", ()):
            head = entry.headline.partition("—")[0].split()
            if head:
                stated[head[0]] = entry.properties
        for value in node.bullets.get("provides", ()):
            head = value.partition("—")[0].split()
            if not head:
                continue
            properties = stated.get(head[0], {})
            observed = bool(properties.get("from"))
            asserted = bool(properties.get("is"))
            keys.add((head[0], observed == asserted))
        provides[node_id] = keys
        needs[node_id] = {edge.to for edge in node.edges if edge.via == "needs" and edge.to in fixtures}

    closure: dict[str, set[tuple[str, bool]]] = {}

    def resolve(node_id: str, seen: frozenset[str]) -> set[tuple[str, bool]]:
        if node_id in closure:
            return closure[node_id]
        if node_id in seen:
            return set()
        owner = Path(node_id).stem
        pairs = {(f"{owner}.{key}", bad) for key, bad in provides.get(node_id, ())}
        for dep in needs.get(node_id, ()):
            pairs |= resolve(dep, seen | {node_id})
        closure[node_id] = pairs
        return pairs

    return {Path(node_id).stem: resolve(node_id, frozenset()) for node_id in fixtures}


def _parse_captures(values: list[str]) -> list[dict[str, Any]]:
    """The `capture: <name> from <json path | UI locator>` declarations among *values*."""
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = captures_mod.parse_bullet(value)
        if isinstance(parsed, captures_mod.CaptureDecl):
            rows.append({"name": parsed.name, "from": parsed.source})
    return list({row["name"]: row for row in rows}.values())


def _unparsed_captures(values: list[str]) -> list[dict[str, Any]]:
    """The `capture:` bullets among *values* the parser read and refused, with its own account."""
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = captures_mod.parse_bullet(value)
        if isinstance(parsed, str):
            rows.append({"value": value, "problem": parsed})
    return list({row["value"]: row for row in rows}.values())


def _parse_acts(
    values: list[str],
    resolve: Callable[[str], LocatorTarget] | None = None,
) -> list[dict[str, Any]]:
    """The acts among *values*, in document order, each with its locator arguments resolved."""
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = acts_mod.parse_act(value)
        if not isinstance(parsed, acts_mod.ActCall):
            continue
        row: dict[str, Any] = {"call": parsed.text(), "name": parsed.name, "args": parsed.args}
        if resolve is not None:
            located = {
                param.name: resolve(parsed.args[param.name])
                for param in acts_mod.ACT_BY_NAME[parsed.name].params
                if param.locator and param.name in parsed.args
            }
            if located:
                row["locates"] = located
        rows.append(row)
    return list({row["call"]: row for row in rows}.values())


def _unparsed_acts(values: list[str]) -> list[dict[str, Any]]:
    """The `arrange:` bullets among *values* the act parser read and refused, with its account."""
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = acts_mod.parse_act(value)
        if isinstance(parsed, checks_mod.Refusal):
            rows.append({"value": value, "kind": parsed.kind, "problem": parsed.message})
    return list({row["value"]: row for row in rows}.values())


def _parse_fixtures(
    values: list[str],
    fixture_provides: dict[str, list[str]] | None = None,
    fixture_undetermined: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """The declared arrangements among *values*, in order, deduped on name and arguments."""
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = fixtures_mod.parse_bullet(value)
        if isinstance(parsed, fixtures_mod.FixtureRef):
            row = {"name": parsed.name, "args": list(parsed.args), "provides": parsed.provides}
            keys = (fixture_provides or {}).get(parsed.name)
            if keys:
                row["providesKeys"] = keys
            undetermined = (fixture_undetermined or {}).get(parsed.name)
            if undetermined:
                row["providesUndetermined"] = undetermined
            rows.append(row)
    return list({(row["name"], tuple(row["args"])): row for row in rows}.values())


def _unparsed_fixtures(values: list[str]) -> list[dict[str, Any]]:
    """The `fixture:` bullets among *values* the parser read and rejected, with its sentence."""
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = fixtures_mod.parse_bullet(value)
        if isinstance(parsed, str):
            rows.append({"value": value, "problem": parsed})
    return list({row["value"]: row for row in rows}.values())


def _no_arrangement_stated(values: list[str]) -> bool:
    """True when one of *values* is a `fixture:` bullet stating this node arranges nothing."""
    return any(
        isinstance(fixtures_mod.parse_bullet(value), fixtures_mod.NoArrangement)
        for value in values
    )


def _same_as_component(node_id: str, book: Mapping[str, BookNode]) -> frozenset[str]:
    """Every node id reachable from *node_id* by following declared `same-as:` edges, *node_id* included."""
    seen = {node_id}
    frontier = [node_id]
    while frontier:
        current = frontier.pop()
        node = book.get(current)
        if node is None:
            continue
        for target in node.targets("same-as", book):
            if target.id not in seen:
                seen.add(target.id)
                frontier.append(target.id)
    return frozenset(seen)


def _document_of(node_id: str) -> str:
    """The document part of a node id — everything ahead of its first `#`."""
    return node_id.split("#", 1)[0]


def _family_root(node_id: str, owners: set[str], book: Mapping[str, BookNode]) -> str:
    """The declared-family root *node_id* belongs to among *owners*, for `CONTAINER_FANOUT`."""
    seen: set[str] = set()
    current = node_id
    while current not in seen:
        seen.add(current)
        same_as_root = min(_same_as_component(current, book))
        if same_as_root != current:
            current = same_as_root
            continue
        node = book.get(current)
        if node is not None:
            target = resolve_extends(node, book).target
            if target is not None:
                current = target.id
                continue
        file_id, sep, _anchor = current.partition("#")
        if sep and file_id in owners:
            current = file_id
            continue
        break
    return current


_Claim = tuple[str, int]


@dataclass(frozen=True, slots=True)
class _Attributed:
    """One kind of bullet a node declares, split into the node's own and each claim's."""

    own: list[str]
    per_claim: dict[_Claim, list[str]]

    def of(self, claim: _Claim) -> list[str]:
        return self.per_claim.get(claim, [])


@dataclass(frozen=True, slots=True)
class _Attribution:
    """A node's checks, fixtures, acts and captures, each attributed to the node or to one claim under it."""

    checks: _Attributed
    fixtures: _Attributed
    acts: _Attributed
    captures: _Attributed


@dataclass(frozen=True, slots=True)
class _Parts:
    """The checks, fixtures, acts and captures one obligation declares, with the bullets each parser refused."""

    checks: list[dict[str, Any]]
    checks_unparsed: list[dict[str, Any]]
    fixtures: list[dict[str, Any]]
    fixtures_unparsed: list[dict[str, Any]]
    arranges_nothing: bool
    acts: list[dict[str, Any]]
    acts_unparsed: list[dict[str, Any]]
    captures: list[dict[str, Any]]
    captures_unparsed: list[dict[str, Any]]

    def stamp(self, obligation: dict[str, Any]) -> None:
        """Write each part that is present onto *obligation*, and drop each one that is absent."""
        fields: tuple[tuple[str, object], ...] = (
            ("checksDeclared", self.checks),
            ("checksUnparsed", self.checks_unparsed),
            ("fixturesDeclared", self.fixtures),
            ("fixturesUnparsed", self.fixtures_unparsed),
            ("arrangesNothing", self.arranges_nothing),
            ("actsDeclared", self.acts),
            ("actsUnparsed", self.acts_unparsed),
            ("capturesDeclared", self.captures),
            ("capturesUnparsed", self.captures_unparsed),
        )
        for key, value in fields:
            if value:
                obligation[key] = value
            else:
                obligation.pop(key, None)


@dataclass(frozen=True, slots=True)
class _PartReader:
    """What parsing a node's parts reads from the book: its locators and each fixture's provided keys."""

    resolve_locator: Callable[[str], LocatorTarget] | None
    fixture_provides: dict[str, list[str]] | None
    fixture_undetermined: dict[str, list[str]] | None
    fixture_needs: Mapping[str, frozenset[str]] | None

    def node_parts(self, attribution: _Attribution) -> _Parts:
        """The parts the node states for every claim under it."""
        fixtures = attribution.fixtures.own
        return _Parts(
            checks=_dedup_checks(_parse_checks(attribution.checks.own, self.resolve_locator)),
            checks_unparsed=_unparsed_checks(attribution.checks.own),
            fixtures=_needs_first(_parse_fixtures(fixtures, self.fixture_provides, self.fixture_undetermined),
                                  self.fixture_needs),
            fixtures_unparsed=_unparsed_fixtures(fixtures),
            arranges_nothing=_no_arrangement_stated(fixtures),
            acts=_parse_acts(attribution.acts.own, self.resolve_locator),
            acts_unparsed=_unparsed_acts(attribution.acts.own),
            captures=[],
            captures_unparsed=_unparsed_captures(attribution.captures.own),
        )

    def claim_parts(self, node: _Parts, attribution: _Attribution, claim: _Claim) -> _Parts:
        """The parts one claim owes: its own checks and captures, and its fixtures and acts on top of the node's."""
        checks = attribution.checks.of(claim)
        fixtures = attribution.fixtures.of(claim)
        acts = attribution.acts.of(claim)
        captures = attribution.captures.of(claim)
        arranged = _parse_fixtures(fixtures, self.fixture_provides, self.fixture_undetermined)
        return _Parts(
            checks=_dedup_checks(_parse_checks(checks, self.resolve_locator)),
            checks_unparsed=_unparsed_checks(checks),
            fixtures=_needs_first(list({(row["name"], tuple(row["args"])): row for row in [*node.fixtures, *arranged]}.values()),
                                  self.fixture_needs),
            fixtures_unparsed=_dedup_by_value([*node.fixtures_unparsed, *_unparsed_fixtures(fixtures)]),
            arranges_nothing=node.arranges_nothing or _no_arrangement_stated(fixtures),
            acts=list({row["call"]: row for row in [*node.acts, *_parse_acts(acts, self.resolve_locator)]}.values()),
            acts_unparsed=_dedup_by_value([*node.acts_unparsed, *_unparsed_acts(acts)]),
            captures=_parse_captures(captures),
            captures_unparsed=_unparsed_captures(captures),
        )


def _obligations(
    book_node: BookNode,
    reasons: list[Reason],
    *,
    journey: bool,
    required: bool = True,
    owed_keys: frozenset[str] | None = None,
    scope: tuple[str, ...] = (),
    judgment: list[dict[str, Any]] | None = None,
    fixture_provides: dict[str, list[str]] | None = None,
    fixture_undetermined: dict[str, list[str]] | None = None,
    fixture_needs: Mapping[str, frozenset[str]] | None = None,
    resolve_locator: Callable[[str], LocatorTarget] | None = None,
    book: Mapping[str, BookNode],
    walks: Mapping[str, tuple[str, ...]] | None = None,
) -> list[dict[str, Any]]:
    """Mint one obligation per normative bullet, plus the node-level contract."""
    required = required and owes_live_evidence(book_node.type, book_node.page_type)
    family = _same_as_component(book_node.id, book)
    representative = min(family)
    base = _node_obligation(book_node, reasons, family, journey=journey, required=required, scope=scope, book=book)
    reader = _PartReader(resolve_locator, fixture_provides, fixture_undetermined, fixture_needs)
    ambient = [*_guard_fixtures(book_node, book, walks or {}), *_parent_fixtures(book_node, book)]
    attribution = _with_ambient_fixtures(_attribution(book_node), ambient)
    node_parts = reader.node_parts(attribution)
    node_parts.stamp(base)
    base["docPosition"] = [book_node.line, -1]
    undetermined = _undetermined_claims(book_node)
    positions = _doc_positions(book_node)
    output = [base]
    for key in registry.normative_keys(book_node.type):
        for index, requirement in enumerate(book_node.bullets.get(key, ()), start=1):
            claim = (key, index)
            if registry.states_no_claim(key, requirement):
                continue
            obligation = _claim_obligation(
                base,
                book_node,
                claim,
                requirement,
                representative=representative,
                position=positions.get(claim, 0),
                book=book,
            )
            if claim in undetermined:
                obligation["claimCombiner"] = "unstated"
            if required and owed_keys is not None and key not in owed_keys:
                obligation["required"] = False
                obligation["evidenceRequired"] = "context"
            reader.claim_parts(node_parts, attribution, claim).stamp(obligation)
            output.append(obligation)
    _discharge_address_pair(book_node.type, output)
    if judgment:
        base["judgment"] = judgment
    unspecified = _unspecified(book_node)
    if unspecified:
        base["unspecified"] = unspecified
    return output


def _discharge_address_pair(node_type: str, minted: list[dict[str, Any]]) -> None:
    """Stop owing a check on an address bullet when the check under its pair already proves the address."""
    pair = [o for o in minted if o["kind"] in registry.address_keys(node_type)]
    if not any(o.get("checksDeclared") for o in pair):
        return
    for obligation in pair:
        if not obligation.get("checksDeclared"):
            obligation["required"] = False
            obligation["evidenceRequired"] = "context"


def _node_obligation(
    book_node: BookNode,
    reasons: list[Reason],
    family: frozenset[str],
    *,
    journey: bool,
    required: bool,
    scope: tuple[str, ...],
    book: Mapping[str, BookNode],
) -> dict[str, Any]:
    """The node-level contract or end-state obligation, before its parts are stamped on."""
    obligation: dict[str, Any] = {
        "id": f"okf:{min(family)}:{'end-state' if journey else 'contract'}",
        "kind": "journey" if journey else "contract",
        "node": book_node.id,
        "occurrenceDocuments": sorted({_document_of(member) for member in family}),
        "nodeType": book_node.type,
        "source": book_node.path,
        "surface": book_node.surface,
        "requirement": book_node.title or book_node.id,
        "required": required,
        "evidenceRequired": "live" if required else "context",
        "reasons": [reason.row() for reason in reasons or [Reason(ReasonKind.GRAPH_CLOSURE, book_node.id)]],
    }
    obligation.update(obligation_frame(book_node, locators_mod.repeat_contract(book_node, scope), book).row())
    return obligation


def _claim_obligation(
    base: dict[str, Any],
    book_node: BookNode,
    claim: _Claim,
    requirement: str,
    *,
    representative: str,
    position: int,
    book: Mapping[str, BookNode],
) -> dict[str, Any]:
    """One claim's obligation, the node's obligation restated for the claim's own requirement and subject."""
    key, index = claim
    obligation = {
        **base,
        "id": f"okf:{representative}:{key.replace(' ', '-')}:{index}",
        "kind": key.replace(" ", "-"),
        "requirement": requirement,
        "docPosition": [book_node.line, position],
    }
    if key in RELATION_KEYS or key in _EVENT_KEYS:
        subject, prose = relation_subject(requirement)
        obligation["requirement"] = prose
        if subject is not None:
            obligation["subject"] = subject
    if book_node.type == "flow":
        linked = linked_surface(book_node, (requirement,), book)
        if linked:
            obligation["surface"] = linked
    return obligation


def _attribution(book_node: BookNode) -> _Attribution:
    """The node's checks, fixtures, acts and captures, attributed the way the registry combines its claims."""
    args = (book_node.type, book_node.bullet_order, book_node.combiners)
    return _Attribution(
        checks=_Attributed(*registry.attributed_checks(*args)),
        fixtures=_Attributed(*registry.attributed_fixtures(*args)),
        acts=_Attributed(*registry.attributed_acts(*args)),
        captures=_Attributed(*registry.attributed_captures(*args)),
    )


def _screen_hosting(book_node: BookNode, book: Mapping[str, BookNode]) -> BookNode | None:
    """The screen *book_node* is shown on: its own file's node, or the page a fragment file's `host:` links."""
    page = book.get(book_node.id.split("#", 1)[0])
    if page is not None and page.type == "fragment":
        hosts = sorted({edge.to.split("#", 1)[0] for edge in page.edges if edge.via == "host" and edge.to})
        page = book.get(hosts[0]) if len(hosts) == 1 else None
    return page if page is not None and page.type == "screen" else None


def _walks(navigation: Mapping[str, Mapping[str, Any]]) -> dict[str, tuple[str, ...]]:
    """Each routed screen's walk: every screen a scenario passes through to reach it, the screen itself last."""
    return {
        screen: (*(hop["from"] for hop in hops), screen)
        for surface in navigation.values()
        for screen, hops in surface.get("routes", {}).items()
    }


def _guard_fixtures(
    book_node: BookNode, book: Mapping[str, BookNode], walks: Mapping[str, tuple[str, ...]],
) -> list[str]:
    """The fixture each `requires:` guard links, by name, of every screen the walk to *book_node*'s screen passes through."""
    screen = _screen_hosting(book_node, book)
    if screen is None:
        return []
    passed = [page for screen_id in walks.get(screen.id, (screen.id,)) if (page := book.get(screen_id)) is not None]
    linked = [edge.to for page in passed for edge in page.edges if edge.via == reach.GUARD_BULLET and edge.to]
    return list(dict.fromkeys(
        Path(target).stem for target in linked if (node := book.get(target)) is not None and node.type == "fixture"))


def _parent_fixtures(book_node: BookNode, book: Mapping[str, BookNode]) -> list[str]:
    """The node-level fixtures of each component *book_node* sits inside through `parent:`, outermost first."""
    chain: list[BookNode] = []
    seen = {book_node.id}
    node: BookNode | None = book_node
    while node is not None:
        targets = sorted(edge.to for edge in node.edges if edge.via == "parent" and edge.to in book)
        node = book[targets[0]] if targets and targets[0] not in seen else None
        if node is not None:
            seen.add(node.id)
            chain.append(node)
    return [bullet for parent in reversed(chain) for bullet in _attribution(parent).fixtures.own]


def _with_ambient_fixtures(attribution: _Attribution, ambient: list[str]) -> _Attribution:
    """*attribution* with each fixture its screen's guards or its parents arrange ambient to every claim, ahead of the node's own."""
    if not ambient:
        return attribution
    fixtures = _Attributed([*ambient, *attribution.fixtures.own], attribution.fixtures.per_claim)
    return replace(attribution, fixtures=fixtures)


def _undetermined_claims(book_node: BookNode) -> set[_Claim]:
    """The claims whose combiner the node leaves unstated."""
    groups = registry.undetermined_claims(book_node.type, book_node.bullet_order, book_node.combiners)
    return {claim for group in groups.values() for claim in group}


def _doc_positions(book_node: BookNode) -> dict[_Claim, int]:
    """Each normative claim's position in the node's document, by key and index."""
    positions: dict[_Claim, int] = {}
    seen = {key: 0 for key in registry.normative_keys(book_node.type)}
    for key, _, position in book_node.bullet_order:
        if key in seen:
            seen[key] += 1
            positions[(key, seen[key])] = position
    return positions


def _unspecified(book_node: BookNode) -> list[dict[str, str]]:
    """The node's `unspecified:` bullets, each with the first link it cites."""
    return [
        {
            "text": value,
            "citation": next((href for _t, href in markdown.extract_refs(value).links), ""),
        }
        for value in book_node.bullets.get("unspecified", ())
    ]


def _dedup_by_value(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list({row["value"]: row for row in rows}.values())


def _acceptance_criteria(story_file: Path | None) -> list[dict[str, str]]:
    if story_file is None or not story_file.is_file():
        return []
    doc = markdown.split(story_file.read_text(encoding="utf-8"))
    criteria: list[dict[str, str]] = []
    sections = (
        ("Acceptance Criteria", "ac", "functional"),
        ("Non-Functional Acceptance Criteria", "nfac", "non-functional"),
    )
    for heading, prefix, category in sections:
        section = doc.find_section(heading)
        if section is None:
            continue
        for index, bullet in enumerate(section.bullets, start=1):
            text = bullet.text.strip()
            match = _AC_RE.match(text)
            number, requirement = (match.group(1), match.group(2)) if match else (str(index), text)
            criteria.append({
                "id": f"{prefix}:{number}",
                "requirement": requirement,
                "kind": "behavioral",
                "category": category,
            })
    return criteria


def _story_identity(story_file: Path | None) -> dict[str, str]:
    if story_file is None or not story_file.is_file():
        return {}
    frontmatter = markdown.split(story_file.read_text(encoding="utf-8")).frontmatter or {}
    values = {
        "id": str(frontmatter.get("id") or ""),
        "externalKey": str(frontmatter.get("externalKey") or ""),
        "slug": str(frontmatter.get("slug") or story_file.parent.name),
    }
    return {key: value for key, value in values.items() if value}
