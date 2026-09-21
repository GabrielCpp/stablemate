"""Deterministic changed-code to OKF obligation mapping."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from unidiff.patch import PatchSet
from unidiff.errors import UnidiffParseError

from ostler import graph as graph_mod
from ostler import locators as locators_mod
from ostler import acts as acts_mod
from ostler import checks as checks_mod
from ostler import inventory, markdown, path as path_mod, refs as refs_mod, registry, syntax
from ostler.model import Graph, _parse_ui_nodes, load
from ostler import reach
from ostler import routes as routes_mod
from ostler.qa import captures as captures_mod
from ostler.qa import fixtures as fixtures_mod
from ostler.qa.compile import annotate_deferred_obligations
from ostler.qa.outcome import QaOutcome
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

_CONTAINER_FANOUT = 3

RELATION_KEYS = (
    "consistency",
    "consistency rule",
    "consistency group",
    "persistence",
    "event",
    "concurrency",
    "idempotency",
)

_RELATION_REASON_KINDS = frozenset(key.replace(" ", "-") for key in RELATION_KEYS)

_EVENT_KEYS = ("emits", "consumes")

_SHARED_INVARIANT_KEYS = frozenset(RELATION_KEYS) | frozenset(_EVENT_KEYS)

_RELATION_SUBJECT_RE = re.compile(r"^([a-z0-9][a-z0-9._-]*)\s+—\s+(\S.*)$", re.DOTALL)

_RELATION_FANOUT = 6

_CLOSURE_REASON_KINDS = frozenset(
    {
        "contains-impacted-node",
        "flow-links-contract",
        "flow-contract-closure",
        "graph-closure",
        "judgment-context",
    }
)

_COBINDING_REASON_KINDS = frozenset({"event-consumer", "event-producer"}) | _RELATION_REASON_KINDS

_CONTEXT_ONLY_REASON_KINDS = _CLOSURE_REASON_KINDS | _COBINDING_REASON_KINDS

_LOCATOR_KEYS = tuple(sorted(registry.LOCATOR_KEYS))
_LOCATOR_KEY_RENAME = {"exclusive-with": "exclusiveWith"}


def _sort_key(obligation_id: str) -> list[tuple[int, int | str]]:
    """Order obligation ids so `…:raises:10` follows `…:raises:2`."""
    return [(1, int(part)) if part.isdigit() else (0, part) for part in obligation_id.split(":")]


@dataclass(frozen=True)
class ChangedUnit:
    path: str
    base_path: str
    head_path: str
    status: str
    base_lines: tuple[int, ...]
    head_lines: tuple[int, ...]
    base_symbols: tuple[str, ...]
    head_symbols: tuple[str, ...]
    repository: str = ""
    surface: str = ""
    source_root: str = ""


def _source_ref(repository: str, path: str, symbol: str = "") -> str:
    return refs_mod.render_code_ref(refs_mod.CodeRef(repository, path, symbol))


def _ref_owns_change(value: str, change: ChangedUnit) -> bool:
    """Whether one owning citation names either side of a changed source file."""
    try:
        cited = refs_mod.parse_code_ref(value)
    except ValueError:
        return False
    return (
        cited.repository == change.repository
        and cited.path in {change.base_path, change.head_path}
    )


def _book_root(root: Path, features_root: str) -> str:
    """The book's own root, relative to *root*, when `--features-root` names a nested book."""
    return path_mod.book_prefix_in(root, features_root)


def book_files(root: Path, features_root: str) -> list[dict[str, str]]:
    """Every `*.md` file under the book at *features_root*, with its path and sha256."""
    book_dir = root / features_root if features_root else root
    files: list[dict[str, str]] = []
    if not book_dir.is_dir():
        return files
    for path in book_dir.rglob("*.md"):
        if not path.is_file():
            continue
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


def _book_relative(path: str, book_root: str) -> str:
    """*path* (relative to `root`) rebased onto `book_root`; unchanged outside it."""
    if not book_root or not path:
        return path
    prefix = f"{book_root}/"
    return path[len(prefix):] if path.startswith(prefix) else path


def _matching_refs(refs: set[str], cited: list[str]) -> list[str]:
    """Citations in *cited* that name something in *refs*, tolerant of symbol spelling."""
    parsed_refs = []
    for value in refs:
        try:
            parsed_refs.append(refs_mod.parse_code_ref(value))
        except ValueError:
            continue
    matches: list[str] = []
    for value in cited:
        try:
            citation = refs_mod.parse_code_ref(value)
        except ValueError:
            continue
        if any(
            citation.repository == ref.repository
            and citation.path == ref.path
            and inventory.symbol_parts(citation.symbol) == inventory.symbol_parts(ref.symbol)
            for ref in parsed_refs
        ):
            matches.append(value)
    return sorted(dict.fromkeys(matches))


EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def book_context(
    root: Path,
    *,
    source_roots: dict[str, list[str]] | None = None,
    features_root: str = "",
    repositories: Sequence[SourceRepository] = (),
) -> dict[str, Any]:
    """Every obligation the book currently owns — no story, no diff, nothing to be proportional to."""
    return build_context(
        root,
        base=EMPTY_TREE_SHA,
        head="WORKTREE",
        source_roots=source_roots,
        features_root=features_root,
        repositories=repositories,
    )


