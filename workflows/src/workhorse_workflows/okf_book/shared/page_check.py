"""The code checks an aggregation turn's pages pass before a later turn judges them.

Nothing here changes a page. A page nothing reachable links to is
charged to the turn. Every doctor error on a changed page is charged, except a stale citation,
which the commit restamps. So is a bullet the page's type does not declare, which doctor only warns
about because a hand-kept book may carry one, but which on a written page is a claim nothing runs. Every obligation
of a changed page that does not compile is charged, unless the gap is one ostler cannot run
yet, which is ostler's to fix and not the page's. Two gaps are no defect at all: a precondition
the arrangement already discharges, and the placeholder obligation every node mints for itself,
which owes a check only through the claims under it. A gap already on a page the job does not
own when the job starts is inherited, and not charged.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from ostler import doctor
from ostler.book_reach import DeadPage, dead_pages
from ostler.model import load
from ostler.qa.compile import HARNESS_LIMIT_GAPS, Plan, compile_plan_gaps
from ostler.qa.context import book_context, validate_context, write_context
from ostler.qa.plan_source import Gap
from workhorse_workflows.okf_book.shared.blockers import Side
from workhorse_workflows.okf_book.shared.production import production_files

BOOK_STORY = "book"
OSTLER_GAPS = HARNESS_LIMIT_GAPS | frozenset({"needs-snapshot", "needs-out-of-band-observation"})
RESTAMPED_CODES = frozenset({"stale-citation"})
REACH_CODES = frozenset({"unreachable-node"})
CHARGED_WARNINGS = frozenset({"unknown-bullet"})
DISCHARGED_GAPS = frozenset({"precondition-discharged-by-arrangement"})
NODE_OBLIGATION_SUFFIXES = (":contract", ":end-state")
UNDECLARED_GAP = "no-verify-declared"
_OBLIGATION_PAGE = re.compile(r"^okf:(?P<page>[^#:]+\.md)")


def obligation_page(obligation_id: str) -> str:
    """The repo-relative page an obligation id names, empty when the id names none."""
    match = _OBLIGATION_PAGE.match(obligation_id)
    return match.group("page") if match else ""


def gap_page(gap: Gap) -> str:
    """The repo-relative page a gap's obligation names, empty when it names none."""
    return obligation_page(gap.obligation_id)


def is_defect(gap: Gap) -> bool:
    """False for a discharged precondition and for a node's own placeholder obligation with no check."""
    if gap.kind in DISCHARGED_GAPS:
        return False
    return not (gap.kind == UNDECLARED_GAP and gap.obligation_id.endswith(NODE_OBLIGATION_SUFFIXES))


def gap_side(gap: Gap) -> Side:
    """Ostler's, when the harness cannot observe what the book states. The book's otherwise."""
    return Side.OSTLER if gap.kind in OSTLER_GAPS else Side.BOOK


@dataclass(frozen=True, slots=True)
class BookCompilation:
    """What compiling the books gave: the plan, when one compiled, and every defect gap either way."""

    plan: Plan | None
    gaps: tuple[Gap, ...]

    @property
    def planned(self) -> bool:
        return self.plan is not None


class _ServicesContext(BaseModel):
    """The QA context of some services' books, which is written for the run and compiled into a plan.

    The fields are the ones every context carries. Ostler's own fields ride along as extras, untouched.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    version: Literal[1, 2]
    available: bool
    obligations: tuple[dict[str, JsonValue], ...]

    def write(self, spec: Path) -> None:
        _ = write_context(self.model_dump(mode="json"), spec)

    def compile(self) -> BookCompilation:
        compiled = compile_plan_gaps(self.model_dump(mode="json"), story=BOOK_STORY)
        gaps = tuple(gap for gap in compiled.gaps if is_defect(gap))
        return BookCompilation(plan=compiled if isinstance(compiled, Plan) else None, gaps=gaps)


def compile_services(root: Path, services: Iterable[str], spec: Path | None = None) -> BookCompilation:
    """Compile the named services' books, each with its production files as its source.

    The QA context is written into `spec` first, when one is given.
    """
    sources = {service: sorted(production_files(root, service)) for service in services}
    packet = book_context(root, source_roots=sources)
    problems = validate_context(packet)
    if problems:
        raise ValueError(f"the books' QA context is malformed: {'; '.join(problems)}")
    context = _ServicesContext.model_validate(packet)
    if spec is not None:
        context.write(spec)
    return context.compile()


def book_gaps(root: Path, services: Iterable[str]) -> tuple[Gap, ...]:
    """Every defect among the obligations the named services' books state and ostler does not compile."""
    return compile_services(root, services).gaps


