"""The worklist builder — one composable answer to "what does the book owe the code?".

Two callers need this answer. ``okf-builder`` runs it against the whole tree at HEAD,
filling a book nobody has written or reconciling one to the current bytes. The coder
docs lane runs it against the *story's* changed paths, restricting the same answer to
what the story actually wrote. Both call into the same function — the only difference
is the path filter — because ``backfill.plan`` and ``coverage.compute`` are already
the right joins, and a second implementation of "what does this book owe" is the
drift the one stale set exists to stop.

**Ostler is imported as a library, not shelled.** ``requires: dist:`` already makes
ostler import before node one, and the CLI-presence fallbacks were deliberately
deleted (``ostler-import-is-a-run-precondition``) — shelling out would reintroduce
exactly the seam that was closed.

**The set is four joins, in drain order.**

* ``dangling`` — doctor codes ``dangling-code-ref``, ``dangling-repository-ref``,
  ``missing-code-symbol``. The checkpoint's channel, here surfaced as ``fix:`` rows.
* ``moved`` — a cited symbol is gone from the path the citation names and present
  *unchanged* elsewhere. Re-grounding work, not re-documenting work.
* ``drifted`` — a cited symbol's bytes disagree with the catalog. Re-grounding work
  the agent reads against the source, distinct from a missing symbol.
* ``uncovered`` — units in the inventory nothing cites. The builder surfaces the
  list; the recheck agent adjudicates which are real work, which are helpers, and
  which are deliberate non-units.

A *trim* joins them: a path the catalog carries that the tree no longer does. Its
citations are dangling in a different way (the file is gone), so the bullets are
cut, the node is queued for authored removal if it lost its last bullet, and the
neighbours are queued for review so a journey whose third step vanished is read
against the book rather than against the file.

A *1-hop* join widens "what changed" past the digest: when file B changes, every
file that imports B is treated as changed too, so its cited units are re-grounded
rather than silently skipped. Unbounded propagation is not an option — any edit to
a core utility would reach the whole repository and the digest skip would stop
skipping anything. One hop is defensible because a documented claim about a
function usually describes that function's own behaviour; deeper drift is residual
risk carried by the book's link structure.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ostler import Ostler, backfill as backfill_mod
from ostler import coverage as coverage_mod
from ostler import doctor as doctor_mod
from ostler import graph as graph_mod
from ostler import inventory as inventory_mod
from ostler import refs as refs_mod
from ostler import source_snapshots


#: A builder row, the same shape the worklist mutator merges in. ``kind`` decides which
#: prompt or repair handler the drain dispatches to; ``target`` is the node id or unit
#: ref the row names; ``context`` is the JSON-encoded prompt payload.
WorklistRow = dict


@dataclass(frozen=True)
class BuildWorklist:
    """The deterministic rows a build queues, plus what the recheck agent adjudicates.

    The drain consumes ``rows`` directly. ``missing`` is the coverage join's whole
    ``missing`` list — the recheck agent decides which are real work, which are
    helpers folded into a documented contract, and which are deliberate non-units.
    Surfaced separately because the agent's read is judgement the builder must
    not make on its own.
    """

    rows: tuple[WorklistRow, ...]
    missing: tuple[dict, ...]
    coverage_complete: bool


def _path_set(paths: Sequence[str] | None) -> set[str] | None:
    """Normalize a path filter to a set of repo-relative paths, or ``None`` for whole tree.

    ``None`` means "no filter" — the run is over the whole tree. An empty list means
    "filter to nothing" — a filter that nothing matches produces an empty worklist, and
    that is the correct answer for a story that touched no source files. The two are
    not the same shape, and conflating them is how a scoped build silently widened.
    """
    if paths is None:
        return None
    return {path.strip().rstrip("/") for path in paths if path and path.strip()}


def _stale_unit_to_row(unit: backfill_mod.StaleUnit) -> WorklistRow | None:
    """Translate a ``backfill.plan`` row to a worklist row, or ``None`` to skip.

    A ``moved``/``drifted`` row carries a node list — every node that cited the unit —
    so a single stale citation fans out into one row per citing node. The first citing
    node is the worklist ``target``; the rest ride in ``context.nodes`` so the turn can
    see them without rereading the join.

    ``uncovered`` is **not** translated here: it has no node yet, and the recheck
    agent decides which are real work. Returning ``None`` keeps the join's verdict
    while the builder leaves judgement alone.
    """
    if unit.reason == "uncovered":
        return None
    if not unit.nodes:
        return None
    if unit.reason in {"moved", "drifted"}:
        kind = "fix:stale-citation"
    else:
        kind = f"fix:{unit.reason}"
    target = unit.nodes[0]
    return {
        "kind": kind,
        "target": target,
        "context": json.dumps({
            "code": kind.removeprefix("fix:"),
            "citation": unit.unit,
            "target": unit.target,
            "evidence": unit.evidence,
            "nodes": list(unit.nodes),
            "grounded": True,
        }, sort_keys=True),
        "requeue": True,
    }


def _deleted_paths(repo_root: Path,
                   catalog: source_snapshots.SourceCatalog | None) -> list[str]:
    """Every repo-relative path the catalog carries but the tree no longer does.

    Compared via ``is_file()`` per path; an unreadable working tree produces an empty
    list, which is the right answer for a corrupted checkout — the build will still
    proceed against the units it can read, and doctor reports what it cannot.
    """
    if catalog is None:
        return []
    own = catalog.repository(source_snapshots.SELF_REPOSITORY)
    if own is None:
        return []
    return [file.path for file in own.files
            if not (repo_root / file.path).is_file()]


def _trim_rows(repo_root: Path, service: str | None,
               deleted: Iterable[str]) -> list[WorklistRow]:
    """``trim-bullet`` rows for every node citing a path the tree no longer carries.

    A path the catalog knows but the tree lacks leaves its bullets pointing at nothing
    in a way doctor misses — doctor reads the *current* tree and finds no symbol to
    ground against. The builder closes that gap: every node citing a deleted path
    gets a row that retires the bullets and queues authored removal if the node lost
    its last bullet.
    """
    deleted_set = set(deleted)
    if not deleted_set:
        return []
    try:
        okf = Ostler(repo_root)
        cited_by = coverage_mod.citations(okf.graph, surface=service)
    except (OSError, ValueError, RuntimeError):
        return []
    rows: list[WorklistRow] = []
    for ref, nodes in cited_by.items():
        try:
            parsed = refs_mod.parse_code_ref(ref)
        except ValueError:
            continue
        if parsed.path not in deleted_set:
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
                         deleted: Iterable[str]) -> list[WorklistRow]:
    """``trim-review`` rows for every node that linked to something trimmed.

    A journey whose third step vanished is structurally valid and reads as a corpse
    until somebody re-reads the steps against the book. The detection is one pass
    over the graph: every incoming edge to a node whose citations now dangle.
    Without this, an authored removal lands and its caller still lists a step that
    does not exist.
    """
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
        if not any(_ref_path(ref) in deleted_set for ref in cited):
            continue
        for caller in incoming.get(node["id"], ()):
            rows.append({
                "kind": "trim-review",
                "target": caller,
                "context": json.dumps({
                    "code": "trim-review",
                    "trimmed_node": node["id"],
                    "trimmed_citations": [str(ref) for ref in cited
                                          if _ref_path(ref) in deleted_set],
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
    """``unreachable`` rows for every node nothing in the book links to.

    The concept nobody ever linked to and the flow whose only incoming edge was
    the page that just got trimmed both read as orphans under ``graph --orphans``,
    and both queue the same authored-removal row. The check is the one the OKF
    graph already computes — its ``select(orphans=True)`` reads incoming edges
    and yields every node with none.
    """
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


def _one_hop_changes(root: Path, changed: Iterable[str],
                     catalog: source_snapshots.SourceCatalog | None) -> set[str]:
    """The changed set widened by one hop through the import graph.

    For every path in *changed*, every file in the tree that imports it becomes
    "1-hop changed" — its cited units are queued for re-grounding rather than
    silently skipped, because the documented contract may now be a lie even though
    the bytes are unchanged. Carried in the same set the digest skip returns.

    The bound is one hop. Unbounded propagation through the import graph would reach
    the entire repository for any edit to a core utility, which is the three-day
    recompute this design exists to avoid.
    """
    initial = set(changed)
    if not initial:
        return initial
    candidates = _catalog_files(root, catalog)
    index = _import_index(root, candidates)
    widened = set(initial)
    frontier = set(initial)
    while frontier:
        next_frontier: set = set()
        for path in frontier:
            for importer in index.get(path, ()):
                if importer not in widened:
                    next_frontier.add(importer)
        widened.update(next_frontier)
        frontier = next_frontier
    return widened


def _catalog_files(root: Path, catalog: source_snapshots.SourceCatalog | None
                   ) -> Iterable[str]:
    """Every file the catalog carries, or every tracked source file as a fallback."""
    if catalog is not None:
        own = catalog.repository(source_snapshots.SELF_REPOSITORY)
        if own is not None:
            return [file.path for file in own.files]
    if not root.is_dir():
        return []
    return [path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.suffix in inventory_mod.SOURCE_SUFFIXES]


def _import_index(root: Path, files: Iterable[str]) -> dict[str, set[str]]:
    """Reverse map: for every repo-relative path, the paths whose imports name it.

    Built by parsing every file in *files* that has a grammar the front end reads,
    extracting its imports (Python, Go, TypeScript), and resolving each specifier
    against the tree. The resolution is a small language-shaped heuristic — enough
    to bound the one-hop walk, no more.
    """
    index: dict[str, set[str]] = {}
    for path in sorted(set(files)):
        target = root / path
        if not target.is_file():
            continue
        try:
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        specifiers = inventory_mod.imports_of(path, text)
        for imported in _resolve_specifiers(root, path, specifiers):
            index.setdefault(imported, set()).add(path)
    return index


def _resolve_specifiers(root: Path, importing_path: str,
                        specifiers: Iterable[str]) -> list[str]:
    """A specifier → one or more repo-relative paths the specifier could mean here.

    The resolution is the worklist builder's responsibility: ``inventory.imports_of``
    returns specifiers as written (dotted Python, relative Go, ``./``-prefixed
    TypeScript), and a tree may carry both ``foo/bar.py`` and ``foo/bar/__init__.py``
    for the same Python module. The walk picks every plausible match and lets the
    digest skip finish the disambiguation at the unit level.

    Third-party specifiers (``@scope/pkg``, ``github.com/...``, Python stdlib names)
    yield no matches — they live outside the tree, and one-hop propagation through
    them would reach every file the workspace imports, which is the unbounded
    case the design is trying to avoid.
    """
    matches: set[str] = set()
    for spec in specifiers:
        for resolved in _candidates_for(root, importing_path, spec):
            matches.add(resolved)
    return sorted(matches)


def _candidates_for(root: Path, importing_path: str, spec: str) -> list[str]:
    """The repo-relative paths a single *spec* could resolve to from *importing_path*."""
    if not spec:
        return []
    suffix = Path(importing_path).suffix
    if suffix == ".py":
        return _py_candidates(root, importing_path, spec)
    if suffix == ".go":
        return _go_candidates(root, spec)
    if suffix in {".ts", ".tsx"}:
        return _ts_candidates(root, importing_path, spec)
    return []


def _py_candidates(root: Path, importing_path: str, spec: str) -> list[str]:
    """Python's specifier → file candidates.

    A leading ``.`` makes it relative; otherwise it is a top-level module path that may
    be either the repo's source root (a package the importer happens to live in) or a
    third-party import. Top-level names that do not resolve to a file in the tree are
    third-party — skipped here.
    """
    parts = spec.split(".")
    if not parts or not parts[0]:
        return []
    if parts[0].startswith("."):
        rel_dots = len(parts[0])
        package = Path(importing_path).parent
        for _ in range(rel_dots - 1):
            package = package.parent
        tail = "/".join(p for p in parts[1:] if p)
        base = (package / tail) if tail else package
        return list(_py_module_candidates(root, base))
    matches: list[str] = []
    seen: set[str] = set()
    importer_dir = Path(importing_path).parent
    for ancestor in [importer_dir, *importer_dir.parents]:
        base = ancestor.joinpath(*parts)
        for candidate in _py_module_candidates(root, base):
            if candidate not in seen:
                seen.add(candidate)
                matches.append(candidate)
        try:
            ancestor.relative_to(root)
        except ValueError:
            break
    base = root.joinpath(*parts)
    for candidate in _py_module_candidates(root, base):
        if candidate not in seen:
            seen.add(candidate)
            matches.append(candidate)
    return matches


def _py_module_candidates(root: Path, base: Path) -> Iterable[str]:
    """A Python *base* path's two file shapes: ``base.py`` and ``base/__init__.py``."""
    py = base.with_suffix(".py")
    if (root / py).is_file():
        yield py.as_posix()
    init = base / "__init__.py"
    if (root / init).is_file():
        yield init.as_posix()


