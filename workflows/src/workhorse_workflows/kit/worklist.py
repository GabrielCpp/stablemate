"""The worklist builder — one composable answer to "what does the book owe the code?"."""
from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ostler import Ostler, backfill as backfill_mod
from ostler import coverage as coverage_mod
from ostler import doctor as doctor_mod
from ostler import graph as graph_mod
from ostler import refs as refs_mod


WorklistRow = dict


@dataclass(frozen=True)
class BuildWorklist:
    """The deterministic rows a build queues, plus what the recheck agent adjudicates."""

    rows: tuple[WorklistRow, ...]
    missing: tuple[dict, ...]
    coverage_complete: bool


def _path_set(paths: Sequence[str] | None) -> set[str] | None:
    """Normalize a path filter to a set of repo-relative paths, or ``None`` for whole tree."""
    if paths is None:
        return None
    return {path.strip().rstrip("/") for path in paths if path and path.strip()}


def _stale_unit_to_row(unit: backfill_mod.StaleUnit) -> WorklistRow | None:
    """Translate a ``backfill.plan`` row to a worklist row, or ``None`` to skip."""
    if unit.reason == "uncovered":
        return None
    if not unit.nodes:
        return None
    kind = f"fix:{unit.reason}"
    target = unit.nodes[0]
    context = {
        "code": kind.removeprefix("fix:"),
        "citation": unit.unit,
        "evidence": unit.evidence,
        "nodes": list(unit.nodes),
        "grounded": True,
    }
    if unit.relocated_to:
        context["relocated_to"] = unit.relocated_to
    return {
        "kind": kind,
        "target": target,
        "context": json.dumps(context, sort_keys=True),
        "requeue": True,
    }


def _deleted_paths(repo_root: Path, service: str | None) -> list[str]:
    """Every own-repository path the book cites that the tree no longer carries."""
    try:
        okf = Ostler(repo_root)
        cited = coverage_mod.citations(okf.graph, surface=service)
    except (OSError, ValueError, RuntimeError):
        return []
    deleted: set[str] = set()
    for ref in cited:
        try:
            parsed = refs_mod.parse_code_ref(ref)
        except ValueError:
            continue
        if parsed.repository:
            continue
        if not (repo_root / parsed.path).is_file():
            deleted.add(parsed.path)
    return sorted(deleted)


def _trim_rows(repo_root: Path, service: str | None,
               deleted: Iterable[str], relocated: frozenset[str] = frozenset()) -> list[WorklistRow]:
    """``trim-bullet`` rows for every node citing a path the tree no longer carries."""
    deleted_set = set(deleted)
    if not deleted_set:
        return []
    try:
        okf = Ostler(repo_root)
        cited_by = coverage_mod.citations(okf.graph, surface=service)
    except (OSError, ValueError, RuntimeError):
        return []
    relocated_undigested = {refs_mod.strip_digest(ref) for ref in relocated}
    rows: list[WorklistRow] = []
    for ref, nodes in cited_by.items():
        if ref in relocated_undigested:
            continue
        try:
            parsed = refs_mod.parse_code_ref(ref)
        except ValueError:
            continue
        if parsed.repository or parsed.path not in deleted_set:
            continue
        for node in nodes:
            rows.append({
                "kind": "trim-bullet",
                "target": node,
                "context": json.dumps({
                    "code": "trim-bullet",
                    "citation": ref,
                    "missing_path": parsed.path,
                    "grounded": True,
                }, sort_keys=True),
                "requeue": True,
            })
    return rows


def _trim_neighbour_rows(repo_root: Path, service: str | None,
                         deleted: Iterable[str],
                         relocated: frozenset[str] = frozenset()) -> list[WorklistRow]:
    """``trim-review`` rows for every node that linked to something trimmed."""
    deleted_set = set(deleted)
    if not deleted_set:
        return []
    try:
        okf = Ostler(repo_root)
        data = graph_mod.build(okf.graph, surface=service)
    except (OSError, ValueError, RuntimeError):
        return []
    incoming: dict[str, list[str]] = {}
    for edge in data["edges"]:
        if edge.get("to"):
            incoming.setdefault(edge["to"], []).append(edge["from"])
    rows: list[WorklistRow] = []
    for node in data["nodes"]:
        cited = node.get("bullets", {}).get("code", []) or []
        if not isinstance(cited, list):
            cited = [cited]
        trimmed = [ref for ref in cited
                  if _ref_path(ref) in deleted_set and ref not in relocated]
        if not trimmed:
            continue
        for caller in incoming.get(node["id"], ()):
            rows.append({
                "kind": "trim-review",
                "target": caller,
                "context": json.dumps({
                    "code": "trim-review",
                    "trimmed_node": node["id"],
                    "trimmed_citations": [str(ref) for ref in trimmed],
                }, sort_keys=True),
                "requeue": True,
            })
    return rows