def _navigation(head_graph: Graph) -> dict[str, dict[str, Any]]:
    """Every surface's derived screen reachability, keyed by surface (Option C, Amendment 1)."""
    dump = graph_mod.build(head_graph)
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
            navigation[surface] = reach.reachability(head_graph, surface=surface, driver=driver)
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
) -> dict[str, Any]:
    """Map a `base..head` code diff onto the OKF graph and return the obligation packet."""
    root = root.resolve()
    excluded_paths = {str(path) for path in exclude_paths}
    features_root = path_mod.resolve_features_root(features_root, root)
    source_roots = source_roots or {}
    book_root = _book_root(root, features_root)
    book_files_list = book_files(root, features_root)
    story_file_record_value = story_file_record(root, story_file)
    current = load(root, root_overrides={"features": features_root})
    base_graph = _graph_at_revision(root, base, features_root)
    head_graph = current if head == "WORKTREE" else _graph_at_revision(root, head, features_root)
    excluded_doc_roots = {
        path.resolve().relative_to(root).as_posix()
        for path in current.doc_roots.values()
        if path.resolve().is_relative_to(root)
    }
    base_nodes, base_edges, base_ends, base_scopes, base_details = _serialized_graph(base_graph)
    head_nodes, head_edges, head_ends, head_scopes, head_details = _serialized_graph(head_graph)
    nodes_by_id = _merge_snapshot_nodes(base_nodes, head_nodes)
    node_scopes = {**base_scopes, **head_scopes}
    declared_config = {
        item
        for node in nodes_by_id.values()
        for item in refs_mod.code_refs(node.get("bullets", {}).get("config"))
    }
    repository_rows: list[dict[str, Any]] = []
    repositories_by_id = {repository.id: repository for repository in repositories}
    health: list[dict[str, Any]] = []
    if repositories:
        changes_all: list[ChangedUnit] = []
        seen_repositories: set[str] = set()
        for repository in repositories:
            if repository.id in seen_repositories:
                raise ValueError(f"duplicate source repository id {repository.id!r}")
            seen_repositories.add(repository.id)
            checkout = Path(repository.checkout).resolve()
            roots: dict[str, list[str]] = {}
            for scope in repository.scopes:
                roots.setdefault(scope.surface, []).append(scope.root)
            for change in _changed_units(checkout, repository.base, repository.head, roots):
                changes_all.append(replace(
                    change,
                    repository=repository.id,
                    surface=_surface_owner(change.path, roots),
                    source_root=str(checkout),
                ))
            repository_rows.append({
                "id": repository.id,
                "base": repository.base,
                "baseSha": _git(checkout, "rev-parse", "--verify",
                                f"{repository.base}^{{commit}}").strip(),
                "head": repository.head,
                "headSha": (None if repository.head == "WORKTREE" else
                            _git(checkout, "rev-parse", "--verify",
                                 f"{repository.head}^{{commit}}").strip()),
                "headAnchorSha": (_git(checkout, "rev-parse", "HEAD").strip()
                                   if repository.head == "WORKTREE" else None),
                "sourceFingerprint": source_fingerprint(repository),
                "scopes": [scope.model_dump(mode="json") for scope in repository.scopes],
            })
    else:
        changes_all = _changed_units(root, base, head, source_roots)

    changes = [
        change
        for change in changes_all
        if change.path not in excluded_paths
        and (change.repository or not any(
            change.path == prefix or change.path.startswith(prefix.rstrip("/") + "/")
            for prefix in excluded_doc_roots
        ))
        and (
            _source_ref(change.repository, change.path) in declared_config
            or (
                not _is_non_production_path(change.path)
                and not _is_generated_unit(Path(change.source_root) if change.source_root else root,
                                           change)
            )
        )
    ]

    direct_reasons: dict[str, list[dict[str, str]]] = {}
    changed_code: list[dict[str, Any]] = []
    for change in changes:
        change_book_root = "" if change.repository else book_root
        book_path = _book_relative(change.path, change_book_root)
        book_base_path = _book_relative(change.base_path, change_book_root)
        book_head_path = _book_relative(change.head_path, change_book_root)
        refs = {
            *(
                _source_ref(change.repository, book_base_path, symbol)
                for symbol in change.base_symbols
                if change.base_path
            ),
            *(
                _source_ref(change.repository, book_head_path, symbol)
                for symbol in change.head_symbols
                if change.head_path
            ),
        }
        book_change = replace(change, path=book_path, base_path=book_base_path, head_path=book_head_path)
        changed_code.append(
            {
                "path": change.path,
                "repository": change.repository,
                "id": _source_ref(change.repository, change.path),
                "basePath": change.base_path,
                "headPath": change.head_path,
                "status": change.status,
                "baseLines": list(change.base_lines),
                "headLines": list(change.head_lines),
                "baseSymbols": list(change.base_symbols),
                "headSymbols": list(change.head_symbols),
            }
        )
        mapped = change.status == "deleted"
        for node_id, node in nodes_by_id.items():
            bullets = node.get("bullets", {})
            owned_file = False
            for key in registry.owning_keys(str(node.get("type", ""))):
                cited = refs_mod.code_refs(bullets.get(key))
                exact = _matching_refs(refs, cited)
                if exact:
                    mapped = True
                    for ref in exact:
                        direct_reasons.setdefault(node_id, []).append(
                            {"kind": "changed-code", "ref": ref, "key": key}
                        )
                elif not owned_file and any(
                    _ref_owns_change(item, book_change)
                    for item in cited
                ):
                    mapped = owned_file = True
                    direct_reasons.setdefault(node_id, []).append(
                        {
                            "kind": "file-owner",
                            "ref": _source_ref(change.repository, book_path),
                            "key": key,
                        }
                    )
        if not mapped:
            surface = change.surface or _surface_owner(change.path, source_roots)
            surface_nodes = [
                node_id
                for node_id, node in nodes_by_id.items()
                if surface and node.get("surface") == surface
            ]
            if surface_nodes:
                mapped = True
                for node_id in surface_nodes:
                    direct_reasons.setdefault(node_id, []).append(
                        {
                            "kind": "surface-owner",
                            "ref": f"{surface}:{_source_ref(change.repository, book_path)}",
                        }
                    )
            else:
                health.append(
                    {
                        "kind": "unmapped-change",
                        "severity": "error",
                        "path": _source_ref(change.repository, book_path),
                        "message": "changed production unit has no exact symbol, file, or surface owner",
                    }
                )

    file_owners: dict[str, set[str]] = {}
    symbol_owners: dict[str, set[str]] = {}
    for node_id, reasons in direct_reasons.items():
        for reason in reasons:
            if reason["kind"] == "file-owner":
                file_owners.setdefault(reason["ref"], set()).add(node_id)
            elif reason["kind"] == "changed-code":
                symbol_owners.setdefault(reason["ref"], set()).add(node_id)
    shared_files = {
        ref
        for ref, owners in file_owners.items()
        if len({_family_root(node_id, owners, nodes_by_id) for node_id in owners}) > 1
    }
    shared_symbols = {
        ref
        for ref, owners in symbol_owners.items()
        if len({_family_root(node_id, owners, nodes_by_id) for node_id in owners})
        >= _CONTAINER_FANOUT
    }

    impacted = set(direct_reasons)
    for node_id in list(impacted):
        parent = nodes_by_id.get(node_id, {}).get("parent")
        while parent and parent in nodes_by_id:
            if parent not in impacted:
                direct_reasons.setdefault(parent, []).append(
                    {"kind": "contains-impacted-node", "ref": node_id}
                )
            impacted.add(parent)
            parent = nodes_by_id[parent].get("parent")
    edges = base_edges | head_edges
    end_edges = base_ends | head_ends
    flows = {node_id for node_id, node in nodes_by_id.items() if node.get("type") == "flow"}
    journeys = set(impacted & flows)
    for source, target in edges:
        if source in flows and target in impacted:
            journeys.add(source)
            direct_reasons.setdefault(source, []).append(
                {"kind": "flow-links-contract", "ref": target}
            )
    contracts = impacted - flows
    for source, target in edges:
        if source in journeys and target in nodes_by_id and target not in flows:
            contracts.add(target)
            direct_reasons.setdefault(target, []).append(
                {"kind": "flow-contract-closure", "ref": source}
            )

    relation_keys = RELATION_KEYS
    related = True
    while related:
        related = False
        selected = contracts | journeys
        emitted = {
            value
            for node_id in selected
            for value in _values(nodes_by_id[node_id].get("bullets", {}).get("emits"))
        }
        consumed = {
            value
            for node_id in selected
            for value in _values(nodes_by_id[node_id].get("bullets", {}).get("consumes"))
        }
        relation_values = {
            _relation_join_key(value)
            for node_id in selected
            for key in relation_keys
            for value in _values(nodes_by_id[node_id].get("bullets", {}).get(key))
        }
        for node_id, node in nodes_by_id.items():
            if node_id in selected:
                continue
            bullets = node.get("bullets", {})
            reasons: list[dict[str, str]] = []
            for value in _values(bullets.get("consumes")):
                if value in emitted:
                    reasons.append({"kind": "event-consumer", "ref": value})
            for value in _values(bullets.get("emits")):
                if value in consumed:
                    reasons.append({"kind": "event-producer", "ref": value})
            for key in relation_keys:
                for value in _values(bullets.get(key)):
                    join = _relation_join_key(value)
                    if join in relation_values:
                        reasons.append({"kind": key.replace(" ", "-"), "ref": join})
            if reasons:
                (journeys if node.get("type") == "flow" else contracts).add(node_id)
                direct_reasons.setdefault(node_id, []).extend(reasons)
                related = True

    detail_edges = base_details | head_details
    judgment_by_node: dict[str, list[dict[str, Any]]] = {}
    for source, target in sorted(detail_edges):
        if source not in contracts and source not in journeys:
            continue
        concept = nodes_by_id.get(target)
        if not concept or concept.get("type") != "concept":
            continue
        bullets = concept.get("bullets", {})
        judgment_by_node.setdefault(source, []).append(
            {
                "concept": target,
                "title": concept.get("title") or target,
                "rules": _values(bullets.get("rule")),
                "prefers": _values(bullets.get("prefers")),
                "deprecates": _values(bullets.get("deprecates")),
            }
        )
        if target not in contracts and target not in journeys:
            contracts.add(target)
            direct_reasons.setdefault(target, []).append({"kind": "judgment-context", "ref": source})

    selected = contracts | journeys
    verification_index: list[dict[str, Any]] = []
    for node_id, node in sorted(nodes_by_id.items()):
        for ref in _verification_refs(node):
            verification_index.append(
                {"node": node_id, "ref": ref, "path": _code_path(ref), "impacted": node_id in selected}
            )
    verification_refs = [
        {"node": item["node"], "ref": item["ref"], "path": item["path"]}
        for item in verification_index
        if item["impacted"]
    ]
    grounded: set[str] = set()
    for node_id in sorted(selected):
        node = nodes_by_id[node_id]
        for normalized in refs_mod.code_refs(node.get("bullets", {}).get("code")):
            if not _grounding_for_ref(
                root, base, head, normalized, repositories_by_id, book_root
            ):
                health.append(
                    {
                        "kind": "dangling-grounding",
                        "severity": "error",
                        "node": node_id,
                        "ref": normalized,
                        "message": "code grounding resolves in neither base nor head",
                    }
                )
            else:
                grounded.add(node_id)
        node_type = str(node.get("type", ""))
        node_bullets = node.get("bullets", {})
        combiners = {int(pos): str(word) for pos, word in (node.get("combiners") or {}).items()}
        _, checks_per_bullet = registry.attributed_checks(
            node_type, node.get("bulletOrder") or [], combiners
        )
        if registry.check_keys(node_type):
            for key in registry.normative_keys(node_type):
                for index in range(1, len(_values(node_bullets.get(key))) + 1):
                    if not checks_per_bullet.get((key, index)):
                        health.append(
                            {
                                "kind": "missing-declared-check",
                                "severity": "warning",
                                "node": node_id,
                                "key": key,
                                "message": (
                                    f"impacted contract's `{key}:` claim declares no "
                                    "`verify:` check to fulfil it"
                                ),
                            }
                        )
    demoted_symbols: frozenset[str] | set[str] = shared_symbols
    required_contracts = {
        node_id
        for node_id in contracts
        if _is_required(node_id, direct_reasons, grounded, shared_files, shared_symbols)
    }
    if not required_contracts:
        floored = {
            node_id
            for node_id in contracts
            if _is_required(node_id, direct_reasons, grounded, shared_files, frozenset())
        }
        if floored:
            required_contracts = floored
            demoted_symbols = frozenset()
            health.append(
                {
                    "kind": "shared-symbol-floor",
                    "severity": "warning",
                    "message": (
                        "every changed symbol is cited by enough nodes to be demoted, which"
                        " would leave this change owing no live evidence at all; the"
                        " demotion was dropped and the changed-code reasons kept"
                    ),
                }
            )
    reached_by_the_diff = set(required_contracts)
    required_subjects = {
        subject for node_id in required_contracts for subject in _named_subjects(nodes_by_id[node_id])
    }
    if required_subjects:
        hopped = False
        for node_id in sorted(contracts - required_contracts):
            for subject in sorted(_named_subjects(nodes_by_id[node_id]) & required_subjects):
                direct_reasons.setdefault(node_id, []).append(
                    {"kind": "relation-of-required", "ref": subject}
                )
                hopped = True
        if hopped:
            required_contracts = {
                node_id
                for node_id in contracts
                if _is_required(node_id, direct_reasons, grounded, shared_files, demoted_symbols)
            }
        for subject in sorted(required_subjects):
            owners = sorted(
                node_id for node_id, node in nodes_by_id.items() if subject in _named_subjects(node)
            )
            if len(owners) > _RELATION_FANOUT:
                health.append(
                    {
                        "kind": "relation-fanout",
                        "severity": "warning",
                        "ref": subject,
                        "message": (
                            f"relation subject `{subject}` binds {len(owners)} nodes; a change"
                            " reaching any of them owes live evidence for all of them, which"
                            " usually means the subject is named more broadly than the record"
                        ),
                    }
                )
    fixture_provides = _fixture_provides_index(nodes_by_id)
    fixture_undetermined = _fixture_undetermined_index(nodes_by_id)
    obligations = [
        obligation
        for node_id in sorted(contracts)
        for obligation in _obligations(
            nodes_by_id[node_id],
            direct_reasons.get(node_id, []),
            journey=False,
            required=node_id in required_contracts,
            owed_keys=None if node_id in reached_by_the_diff else _SHARED_INVARIANT_KEYS,
            scope=node_scopes.get(node_id, ()),
            judgment=judgment_by_node.get(node_id),
            fixture_provides=fixture_provides,
            fixture_undetermined=fixture_undetermined,
            resolve_locator=_locator_resolver(head_graph, nodes_by_id, nodes_by_id[node_id]),
            nodes_by_id=nodes_by_id,
        )
    ] + [
        obligation
        for node_id in sorted(journeys)
        for obligation in _obligations(
            nodes_by_id[node_id],
            direct_reasons.get(node_id, []),
            journey=True,
            required=_journey_is_required(
                node_id, direct_reasons, required_contracts, end_edges
            ),
            scope=node_scopes.get(node_id, ()),
            judgment=judgment_by_node.get(node_id),
            fixture_provides=fixture_provides,
            fixture_undetermined=fixture_undetermined,
            resolve_locator=_locator_resolver(head_graph, nodes_by_id, nodes_by_id[node_id]),
            nodes_by_id=nodes_by_id,
        )
    ]
    obligations.sort(key=lambda item: _sort_key(str(item["id"])))
    seen_obligation_ids: set[str] = set()
    deduped_obligations: list[dict[str, Any]] = []
    for obligation in obligations:
        obligation_id = str(obligation["id"])
        if obligation_id in seen_obligation_ids:
            continue
        seen_obligation_ids.add(obligation_id)
        deduped_obligations.append(obligation)
    obligations = deduped_obligations
    navigation = _navigation(head_graph)
    cli_binaries = _cli_binaries(nodes_by_id)
    return {
        "version": 2 if repositories else 1,
        "available": bool(nodes_by_id),
        "base": base,
        "head": head,
        "featuresRoot": features_root,
        "bookFiles": book_files_list,
        "storyFile": story_file_record_value,
        "changedCode": changed_code,
        **({"changedUnits": changed_code, "repositories": repository_rows} if repositories else {}),
        "directNodes": [
            {"node": node_id, "reasons": direct_reasons[node_id]}
            for node_id in sorted(direct_reasons)
        ],
        "contracts": sorted(contracts),
        "journeys": sorted(journeys),
        "journeyNodes": sorted(journeys),
        "verificationRefs": verification_refs,
        "verificationIndex": verification_index,
        "navigation": navigation,
        "cliBinaries": cli_binaries,
        "screenRoutes": routes_mod.screen_routes(head_graph),
        "healthFindings": health,
        "story": _story_identity(story_file),
        "acceptanceCriteria": _acceptance_criteria(story_file),
        "obligations": obligations,
    }