def dead_book_pages(root: Path) -> tuple[DeadPage, ...]:
    """Every page no link path from its service's entries page reaches."""
    return tuple(dead_pages(load(root)))


def unreached(root: Path, pages: Iterable[str]) -> tuple[DeadPage, ...]:
    """The named pages no link path from an entries page reaches."""
    wanted = frozenset(pages)
    return tuple(page for page in dead_book_pages(root) if page.rel in wanted)


def charged_pages(root: Path, changed: Iterable[str], owned: Iterable[str]) -> tuple[str, ...]:
    """The pages a job answers for: every page it changed, and each of its own the entries page reaches, changed or not.

    An own page nothing reaches is charged for its reach alone, since it is collected after the job.
    """
    mine = frozenset(owned)
    dead = frozenset(page.rel for page in unreached(root, mine))
    return tuple(sorted({*changed, *(mine - dead)}))


def _doctor_problems(root: Path, pages: list[str]) -> list[str]:
    if not pages:
        return []
    report = doctor.scope_to_paths(doctor.run(load(root)), pages)
    return [
        f"{f.path}:{f.line}: {f.code}: {f.message}" + (f" {f.suggestion}" if f.suggestion else "")
        for f in report.findings
        if (f.severity == "error" or f.code in CHARGED_WARNINGS) and f.code not in RESTAMPED_CODES | REACH_CODES
    ]


def _gap_line(gap: Gap) -> str:
    return f"{gap.obligation_id} does not compile: {gap.kind}: {gap.detail}"


def _gap_problems(root: Path, service: str, pages: list[str], known: frozenset[str]) -> list[str]:
    wanted = frozenset(pages)
    by_fix: dict[tuple[str, str], list[str]] = {}
    for gap in book_gaps(root, (service,)):
        if gap_page(gap) in wanted and gap_side(gap) is Side.BOOK and _gap_line(gap) not in known:
            by_fix.setdefault((gap.kind, gap.detail), []).append(gap.obligation_id)
    return [
        f"{ids[0]} does not compile: {kind}: {detail}"
        if len(ids) == 1
        else f"each of {len(ids)} claims does not compile: {kind}: {detail} The claims: {', '.join(ids)}"
        for (kind, detail), ids in by_fix.items()
    ]


def inherited_gaps(root: Path, service: str, owned: frozenset[str]) -> tuple[str, ...]:
    """The book's compile gaps already on pages a job does not own. The job may only add to those pages, so it is not charged for them."""
    return tuple(
        _gap_line(gap)
        for gap in book_gaps(root, (service,))
        if gap_side(gap) is Side.BOOK and gap_page(gap) not in owned
    )


def unreached_problems(pages: Iterable[str]) -> tuple[str, ...]:
    """What the turn is charged for each page it wrote that nothing reachable links to."""
    return tuple(f"{page} is linked from no page the entries page reaches, so it was deleted." for page in pages)


def unlinked_own_page_problems(root: Path, owned: Iterable[str]) -> tuple[str, ...]:
    """What the job is charged for each page of its own that nothing reachable links to. Garbage collection deletes it after the job."""
    return tuple(
        f"{page.rel} is linked from no page the entries page reaches, so it is deleted after this job. "
        "Link it from a page the entries page reaches, or delete it."
        for page in unreached(root, owned)
    )


def page_problems(
    root: Path, service: str, changed: Iterable[str], inherited_gaps: Iterable[str] = ()
) -> tuple[str, ...]:
    """The doctor errors and the book's compile gaps on the changed pages still in the book, the inherited gaps left out.

    Reach is left out: a new page nothing reaches is deleted and charged on its own, and a committed one is garbage collection's.
    """
    pages = sorted(p for p in frozenset(changed) if p.endswith(".md") and (root / p).is_file())
    return (*_doctor_problems(root, pages), *_gap_problems(root, service, pages, frozenset(inherited_gaps)))
