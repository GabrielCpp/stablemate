"""``ostler backfill plan`` — what in the book no longer matches the code.

One question, asked once. Before this, three places computed a stale set independently: the
builder's `prepare` diffed git, its `incremental` node read a story's QA packet, and the
coverage join compared an inventory against the citations. Three answers to one question
drift, and the drift was invisible — a book could report every unit covered while its
citations described a commit from months earlier, because nothing compared what the book said
about a symbol with what that symbol currently *is*.

The stale set is four sets over four on-disk inputs, and every lifecycle event is the same
computation with a different starting watermark:

``uncovered``
    in the inventory, cited by no node. New code, and the only set a first fill produces.
``drifted``
    cited, and the catalog's digest for it disagrees with the file's. The node describes a
    symbol that has since been rewritten.
``moved``
    cited, gone from the path the citation names, and present *unchanged* somewhere else.
    Re-grounding work, not re-documenting work — the distinction a git rename detector makes
    and a coverage join cannot.
``dangling``
    doctor already says the citation points at nothing. Carried here so one command answers
    "what does this book owe" rather than two.

Everything here is a function of its arguments. The git diff, the doctor run and the file
walk all happen in the caller (`cli`), because the property the three implementations this
replaces all lacked is being testable without a checkout, an agent or a workflow.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ostler import coverage as coverage_mod
from ostler import inventory as inventory_mod
from ostler import refs as refs_mod
from ostler.doctor import Finding
from ostler.model import Graph
from ostler.source_snapshots import SELF_REPOSITORY, SourceCatalog, SourceFile

#: The doctor codes that say a citation points at nothing. `dangling-repository-ref` is here
#: too: from the book's side it is the same defect — a `code:` bullet naming code that this
#: repository cannot show you — and the remedy is the same edit.
DANGLING_CODES = frozenset({
    "dangling-code-ref", "dangling-repository-ref", "missing-code-symbol",
})

#: Ordered by how much work the row implies, cheapest first, so a rendered plan reads as a
#: queue rather than a bag.
REASON_ORDER = ("dangling", "moved", "drifted", "uncovered")


@dataclass(frozen=True)
class StaleUnit:
    """One `code:` target the book owes work on, and why."""

    #: The `code:` target, in the book's own grammar (`path::symbol`).
    unit: str
    #: One of `REASON_ORDER`.
    reason: str
    #: What the reason is grounded in — the new path for a `moved`, the doctor message for a
    #: `dangling`, the digests for a `drifted`. Never a remedy: the plan states the finding.
    evidence: str = ""
    #: The book nodes citing this unit. Empty for `uncovered`, which is cited by nobody.
    nodes: tuple[str, ...] = ()
    #: For a `moved` row, where the symbol lives now — the ref the citation should name. It
    #: is what lets the plan drop the `uncovered` row the new location would otherwise raise:
    #: the symbol is documented, and the bullet pointing at it is what is out of date.
    target: str = ""

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
                 "nodes": list(u.nodes), "target": u.target}
                for u in self.units
            ],
            "errors": list(self.errors),
        }


def _snapshot_files(catalog: SourceCatalog | None) -> dict[str, SourceFile]:
    """The graph's own repository's snapshot, by path. Empty means "no watermark yet"."""
    if catalog is None:
        return {}
    snapshot = catalog.repository(SELF_REPOSITORY)
    if snapshot is None:
        return {}
    return {item.path: item for item in snapshot.files}


class _CurrentDigests:
    """Digests of the tree as it is now, read once per file and only when asked for.

    A book cites a small fraction of a source tree, and the `moved` search below needs a
    reverse index over the *inventory* rather than the citations — so the whole-tree read is
    deferred until something is actually missing from where it was cited.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._by_path: dict[str, dict[str, str]] = {}
        self._by_digest: dict[str, tuple[str, str]] | None = None

    def of(self, path: str) -> dict[str, str]:
        cached = self._by_path.get(path)
        if cached is None:
            try:
                cached = dict(inventory_mod.symbol_digests_at(self._root / path))
            except (OSError, UnicodeDecodeError):
                cached = {}
            self._by_path[path] = cached
        return cached

    def locate(self, digest: str, paths: Iterable[str]) -> tuple[str, str] | None:
        """Where *digest* lives now, searching *paths*. `None` when it lives nowhere."""
        if self._by_digest is None:
            index: dict[str, tuple[str, str]] = {}
            for path in paths:
                for name, value in self.of(path).items():
                    index.setdefault(value, (path, name))
            self._by_digest = index
        return self._by_digest.get(digest)


def _uncovered(join: dict) -> list[StaleUnit]:
    """The coverage join's misses, verbatim. The transitive module rule is already applied."""
    return [
        StaleUnit(unit=miss["code"], reason="uncovered", evidence=miss.get("kind", ""))
        for miss in join["missing"]
    ]