VERIFICATION_INDEX_FILE = "qa-okf-verification-index.json"


def write_context(packet: dict[str, Any], spec_dir: Path) -> tuple[Path, Path]:
    spec_dir.mkdir(parents=True, exist_ok=True)
    json_path = spec_dir / "qa-okf-context.json"
    md_path = spec_dir / "qa-okf-context.md"
    reader_packet = {key: value for key, value in packet.items() if key != "verificationIndex"}
    (spec_dir / VERIFICATION_INDEX_FILE).write_text(
        json.dumps(packet.get("verificationIndex", []), indent=2) + "\n", encoding="utf-8"
    )
    json_path.write_text(json.dumps(reader_packet, indent=2) + "\n", encoding="utf-8")
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
            repeat = obligation.get("repeat")
            if repeat:
                parts = [f"one per `{repeat['onePer']}`"]
                if repeat.get("binds"):
                    parts.append("binds " + ", ".join(f"`{b}`" for b in repeat["binds"]))
                if repeat.get("uniqueBy"):
                    parts.append(f"unique by `{repeat['uniqueBy']}`")
                if repeat.get("variants"):
                    variants = repeat["variants"]
                    parts.append(
                        f"variants `{variants['path']}` = " + " | ".join(variants["values"])
                    )
                lines.append(f"  - repeated: {'; '.join(parts)}")
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
        story_name = str(packet.get("story", "") or "story")
        annotate_deferred_obligations(packet, story=story_name)
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


