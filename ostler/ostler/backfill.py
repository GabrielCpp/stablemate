"""``ostler backfill plan`` — what in the book no longer matches the code."""
from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ostler import coverage as coverage_mod
from ostler import refs as refs_mod
from ostler.doctor import Finding
from ostler.model import Graph

DANGLING_CODES = frozenset({"dangling-code-ref", "directory-code-ref", "missing-code-symbol"})

REASON_ORDER = ("dangling", "uncovered")


@dataclass(frozen=True)
class StaleUnit:
    """One `code:` target the book owes work on, and why."""

    unit: str
    reason: str
    evidence: str = ""
    nodes: tuple[str, ...] = ()
    relocated_to: str = ""

    @property
    def path(self) -> str:
        """The file the unit lives in, for a scope filter to match on."""
        try:
            return refs_mod.parse_code_ref(self.unit).path
        except ValueError:
            return self.unit.split("::", 1)[0]


@dataclass(frozen=True)
class BackfillPlan:
    """The whole stale set, plus what the instrument could not see."""

    surface: str = ""
    units: tuple[StaleUnit, ...] = ()
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_clean(self) -> bool:
        return not self.units and not self.errors

    def by_reason(self) -> dict[str, list[StaleUnit]]:
        return {
            reason: [unit for unit in self.units if unit.reason == reason]
            for reason in REASON_ORDER
        }

    def as_dict(self) -> dict:
        return {
            "surface": self.surface,
            "clean": self.is_clean,
            "counts": {reason: len(rows) for reason, rows in self.by_reason().items()},
            "units": [
                {"unit": u.unit, "reason": u.reason, "evidence": u.evidence,
                 "nodes": list(u.nodes)}
                for u in self.units
            ],
            "errors": list(self.errors),
        }


def _uncovered(join: dict) -> list[StaleUnit]:
    """The coverage join's misses, verbatim."""
    return [
        StaleUnit(unit=miss["code"], reason="uncovered", evidence=miss.get("kind", ""))
        for miss in join["missing"]
    ]


def _dangling(findings: Iterable[Finding], cited: dict[str, list[str]]) -> list[StaleUnit]:
    """Doctor's verdict on citations that point at nothing."""
    rows: list[StaleUnit] = []
    seen: set[str] = set()
    for finding in findings:
        if finding.code not in DANGLING_CODES or not finding.ref or finding.ref in seen:
            continue
        key = refs_mod.strip_digest(finding.ref)
        if key not in cited:
            continue
        seen.add(finding.ref)
        rows.append(StaleUnit(
            unit=finding.ref, reason="dangling", evidence=finding.message,
            nodes=tuple(cited.get(key, ())),
        ))
    return rows


def _symbol_of(unit: str) -> str:
    """The bare symbol name a `code:` target names, or `""` for a whole-file target."""
    try:
        return refs_mod.parse_code_ref(unit).symbol or ""
    except ValueError:
        return unit.rsplit("::", 1)[-1] if "::" in unit else ""


def _mark_relocated(
    dangling: Iterable[StaleUnit], symbol_paths: dict[str, list[str]],
) -> list[StaleUnit]:
    """Tag each `dangling` row with where its symbol moved to, when that is unambiguous."""
    marked: list[StaleUnit] = []
    for row in dangling:
        symbol = _symbol_of(row.unit)
        paths = symbol_paths.get(symbol, []) if symbol else []
        other = [path for path in paths if path != row.path]
        if symbol and len(paths) == 1 and other:
            row = dataclasses.replace(row, relocated_to=f"{other[0]}::{symbol}")
        marked.append(row)
    return marked


def _already_documented_elsewhere(
    uncovered: Iterable[StaleUnit], relocated_symbols: set[str],
) -> list[StaleUnit]:
    """Drop an `uncovered` row whose symbol is a `dangling` citation's symbol, moved not lost."""
    kept: list[StaleUnit] = []
    for row in uncovered:
        symbol = _symbol_of(row.unit)
        if symbol and symbol in relocated_symbols:
            continue
        kept.append(row)
    return kept


def _in_scope(unit: StaleUnit, scope: Sequence[str]) -> bool:
    """Whether a row survives `--scope`."""
    path = unit.path
    if scope and not any(path == part or path.startswith(part.rstrip("/") + "/")
                         for part in scope):
        return False
    return True


def plan(graph: Graph, inventory: dict, *,
         surface: str | None = None, waivers: dict[str, str] | None = None,
         findings: Iterable[Finding] = (), scope: Sequence[str] = ()) -> BackfillPlan:
    """The stale set: what the book owes the code at this moment."""
    cited = coverage_mod.citations(graph, surface)
    join = coverage_mod.compute(inventory, cited, waivers or {})

    symbol_paths: dict[str, list[str]] = {}
    for unit in inventory["units"]:
        symbol = str(unit.get("symbol") or "")
        path = str(unit.get("path") or "")
        if symbol:
            symbol_paths.setdefault(symbol, []).append(path)
    dangling_rows = _mark_relocated(_dangling(findings, cited), symbol_paths)
    relocated_symbols = {
        _symbol_of(row.unit) for row in dangling_rows if row.relocated_to
    }
    uncovered_rows = _already_documented_elsewhere(_uncovered(join), relocated_symbols)

    rows = dangling_rows + uncovered_rows

    order = {reason: n for n, reason in enumerate(REASON_ORDER)}
    kept = sorted(
        (row for row in rows if _in_scope(row, scope)),
        key=lambda row: (order.get(row.reason, len(order)), row.unit),
    )
    return BackfillPlan(surface=surface or "", units=tuple(kept),
                        errors=tuple(join["errors"]))


def render(result: BackfillPlan) -> str:
    """The human face."""
    if result.is_clean:
        return f"{result.surface or '(all)'}: the book matches the code — nothing to backfill"
    counts = result.by_reason()
    head = ", ".join(f"{len(rows)} {reason}" for reason, rows in counts.items() if rows)
    lines = [f"{result.surface or '(all)'}: {head}"]
    for error in result.errors:
        lines.append(f"  inventory error: {error}")
    for reason in REASON_ORDER:
        for row in counts[reason]:
            suffix = f" — {row.evidence}" if row.evidence else ""
            lines.append(f"  {reason} {row.unit}{suffix}")
    return "\n".join(lines)


__all__ = [
    "DANGLING_CODES",
    "REASON_ORDER",
    "BackfillPlan",
    "StaleUnit",
    "plan",
    "render",
]