def _dangling(findings: Iterable[Finding], cited: dict[str, list[str]],
              claimed: set[str]) -> list[StaleUnit]:
    """Doctor's verdict on citations that point at nothing.

    Takes the findings rather than a graph so the plan stays a pure function; `cli` runs
    doctor. Keyed on the finding's `ref`, which is the offending `code:` target itself.

    Only refs this book actually cites are kept. Doctor reads the whole graph, and a plan
    scoped to one surface that reports another book's broken bullets is a plan whose count
    cannot be acted on by the run that asked for it.

    A ref *claimed* by a `moved` row is dropped. Doctor is right that the citation points at
    nothing, but "this symbol is now over there" is the more useful sentence and it comes with
    the destination; two rows for one bullet would have an editor read the weaker one first.
    """
    rows: list[StaleUnit] = []
    seen: set[str] = set(claimed)
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


def _watermark_rows(cited: dict[str, list[str]], stored: dict[str, SourceFile],
                    current: _CurrentDigests,
                    inventory_paths: Sequence[str]) -> list[StaleUnit]:
    """`drifted` and `moved`, from the citations the catalog has a watermark for.

    A citation with no stored digest yields nothing. That is the first-fill case and the
    pre-watermark case, and both are already answered: an undocumented symbol is `uncovered`,
    and a documented one whose watermark was never taken has nothing to disagree with. A
    watermark says "this changed"; its absence never says "this did not".

    Cross-repository citations are skipped. Their current digest lives in a checkout this
    process was not given, so the only honest answer is that the catalog is the newest thing
    here — `provenance.source_freshness` is the check that covers them.
    """
    rows: list[StaleUnit] = []
    for ref in sorted(cited):
        try:
            parsed = refs_mod.parse_code_ref(ref)
        except ValueError:
            continue
        if parsed.repository != SELF_REPOSITORY:
            continue
        snapshot = stored.get(parsed.path)
        if snapshot is None:
            continue
        nodes = tuple(cited[ref])
        if not parsed.symbol:
            live = current.of(parsed.path)
            if snapshot.declarations and live and _file_digest(snapshot) != _joined(live):
                rows.append(StaleUnit(unit=ref, reason="drifted",
                                      evidence="the file's declarations changed", nodes=nodes))
            continue
        was = snapshot.digest_of(parsed.symbol)
        if not was:
            continue
        now = current.of(parsed.path).get(parsed.symbol)
        if now is None:
            found = current.locate(was, inventory_paths)
            if found is not None:
                target = f"{found[0]}::{found[1]}"
                rows.append(StaleUnit(unit=ref, reason="moved", target=target,
                                      evidence=f"unchanged, now at {target}", nodes=nodes))
            continue
        if now != was:
            rows.append(StaleUnit(unit=ref, reason="drifted",
                                  evidence=f"{was[:12]} → {now[:12]}", nodes=nodes))
    return rows


def _joined(digests: dict[str, str]) -> str:
    return "\0".join(f"{name}\0{digests[name]}" for name in sorted(digests))


def _file_digest(snapshot: SourceFile) -> str:
    return "\0".join(f"{item.name}\0{item.content_sha256}"
                     for item in sorted(snapshot.declarations, key=lambda i: i.name))


def _in_scope(unit: StaleUnit, scope: Sequence[str], changed: set[str] | None) -> bool:
    """Whether a row survives `--scope` and `--since`.

    Both narrow by path and neither widens: a row outside the scope is not *absent*, it is
    simply not this run's work, and the next unscoped run will still report it.
    """
    path = unit.path
    if changed is not None and path not in changed:
        return False
    if scope and not any(path == part or path.startswith(part.rstrip("/") + "/")
                         for part in scope):
        return False
    return True


def plan(graph: Graph, inventory: dict, catalog: SourceCatalog | None, *,
         surface: str | None = None, waivers: dict[str, str] | None = None,
         findings: Iterable[Finding] = (), scope: Sequence[str] = (),
         changed: set[str] | None = None) -> BackfillPlan:
    """The stale set: what the book owes the code at this moment.

    *inventory* is the artifact `ostler coverage` reads, *catalog* the watermark
    `sources.json` holds, *findings* doctor's own. *changed* is `--since`'s path set, and
    `None` — not the empty set — means "no revision was named": an empty set is a real
    answer (nothing changed) and must produce an empty plan rather than a full one.
    """
    root = Path(str(inventory.get("repoRoot") or graph.root))
    cited = coverage_mod.citations(graph, surface)
    join = coverage_mod.compute(inventory, cited, waivers or {})
    current = _CurrentDigests(root)
    paths = sorted({str(unit.get("path", "")) for unit in inventory["units"]} - {""})

    watermarked = _watermark_rows(cited, _snapshot_files(catalog), current, paths)
    relocated = {row.target for row in watermarked if row.reason == "moved"}
    rows = (
        _dangling(findings, cited, {row.unit for row in watermarked})
        + watermarked
        # A symbol a `moved` row already points at is documented — by a bullet naming its old
        # path. The remedy is that bullet, not a second node describing the same code.
        + [row for row in _uncovered(join) if row.unit not in relocated]
    )

    order = {reason: n for n, reason in enumerate(REASON_ORDER)}
    kept = sorted(
        (row for row in rows if _in_scope(row, scope, changed)),
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