def _ref_path(ref: str) -> str:
    """The repo-relative path part of a ``code:`` ref, or ``""`` if it doesn't parse."""
    try:
        return refs_mod.parse_code_ref(ref).path
    except ValueError:
        return ""


def _orphan_rows(repo_root: Path, service: str | None) -> list[WorklistRow]:
    """``unreachable`` rows for every page nothing in the book reaches."""
    try:
        okf = Ostler(repo_root)
        data = graph_mod.build(okf.graph, surface=service)
        orphans = graph_mod.select(data, orphans=True)
    except (OSError, ValueError, RuntimeError):
        return []
    return [
        {
            "kind": "unreachable",
            "target": node["id"],
            "context": json.dumps({
                "code": "unreachable",
                "title": node.get("title", ""),
                "type": node.get("type", ""),
            }, sort_keys=True),
            "requeue": True,
        }
        for node in orphans
    ]


def build_worklist(
    repo_root: Path,
    features_root: Path,
    service: str,
    *,
    paths: Sequence[str] | None = None,
) -> BuildWorklist:
    """The deterministic worklist rows for a run, plus what the recheck agent adjudicates."""
    root = Path(repo_root)
    features = Path(features_root)
    surface = service or None
    path_filter = _path_set(paths)
    scope: tuple = tuple(sorted(path_filter)) if path_filter else ()

    try:
        okf = Ostler(root)
        graph = okf.graph
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"could not load the OKF graph at {root}: {exc}") from exc

    from workhorse_workflows.okf_builder.shared.paths import (
        worklist_path as _worklist_path, source_inventory_path as _inv_path,
    )
    worklist_relative = _inv_path(_worklist_path(root, service))
    features_relative = features / ".source-inventory.json"
    candidates = [worklist_relative, features_relative]
    for candidate in candidates:
        if candidate.is_file():
            inventory_path = candidate
            break
    else:
        raise RuntimeError(
            f"could not load the source inventory — none of {candidates} exists"
        )
    try:
        inventory = coverage_mod.load_inventory(inventory_path)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"could not load the source inventory at {inventory_path}: {exc}") from exc

    waivers = coverage_mod.load_waivers(str(features / "coverage-waivers.json"))

    try:
        plan = backfill_mod.plan(
            graph, inventory,
            surface=surface, waivers=waivers,
            findings=doctor_mod.run(graph, check_schema=False).findings,
            scope=scope,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"backfill plan failed: {exc}") from exc

    deleted = _deleted_paths(root, surface)
    if path_filter:
        deleted = [path for path in deleted if path in path_filter]
    deleted_set = set(deleted)
    relocated_refs = frozenset(
        unit.unit for unit in plan.units
        if unit.reason == "dangling" and unit.relocated_to
    )

    rows: list[WorklistRow] = []
    for unit in plan.units:
        if path_filter and unit.path not in path_filter:
            continue
        if unit.reason == "dangling" and unit.path in deleted_set and not unit.relocated_to:
            continue
        row = _stale_unit_to_row(unit)
        if row is not None:
            rows.append(row)

    rows.extend(_trim_rows(root, surface, deleted, relocated_refs))
    rows.extend(_trim_neighbour_rows(root, surface, deleted, relocated_refs))

    if path_filter is None:
        rows.extend(_orphan_rows(root, surface))

    coverage_result = coverage_mod.run(
        graph, surface=surface, inventory=inventory_path,
        waivers=str(features / "coverage-waivers.json"),
    )
    if path_filter is not None:
        coverage_result["missing"] = [
            miss for miss in coverage_result.get("missing", [])
            if miss.get("path") in path_filter
        ]

    coverage_complete = (
        coverage_mod.is_complete(coverage_result) and not deleted
    )

    return BuildWorklist(
        rows=tuple(rows),
        missing=tuple(coverage_result.get("missing", [])),
        coverage_complete=bool(coverage_complete),
    )


__all__ = ["BuildWorklist", "WorklistRow", "build_worklist"]