def _go_candidates(root: Path, spec: str) -> list[str]:
    """Go's specifier → file candidates, dropping the suffix Go's importer expects."""
    if not spec:
        return []
    candidate = Path(spec).with_suffix(".go").as_posix()
    if (root / candidate).is_file():
        return [candidate]
    return []


def _ts_candidates(root: Path, importing_path: str, spec: str) -> list[str]:
    """TypeScript's specifier → file candidates, with the right relative resolution.

    A leading ``./`` or ``../`` is repo-relative to the importer; everything else is a
    package name (third-party or workspace alias) and yields no candidates.
    """
    if not spec:
        return []
    if not (spec.startswith("./") or spec.startswith("../")):
        return []
    base = (Path(importing_path).parent / spec).resolve()
    try:
        rel = base.relative_to(root.resolve())
    except ValueError:
        return []
    candidates: list[str] = []
    for suffix in (".ts", ".tsx"):
        candidate = (rel.with_suffix(suffix)).as_posix()
        if (root / candidate).is_file():
            candidates.append(candidate)
    for suffix in ("/index.ts", "/index.tsx"):
        candidate = (rel.as_posix() + suffix)
        if (root / candidate).is_file():
            candidates.append(candidate)
    return candidates


def build_worklist(
    repo_root: Path,
    features_root: Path,
    service: str,
    *,
    paths: Sequence[str] | None = None,
) -> BuildWorklist:
    """The deterministic worklist rows for a run, plus what the recheck agent adjudicates.

    *paths* filters the inventory and the digest skip to those repo-relative paths. A
    coder lane passes the story's changed paths; the okf-builder passes ``None`` for the
    whole tree. The same join runs in both cases — the only difference is which units
    are in the denominator — so a rebase that only touches the story's files surfaces
    only those units' gaps.

    ``inventory_path`` is the artifact ``ostler coverage`` reads (the workflow already
    produced one); the builder joins against it without re-walking the tree.
    """
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

    # The build's source inventory is parked beside the worklist, not inside the book:
    # the worklist is run state (gitignored under `.agents/`), the book is the committed
    # surface. `coverage_mod.run` is given the worklist-relative path; load through the
    # same lens so the builder and the join read the same file. A caller that has
    # written the inventory under `<features>/.source-inventory.json` is also accepted,
    # which is what the unit tests and the older read paths expect.
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
        # Both candidates absent: report the worklist-relative one (the live one) so
        # the error names what the build actually produced, not the historical name.
        raise RuntimeError(
            f"could not load the source inventory — none of {candidates} exists"
        )
    try:
        inventory = coverage_mod.load_inventory(inventory_path)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"could not load the source inventory at {inventory_path}: {exc}") from exc

    catalog = source_snapshots.load_catalog(root)
    waivers = coverage_mod.load_waivers(str(features / "coverage-waivers.json"))

    try:
        plan = backfill_mod.plan(
            graph, inventory, catalog,
            surface=surface, waivers=waivers,
            findings=doctor_mod.run(graph, check_schema=False).findings,
            scope=scope,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"backfill plan failed: {exc}") from exc

    rows: list[WorklistRow] = []
    for unit in plan.units:
        if path_filter and unit.path not in path_filter:
            continue
        row = _stale_unit_to_row(unit)
        if row is not None:
            rows.append(row)

    deleted = _deleted_paths(root, catalog)
    if path_filter:
        deleted = [path for path in deleted if path in path_filter]
    rows.extend(_trim_rows(root, surface, deleted))
    rows.extend(_trim_neighbour_rows(root, surface, deleted))

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