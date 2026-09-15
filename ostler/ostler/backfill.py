"""``ostler backfill plan`` — what in the book no longer matches the code.

One question, asked once. Before this, three places computed a stale set independently: the
builder's `prepare` diffed git, its `incremental` node read a story's QA packet, and the
coverage join compared an inventory against the citations. Three answers to one question
drift, and the drift was invisible — a book could report every unit covered while its
citations described a commit from months earlier, because nothing compared what the book said
about a symbol with what that symbol currently *is*.

The stale set is two sets over two on-disk inputs, and every lifecycle event is the same
computation:

``uncovered``
    in the inventory, cited by no node. New code, and the only set a first fill produces.
``dangling``
    doctor already says the citation points at nothing. Carried here so one command answers
    "what does this book owe" rather than two.

A cited symbol whose *bytes* have changed is `doctor`'s `stale-citation` finding, not this
module's: a per-citation `@digest` stamp comparison against a live checkout, not a snapshot
this file used to keep and compare against. A cited symbol that *moved* to another path
degrades to the same `dangling` row a renamed-away symbol always got — its old citation names
code that is not there — and the coverage join would otherwise also raise the new location as
`uncovered`, reporting the one edit as two. A `dangling` row whose symbol name is unique across
the inventory carries that new path as `relocated_to`, set once here so every caller reads the
same verdict rather than re-deriving it: `_already_documented_elsewhere` drops the `uncovered`
row the move would otherwise double-count, and a repair worklist keeps the `dangling` row alive
instead of trimming it, because the symbol did not vanish — it moved. A name that recurs
elsewhere is not provably the moved symbol, so it is left unmarked and both rows stand.

Everything here is a function of its arguments. The git diff, the doctor run and the file
walk all happen in the caller (`cli`), because the property the three implementations this
replaces all lacked is being testable without a checkout, an agent or a workflow.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ostler import coverage as coverage_mod
from ostler import refs as refs_mod
from ostler.doctor import Finding
from ostler.model import Graph

#: The doctor codes that say a citation points at nothing.
DANGLING_CODES = frozenset({"dangling-code-ref", "missing-code-symbol"})

#: Ordered by how much work the row implies, cheapest first, so a rendered plan reads as a
#: queue rather than a bag.
REASON_ORDER = ("dangling", "uncovered")


@dataclass(frozen=True)
class StaleUnit:
    """One `code:` target the book owes work on, and why."""

    #: The `code:` target, in the book's own grammar (`path::symbol`).
    unit: str
    #: One of `REASON_ORDER`.
    reason: str
    #: What the reason is grounded in — the doctor message for a `dangling`. Never a remedy:
    #: the plan states the finding.
    evidence: str = ""
    #: The book nodes citing this unit. Empty for `uncovered`, which is cited by nobody.
    nodes: tuple[str, ...] = ()
    #: For a `dangling` row whose symbol is unique elsewhere in the inventory, the `code:`
    #: target it moved to. Empty otherwise — including when the symbol recurs at more than
    #: one other path, which is not provably a move. The single place this is decided; a
    #: caller outside this module reads the field rather than re-deriving the verdict.
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
    #: The inventory's own errors, carried through: a blind front end must not present as a
    #: book with nothing to do. `is_clean` is false while any of these stand.
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
    """The coverage join's misses, verbatim. The transitive module rule is already applied."""
    return [
        StaleUnit(unit=miss["code"], reason="uncovered", evidence=miss.get("kind", ""))
        for miss in join["missing"]
    ]


def _dangling(findings: Iterable[Finding], cited: dict[str, list[str]]) -> list[StaleUnit]:
    """Doctor's verdict on citations that point at nothing.

    Takes the findings rather than a graph so the plan stays a pure function; `cli` runs
    doctor. Keyed on the finding's `ref`, which is the offending `code:` target itself.

    Only refs this book actually cites are kept. Doctor reads the whole graph, and a plan
    scoped to one surface that reports another book's broken bullets is a plan whose count
    cannot be acted on by the run that asked for it.
    """
    rows: list[StaleUnit] = []
    seen: set[str] = set()
    for finding in findings:
        if finding.code not in DANGLING_CODES or not finding.ref or finding.ref in seen:
            continue
        if finding.ref not in cited:
            continue
        seen.add(finding.ref)
        rows.append(StaleUnit(
            unit=finding.ref, reason="dangling", evidence=finding.message,
            nodes=tuple(cited.get(finding.ref, ())),
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
    """Tag each `dangling` row with where its symbol moved to, when that is unambiguous.

    A symbol name unique across the inventory and present at a path other than the dangling
    citation's own is not lost, it moved — `relocated_to` is the single place that verdict is
    decided, computed here once so `_already_documented_elsewhere` and every caller outside
    this module (a repair worklist included) read the same answer rather than each
    re-deriving it, possibly disagreeing.
    """
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
    """Drop an `uncovered` row whose symbol is a `dangling` citation's symbol, moved not lost.

    Without a stored watermark, a symbol that moved from file A to file B is invisible as a
    move — A's old citation surfaces as `dangling` on its own, and B's copy is indistinguishable
    from code the book never covered. Reporting both is reporting the same edit twice, so a row
    is dropped here only when `_mark_relocated` already tagged the matching `dangling` row as a
    move: a name that recurs elsewhere is not provably the moved symbol, and suppressing it
    would bury real uncovered work behind a coincidence.
    """
    kept: list[StaleUnit] = []
    for row in uncovered:
        symbol = _symbol_of(row.unit)
        if symbol and symbol in relocated_symbols:
            continue
        kept.append(row)
    return kept


def _in_scope(unit: StaleUnit, scope: Sequence[str]) -> bool:
    """Whether a row survives `--scope`.

    Both narrow by path and neither widens: a row outside the scope is not *absent*, it is
    simply not this run's work, and the next unscoped run will still report it.
    """
    path = unit.path
    if scope and not any(path == part or path.startswith(part.rstrip("/") + "/")
                         for part in scope):
        return False
    return True


def plan(graph: Graph, inventory: dict, *,
         surface: str | None = None, waivers: dict[str, str] | None = None,
         findings: Iterable[Finding] = (), scope: Sequence[str] = ()) -> BackfillPlan:
    """The stale set: what the book owes the code at this moment.

    *inventory* is the artifact `ostler coverage` reads, *findings* doctor's own.
    """
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
    """The human face. `--json` is the machine's."""
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