def _graph_at_revision(root: Path, revision: str, features_root: str) -> Graph:
    """The base-side graph at `revision`, built from every `.md` file under `features_root`."""
    current = load(root)
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
    graph: Graph,
) -> tuple[
    dict[str, dict[str, Any]],
    set[tuple[str, str]],
    set[tuple[str, str]],
    dict[str, tuple[str, ...]],
    set[tuple[str, str]],
]:
    """The nodes, every resolved edge, the flow destinations, each node's repeat scope, and the `detail:` edges."""
    data = graph_mod.build(graph)
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
    return nodes, edges, ends, locators_mod.scopes(data), details


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
    if not path or path == "/dev/null":
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
    if not path or path == "/dev/null":
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


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


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


def _cli_binaries(nodes_by_id: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Every `cli` file node's declared `binary:`, keyed by the file `path` its `command` sections share."""
    binaries: dict[str, str] = {}
    for node in nodes_by_id.values():
        if node.get("type") != "cli" or node.get("kind") != "file":
            continue
        values = _values(node.get("bullets", {}).get("binary"))
        if values and values[0].strip():
            binaries[str(node["path"])] = values[0].strip()
    return binaries


def _named_subjects(node: dict[str, Any]) -> set[str]:
    """Every subject this node names, pooled across the relation and event bullets."""
    bullets = node.get("bullets", {})
    subjects = {
        subject
        for key in RELATION_KEYS
        for value in _values(bullets.get(key))
        if (subject := relation_subject(value)[0]) is not None
    }
    for key in _EVENT_KEYS:
        for value in _values(bullets.get(key)):
            subject, _ = relation_subject(value)
            subjects.add(subject if subject is not None else value.strip())
    return {subject for subject in subjects if subject}


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


def _verification_refs(node: dict[str, Any]) -> list[str]:
    """Every test a node's ``tests:`` bullets cite, as ``path`` or ``path::name``."""
    refs: list[str] = []
    for value in _values(node.get("bullets", {}).get("tests")):
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


def _surface_owner(path: str, roots: dict[str, list[str]]) -> str:
    matches = [
        (len(prefix.rstrip("/")), surface)
        for surface, prefixes in roots.items()
        for prefix in prefixes
        if prefix.rstrip("/") in ("", ".")
        or path == prefix.rstrip("/")
        or path.startswith(prefix.rstrip("/") + "/")
    ]
    return max(matches)[1] if matches else ""


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
    direct_reasons: dict[str, list[dict[str, str]]],
    grounded: set[str],
    shared_files: frozenset[str] | set[str] = frozenset(),
    shared_symbols: frozenset[str] | set[str] = frozenset(),
) -> bool:
    """Whether this node's obligations are owed live evidence, or are only context."""
    kinds = {
        reason.get("kind", "")
        for reason in direct_reasons.get(node_id, [])
        if not (reason.get("kind") == "file-owner" and reason.get("ref") in shared_files)
        and not (reason.get("kind") == "changed-code" and reason.get("ref") in shared_symbols)
    }
    return node_id in grounded and bool(kinds - _CONTEXT_ONLY_REASON_KINDS)


