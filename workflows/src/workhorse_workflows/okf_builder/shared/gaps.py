"""The QA compiler's gaps on a book, in doctor's own finding vocabulary."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ostler.doctor import gap_findings
from ostler.qa.compile import Gap, compile_plan_gaps
from ostler.qa.context import book_context
from ostler.qa.dispatch import hosts_observation

BOOK_TARGET = "(book)"


def _features_rel(repo_root: Path, features_root: str) -> str:
    try:
        return Path(features_root).resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return Path(features_root).as_posix()


def _line_of(obligation: Mapping[str, Any]) -> int:
    position = obligation.get("docPosition") or []
    if not isinstance(position, list):
        return 0
    lines = [int(value) for value in position if isinstance(value, int) and value > 0]
    return lines[-1] if lines else 0


def _obligations_in(context: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Every obligation the context minted, by id — where a gap's node and line come from."""
    return {
        str(entry.get("id")): entry
        for entry in context.get("obligations", [])
        if isinstance(entry, Mapping)
    }


def _rows(
    gaps: list[Gap], obligations: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Each gap as a doctor finding on the node that owes the obligation."""
    rows: list[dict[str, Any]] = []
    for gap, finding in zip(gaps, gap_findings(list(gaps)), strict=True):
        owner = obligations.get(gap.obligation_id) or {}
        node = str(owner.get("node") or finding.ref)
        node_type = str(owner.get("nodeType") or "")
        unhostable = bool(node_type) and not hosts_observation(node_type)
        rows.append({
            "severity": finding.severity,
            "code": finding.code,
            "message": finding.message,
            "path": str(owner.get("source") or "") or node.split("#", 1)[0],
            "ref": node,
            "line": _line_of(owner),
            "fixable": False,
            "unhostable": unhostable,
        })
    return rows


def _book_obligations(repo_root: str, features_root: str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    return book_context(root, features_root=_features_rel(root, features_root))


def compile_gap_findings(repo_root: str, features_root: str) -> list[dict[str, Any]]:
    """Every obligation the book cannot compile, as a doctor finding on the node that owes it.

    `ostler.doctor.run` reads the graph alone, so a defect only the compiled obligation
    context can see is invisible to it. This reads that layer and speaks doctor's
    vocabulary, so the repair loop seeds, batches and settles compile gaps exactly as it
    does graph findings.
    """
    context = _book_obligations(repo_root, features_root)
    result = compile_plan_gaps(context, story=BOOK_TARGET)
    return _rows(list(result.gaps), _obligations_in(context))


def reported_gap_findings(
    repo_root: str, features_root: str, reported: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """The gaps a live audit already reported, located and named the same way.

    The audit compiles each spec dir's own plan, so its gap list is the one to repair.
    Recompiling the book here would answer a different question. Only the obligation's
    node and line are read back out of the book.
    """
    context = _book_obligations(repo_root, features_root)
    gaps = [
        Gap(str(gap.get("obligation_id", "")), str(gap.get("kind", "")),
            str(gap.get("detail", "")))
        for gap in reported
        if isinstance(gap, Mapping) and gap.get("obligation_id")
    ]
    return _rows(gaps, _obligations_in(context))


__all__ = ["BOOK_TARGET", "compile_gap_findings", "reported_gap_findings"]
