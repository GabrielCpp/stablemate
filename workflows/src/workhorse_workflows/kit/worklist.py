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

**The set is two joins, in drain order.**

* ``dangling`` — doctor codes ``dangling-code-ref``, ``missing-code-symbol``. The
  checkpoint's channel, here surfaced as ``fix:`` rows. A cited symbol's bytes
  disagreeing with the source is doctor's ``stale-citation`` finding instead,
  queued by ``coverage._regrounding`` — a different mechanism, not this join.
* ``uncovered`` — units in the inventory nothing cites. The builder surfaces the
  list; the recheck agent adjudicates which are real work, which are helpers, and
  which are deliberate non-units. A symbol that moved to another path is folded in
  here too: ``backfill.plan`` suppresses the new location's ``uncovered`` row when
  its symbol name uniquely matches a ``dangling`` row already surfaced, so the one
  edit reads as one finding.

A *trim* joins them: an own-repository path the book cites that the tree no longer
carries. Its citations are dangling in a different way (the file is gone), so the
bullets are cut, the node is queued for authored removal if it lost its last
bullet, and the neighbours are queued for review so a journey whose third step
vanished is read against the book rather than against the file. A foreign
``repo://`` citation is never trimmed this way — a checkout-less foreign ref is
``unreachable-citation`` territory, not a deleted path in this tree. A citation
whose symbol relocated (``backfill.plan`` marks the ``dangling`` row's
``relocated_to``) is excluded from trim as well: the file is gone but the symbol
is not, and trim's own rule against re-pointing a bullet to a neighbour means
deleting the node instead of fixing the citation — so the row survives as
``fix:dangling`` and drives a repair that re-points it.
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
from ostler import refs as refs_mod


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

    A ``dangling`` row carries a node list — every node that cited the unit — so a
    single dangling citation fans out into one row per citing node. The first citing
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
    """Every own-repository path the book cites that the tree no longer carries.

    Read off the book's own citations (``coverage.citations``), not a catalog — trim's
    job is to notice a citation pointing at nothing, and the citations the book carries
    right now are exactly that answer. A foreign ``repo://`` citation is skipped: it
    names a path in another repository, and a missing checkout there is
    ``unreachable-citation`` territory, not a deleted path in this tree.
    """
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
    """``trim-bullet`` rows for every node citing a path the tree no longer carries.

    A path the book cites but the tree lacks leaves its bullets pointing at nothing —
    doctor reports it as ``dangling-code-ref``, but trim is the more specific remedy,
    since it also knows which path is gone and can retire the bullet rather than just
    flag it. Every node citing a deleted own-repository path gets a row that retires
    the bullets and queues authored removal if the node lost its last bullet. A
    foreign ``repo://`` citation is never matched here, even if its path happens to
    collide with a deleted local one. A citation in *relocated* is skipped: its symbol
    moved rather than vanished, and ``backfill.plan`` already keeps a ``dangling`` row
    for it so the citation gets re-pointed instead of retired.

    ``coverage.citations`` keys ``cited_by`` digest-free (``ostler.refs.strip_digest``), so
    ``relocated`` — raw bullet text from ``backfill.StaleUnit.unit`` — is stripped the same
    way before the comparison: a citation stamped before its symbol relocated still carries
    its ``@digest``, and comparing that against a digest-stripped key would silently fail to
    recognise the relocation and trim a citation ``backfill.plan`` means to keep alive as
    ``dangling``.
    """
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
    """``trim-review`` rows for every node that linked to something trimmed.

    A journey whose third step vanished is structurally valid and reads as a corpse
    until somebody re-reads the steps against the book. The detection is one pass
    over the graph: every incoming edge to a node whose citations now dangle.
    Without this, an authored removal lands and its caller still lists a step that
    does not exist. A citation in *relocated* is excluded from ``trimmed_citations``
    the same way ``_trim_rows`` excludes it: its node is not being trimmed for that
    citation, only for whichever others are genuinely gone.
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
    """``unreachable`` rows for every page nothing in the book reaches.

    The concept nobody ever linked to and the flow whose only incoming edge was
    the page that just got trimmed both read as orphans under ``graph --orphans``,
    and both queue the same authored-removal row. The check is the one the OKF
    graph already computes — its ``select(orphans=True)`` yields every page no
    edge reaches, on the page or any heading in it, so a heading of a linked
    page is never a row of its own.
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
            # Trim already covers this citation more specifically (it also queues
            # neighbour review), so a `dangling` row for a citation under a path trim
            # is about to retire would just be the same finding queued twice. A
            # relocated citation is the exception: trim would delete the node outright
            # (`investigate.md`'s trim-bullet forbids re-pointing to a neighbour), so
            # the `dangling` row survives to drive a repair that re-points the bullet
            # instead of erasing documentation of a symbol that still exists.
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