def _journey_is_required(
    node_id: str,
    direct_reasons: dict[str, list[dict[str, str]]],
    required_contracts: set[str],
    end_edges: set[tuple[str, str]],
) -> bool:
    """Whether this flow is owed live evidence, or is only context."""
    reasons = [
        reason
        for reason in direct_reasons.get(node_id, [])
        if reason.get("kind") == "flow-links-contract"
        and _reaches_a_required_contract(str(reason.get("ref") or ""), required_contracts)
    ]
    reaches_the_end = any((node_id, reason.get("ref")) in end_edges for reason in reasons)
    walks_the_route = any((node_id, reason.get("ref")) not in end_edges for reason in reasons)
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
    graph: Graph, nodes_by_id: dict[str, dict[str, Any]], node: dict[str, Any]
) -> Callable[[str], LocatorTarget]:
    """Resolve this node's check locators against the book, the way `doctor` resolves them."""
    origin = graph.root / str(node.get("path", ""))

    def resolve(value: str) -> LocatorTarget:
        located = locators_mod.located_node(graph, value, origin)
        if located is None:
            return {"node": "", "locators": {}}
        serialized = nodes_by_id.get(located.id)
        return {
            "node": located.id,
            "locators": _locators(serialized) if serialized is not None else {},
        }

    return resolve


def _dedup_checks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list({row["call"]: row for row in rows}.values())


def _fixture_provides_index(nodes_by_id: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """Every book fixture's own `provides:` keys, plus every one reachable through `needs:`."""
    resolved = _fixture_provides_closure(nodes_by_id)
    return {name: sorted(ref for ref, _ in pairs) for name, pairs in resolved.items()}


def _fixture_undetermined_index(nodes_by_id: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """Every reachable `provides:` key whose *source* the book left undetermined, by fixture stem."""
    resolved = _fixture_provides_closure(nodes_by_id)
    return {name: sorted(ref for ref, bad in pairs if bad) for name, pairs in resolved.items()}


def _fixture_provides_closure(
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, set[tuple[str, bool]]]:
    """`{fixture stem: {(`<owner>.<key>`, source-undetermined), ...}}` over the `needs:` closure."""
    fixtures = {node_id: node for node_id, node in nodes_by_id.items() if node.get("type") == "fixture"}
    provides: dict[str, set[tuple[str, bool]]] = {}
    needs: dict[str, set[str]] = {}
    for node_id, node in fixtures.items():
        keys: set[tuple[str, bool]] = set()
        entries = node.get("entries", {}).get("provides") or []
        stated = {}
        for entry in entries:
            head = str(entry.get("headline", "")).partition("—")[0].split()
            if head:
                stated[head[0]] = entry.get("properties") or {}
        for value in _values(node.get("bullets", {}).get("provides")):
            head = value.partition("—")[0].split()
            if not head:
                continue
            properties = stated.get(head[0], {})
            observed = bool(_property_text(properties.get("from")))
            asserted = bool(_property_text(properties.get("is")))
            keys.add((head[0], observed == asserted))
        provides[node_id] = keys
        needs[node_id] = {
            edge["to"] for edge in node.get("edges", [])
            if edge.get("via") == "needs" and edge.get("to") in fixtures
        }

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


def _property_text(value: object) -> str:
    """One serialized entry property as its text — the JSON-side twin of `Entry.property_text`."""
    if isinstance(value, list):
        return " ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip() if value is not None else ""


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


def _locators(node: dict[str, Any]) -> dict[str, list[str]]:
    declared = registry.declared_keys(node.get("type", ""))
    bullets = node.get("bullets", {})
    return {
        _LOCATOR_KEY_RENAME.get(key, key): _values(bullets.get(key))
        for key in _LOCATOR_KEYS
        if key in declared and _values(bullets.get(key))
    }


def _extends_target(
    node: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any] | None, bool]:
    """The base node an `extends:` arm inherits its control identity from (D51)."""
    to_ids = [
        edge.get("to")
        for edge in node.get("edges") or []
        if edge.get("via") == "extends" and edge.get("to")
    ]
    if not to_ids:
        return None, False
    target = nodes_by_id.get(str(to_ids[0]))
    if target is None or target.get("type") != node.get("type"):
        return None, True
    return target, False


def _same_as_targets(
    node: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """The nodes *node*'s `same-as:` bullet resolves to, in document order."""
    return [
        target
        for edge in node.get("edges") or []
        if edge.get("via") == "same-as" and edge.get("to")
        for target in [nodes_by_id.get(str(edge["to"]))]
        if target is not None
    ]


def _same_as_component(node_id: str, nodes_by_id: dict[str, dict[str, Any]]) -> frozenset[str]:
    """Every node id reachable from *node_id* by following declared `same-as:` edges, *node_id* included."""
    seen = {node_id}
    frontier = [node_id]
    while frontier:
        current = frontier.pop()
        node = nodes_by_id.get(current)
        if node is None:
            continue
        for target in _same_as_targets(node, nodes_by_id):
            target_id = str(target["id"])
            if target_id not in seen:
                seen.add(target_id)
                frontier.append(target_id)
    return frozenset(seen)


def _document_of(node_id: str) -> str:
    """The document part of a node id — everything ahead of its first `#`."""
    return node_id.split("#", 1)[0]


def _linked_surface(
    node: dict[str, Any], value: Any, nodes_by_id: dict[str, dict[str, Any]]
) -> str:
    """The surface of the node *value*'s own links point at — "" when they point at none."""
    hrefs = {
        href
        for item in _values(value)
        for _text, href in markdown.extract_refs(item).links
    }
    if not hrefs:
        return ""
    for edge in node.get("edges") or []:
        target_id = edge.get("to")
        if not target_id or edge.get("href") not in hrefs:
            continue
        target = nodes_by_id.get(str(target_id))
        if target and target.get("surface"):
            return str(target["surface"])
    return ""


def _journey_steps(
    node: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    """The nodes a flow's `steps:` names, in the order the book wrote them."""
    resolved = {
        str(edge["href"]): str(edge["to"])
        for edge in node.get("edges") or []
        if edge.get("to") and edge.get("href")
    }
    walk: list[dict[str, str]] = []
    for item in _values(node.get("bullets", {}).get("steps")):
        for _text, href in markdown.extract_refs(item).links:
            target_id = resolved.get(href, "")
            target = nodes_by_id.get(target_id, {}) if target_id else {}
            walk.append({
                "ref": target_id,
                "href": href,
                "nodeType": str(target.get("type") or ""),
                "surface": str(target.get("surface") or ""),
            })
    return walk


def _family_root(node_id: str, owners: set[str], nodes_by_id: dict[str, dict[str, Any]]) -> str:
    """The declared-family root *node_id* belongs to among *owners*, for `_CONTAINER_FANOUT`."""
    seen: set[str] = set()
    current = node_id
    while current not in seen:
        seen.add(current)
        same_as_root = min(_same_as_component(current, nodes_by_id))
        if same_as_root != current:
            current = same_as_root
            continue
        node = nodes_by_id.get(current)
        if node is not None:
            target, _malformed = _extends_target(node, nodes_by_id)
            if target is not None:
                current = str(target["id"])
                continue
        file_id, sep, _anchor = current.partition("#")
        if sep and file_id in owners:
            current = file_id
            continue
        break
    return current


def _repeat(node: dict[str, Any], scope: tuple[str, ...]) -> dict[str, Any] | None:
    """The compiled repeat contract for a node in a `one-per:` scope, or None."""
    own = locators_mod.repeat_of(node)
    scope = scope or ((own,) if own else ())
    if not scope:
        return None
    repeat: dict[str, Any] = {"onePer": scope[-1], "binds": []}
    located = locators_mod.locator_for(node, scope=scope)
    if located["strategy"] == "template":
        repeat.update(
            {
                "template": located["template"],
                "iterates": located["iterates"],
                "segments": located["segments"],
                "binds": located["binds"],
            }
        )
    unique = locators_mod.unique_by_of(node)
    if unique:
        repeat["uniqueBy"] = unique
    variants = locators_mod.variants_of(node)
    if variants:
        repeat["variants"] = variants
    return repeat


def _obligations(
    node: dict[str, Any],
    reasons: list[dict[str, str]],
    *,
    journey: bool,
    required: bool = True,
    owed_keys: frozenset[str] | None = None,
    scope: tuple[str, ...] = (),
    judgment: list[dict[str, Any]] | None = None,
    fixture_provides: dict[str, list[str]] | None = None,
    fixture_undetermined: dict[str, list[str]] | None = None,
    resolve_locator: Callable[[str], LocatorTarget] | None = None,
    nodes_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Mint one obligation per normative bullet, plus the node-level contract."""
    family = (
        _same_as_component(str(node["id"]), nodes_by_id)
        if nodes_by_id is not None
        else frozenset({str(node["id"])})
    )
    representative = min(family)
    occurrence_documents = sorted({_document_of(member) for member in family})
    suffix = "end-state" if journey else "contract"
    base = {
        "id": f"okf:{representative}:{suffix}",
        "kind": "journey" if journey else "contract",
        "node": node["id"],
        "occurrenceDocuments": occurrence_documents,
        "nodeType": node.get("type", ""),
        "source": node["path"],
        "surface": node.get("surface") or "",
        "requirement": node.get("title") or node["id"],
        "required": required,
        "evidenceRequired": "live" if required else "context",
        "reasons": reasons or [{"kind": "graph-closure", "ref": node["id"]}],
    }
    if nodes_by_id is not None and node.get("type") == "flow":
        end_surface = _linked_surface(node, node.get("bullets", {}).get("end"), nodes_by_id)
        if end_surface:
            base["surface"] = end_surface
        walk = _journey_steps(node, nodes_by_id)
        if walk:
            base["steps"] = walk
    locators = _locators(node)
    if nodes_by_id is not None and node.get("type") in ("interaction", "invocation"):
        extends_target, extends_malformed = _extends_target(node, nodes_by_id)
        if extends_target is not None:
            locators = {**_locators(extends_target), **locators}
        elif extends_malformed:
            base["extendsUnresolved"] = True
    if locators:
        base["locators"] = locators
    repeat = _repeat(node, scope)
    if repeat:
        base["repeat"] = repeat
    combiners = {int(pos): str(word) for pos, word in (node.get("combiners") or {}).items()}
    contract, per_bullet = registry.attributed_checks(
        str(node.get("type", "")), node.get("bulletOrder") or [], combiners
    )
    undetermined = {
        claim
        for group in registry.undetermined_claims(
            str(node.get("type", "")), node.get("bulletOrder") or [], combiners).values()
        for claim in group
    }
    contract_rows = _dedup_checks(_parse_checks(contract, resolve_locator))
    if contract_rows:
        base["checksDeclared"] = contract_rows
    contract_unparsed = _unparsed_checks(contract)
    if contract_unparsed:
        base["checksUnparsed"] = contract_unparsed
    node_fixtures, fixtures_per_bullet = registry.attributed_fixtures(
        str(node.get("type", "")), node.get("bulletOrder") or [], combiners
    )
    ambient = _parse_fixtures(node_fixtures, fixture_provides, fixture_undetermined)
    if ambient:
        base["fixturesDeclared"] = ambient
    ambient_unparsed = _unparsed_fixtures(node_fixtures)
    if ambient_unparsed:
        base["fixturesUnparsed"] = ambient_unparsed
    ambient_nothing = _no_arrangement_stated(node_fixtures)
    if ambient_nothing:
        base["arrangesNothing"] = True
    node_acts, acts_per_bullet = registry.attributed_acts(
        str(node.get("type", "")), node.get("bulletOrder") or [], combiners
    )
    ambient_acts = _parse_acts(node_acts, resolve_locator)
    if ambient_acts:
        base["actsDeclared"] = ambient_acts
    ambient_acts_unparsed = _unparsed_acts(node_acts)
    if ambient_acts_unparsed:
        base["actsUnparsed"] = ambient_acts_unparsed
    captures_contract, captures_per_bullet = registry.attributed_captures(
        str(node.get("type", "")), node.get("bulletOrder") or [], combiners
    )
    contract_captures_unparsed = _unparsed_captures(captures_contract)
    if contract_captures_unparsed:
        base["capturesUnparsed"] = contract_captures_unparsed
    node_line = int(node.get("line") or 0)
    doc_position: dict[tuple[str, int], int] = {}
    _seen = {key: 0 for key in registry.normative_keys(str(node.get("type", "")))}
    for row in node.get("bulletOrder") or []:
        row_key = str(row[0])
        if row_key in _seen:
            _seen[row_key] += 1
            doc_position[(row_key, _seen[row_key])] = int(row[2])
    base["docPosition"] = [node_line, -1]
    output = [base]
    for key in registry.normative_keys(str(node.get("type", ""))):
        for index, requirement in enumerate(_values(node.get("bullets", {}).get(key)), start=1):
            obligation = {
                **base,
                "id": f"okf:{representative}:{key.replace(' ', '-')}:{index}",
                "kind": key.replace(" ", "-"),
                "requirement": requirement,
                "docPosition": [node_line, doc_position.get((key, index), 0)],
            }
            if key in RELATION_KEYS or key in _EVENT_KEYS:
                subject, prose = relation_subject(requirement)
                obligation["requirement"] = prose
                if subject is not None:
                    obligation["subject"] = subject
            if nodes_by_id is not None and node.get("type") == "flow":
                linked = _linked_surface(node, requirement, nodes_by_id)
                if linked:
                    obligation["surface"] = linked
            if (key, index) in undetermined:
                obligation["claimCombiner"] = "unstated"
            if required and owed_keys is not None and key not in owed_keys:
                obligation["required"] = False
                obligation["evidenceRequired"] = "context"
            rows = _dedup_checks(
                _parse_checks(per_bullet.get((key, index), []), resolve_locator))
            if rows:
                obligation["checksDeclared"] = rows
            else:
                obligation.pop("checksDeclared", None)
            refused = _unparsed_checks(per_bullet.get((key, index), []))
            if refused:
                obligation["checksUnparsed"] = refused
            else:
                obligation.pop("checksUnparsed", None)
            arranged = _parse_fixtures(
                fixtures_per_bullet.get((key, index), []), fixture_provides, fixture_undetermined)
            combined = list({(row["name"], tuple(row["args"])): row
                             for row in [*ambient, *arranged]}.values())
            if combined:
                obligation["fixturesDeclared"] = combined
            else:
                obligation.pop("fixturesDeclared", None)
            unparsed = list({row["value"]: row for row in [
                *ambient_unparsed,
                *_unparsed_fixtures(fixtures_per_bullet.get((key, index), [])),
            ]}.values())
            if unparsed:
                obligation["fixturesUnparsed"] = unparsed
            else:
                obligation.pop("fixturesUnparsed", None)
            if ambient_nothing or _no_arrangement_stated(
                fixtures_per_bullet.get((key, index), [])
            ):
                obligation["arrangesNothing"] = True
            else:
                obligation.pop("arrangesNothing", None)
            performed = list({row["call"]: row for row in [
                *ambient_acts,
                *_parse_acts(acts_per_bullet.get((key, index), []), resolve_locator),
            ]}.values())
            if performed:
                obligation["actsDeclared"] = performed
            else:
                obligation.pop("actsDeclared", None)
            refused_acts = list({row["value"]: row for row in [
                *ambient_acts_unparsed,
                *_unparsed_acts(acts_per_bullet.get((key, index), [])),
            ]}.values())
            if refused_acts:
                obligation["actsUnparsed"] = refused_acts
            else:
                obligation.pop("actsUnparsed", None)
            captures = _parse_captures(captures_per_bullet.get((key, index), []))
            if captures:
                obligation["capturesDeclared"] = captures
            else:
                obligation.pop("capturesDeclared", None)
            refused_captures = _unparsed_captures(captures_per_bullet.get((key, index), []))
            if refused_captures:
                obligation["capturesUnparsed"] = refused_captures
            else:
                obligation.pop("capturesUnparsed", None)
            output.append(obligation)
    if judgment:
        base["judgment"] = judgment
    unspecified = [
        {
            "text": value,
            "citation": next((href for _t, href in markdown.extract_refs(value).links), ""),
        }
        for value in _values(node.get("bullets", {}).get("unspecified"))
    ]
    if unspecified:
        base["unspecified"] = unspecified
    return output


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
