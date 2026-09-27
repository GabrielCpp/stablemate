"""The check the writer runs on its whole book, and the run repeats after it.

Nothing here changes a page. It reports a missing entries page, every page nothing the entries
page reaches, and every doctor error on the book, except a stale citation, which the commit
restamps. So is a bullet the page's type does not declare, which doctor only warns about because
a hand-kept book may carry one, but which on a written page is a claim nothing runs. It reports
every command, endpoint and screen no flow walks, and every obligation that does not compile, unless the gap is one ostler cannot run yet, which is
ostler's to fix and not the book's. Two gaps are no defect at all: a precondition the arrangement
already discharges, and the placeholder obligation every node mints for itself, which owes a
check only through the claims under it.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from ostler import doctor
from ostler import graph as graph_mod
from ostler.book_reach import DeadPage, dead_pages
from ostler.model import Graph, load
from ostler.qa.compile import HARNESS_LIMIT_GAPS, Plan, compile_plan_gaps
from ostler.qa.context import book_context, validate_context, write_context
from ostler.qa.plan_source import Gap
from workhorse_workflows.okf_book.shared.blockers import Side
from workhorse_workflows.okf_book.shared.entries import book_dir, entries_path
from workhorse_workflows.okf_book.shared.production import production_files

BOOK_STORY = "book"
OSTLER_GAPS = HARNESS_LIMIT_GAPS | frozenset({"needs-snapshot", "needs-out-of-band-observation"})
RESTAMPED_CODES = frozenset({"stale-citation"})
REACH_CODES = frozenset({"unreachable-node"})
CHARGED_WARNINGS = frozenset({"unknown-bullet"})
JOURNEY_TYPES = frozenset({"command", "endpoint", "screen"})
WALK_BULLETS = frozenset({"start", "steps", "end"})
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
    obligations: tuple[str, ...] = ()

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
        obligations = tuple(str(obligation.get("id", "")) for obligation in self.obligations)
        return BookCompilation(plan=compiled if isinstance(compiled, Plan) else None, gaps=gaps, obligations=obligations)


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


def dead_book_pages(root: Path) -> tuple[DeadPage, ...]:
    """Every page no link path from its service's entries page reaches."""
    return tuple(dead_pages(load(root)))


@dataclass(frozen=True, slots=True)
class PageProblem:
    """One problem the check reports, and the repo-relative page it sits on."""

    page: str
    text: str


def _doctor_problems(book: Graph, pages: list[str]) -> list[PageProblem]:
    if not pages:
        return []
    report = doctor.scope_to_paths(doctor.run(book), pages)
    return [
        PageProblem(f.path, f"{f.path}:{f.line}: {f.code}: {f.message}" + (f" {f.suggestion}" if f.suggestion else ""))
        for f in report.findings
        if (f.severity == "error" or f.code in CHARGED_WARNINGS) and f.code not in RESTAMPED_CODES | REACH_CODES
    ]


def _gap_problems(gaps: Iterable[Gap]) -> list[PageProblem]:
    by_fix: dict[tuple[str, str, str], list[str]] = {}
    for gap in gaps:
        by_fix.setdefault((gap_page(gap), gap.kind, gap.detail), []).append(gap.obligation_id)
    return [
        PageProblem(page, f"{ids[0]} does not compile: {kind}: {detail}")
        if len(ids) == 1
        else PageProblem(page, f"each of {len(ids)} claims on {page} does not compile: {kind}: {detail} The claims: {', '.join(ids)}")
        for (page, kind, detail), ids in by_fix.items()
    ]


def _book_page_paths(root: Path, service: str) -> list[str]:
    folder = book_dir(root, service)
    return sorted(path.relative_to(root).as_posix() for path in folder.rglob("*.md")) if folder.is_dir() else []


def _entries_problems(root: Path, service: str) -> list[PageProblem]:
    if entries_path(root, service).is_file():
        return []
    page = entries_path(root, service).relative_to(root).as_posix()
    return [
        PageProblem(page, f"{page} is missing. Write it with `type: entries` and one `- [title](page.md)` link per entry page.")
    ]


class _Edge(BaseModel):
    model_config = ConfigDict(frozen=True)

    via: str
    to: str | None


class _Node(BaseModel):
    """A node of the book's graph, with only the fields the journey check reads."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: str
    surface: str | None
    parent: str | None
    edges: tuple[_Edge, ...]


_NODES = TypeAdapter(tuple[_Node, ...])


def off_journey_nodes(root: Path, service: str) -> tuple[str, ...]:
    """Every command, endpoint and screen of the service that no flow's walk links, itself or through a part of it."""
    return _off_journey(load(root), service)


def _off_journey(book: Graph, service: str) -> tuple[str, ...]:
    nodes = [node for node in _NODES.validate_python(graph_mod.build(book)["nodes"]) if node.surface == service]
    parents = {node.id: node.parent for node in nodes}
    walked: set[str] = set()
    for flow in (node for node in nodes if node.type == "flow"):
        for edge in flow.edges:
            target = edge.to if edge.via in WALK_BULLETS else None
            while target and target not in walked:
                walked.add(target)
                target = parents.get(target)
    return tuple(node.id for node in nodes if node.type in JOURNEY_TYPES and node.id not in walked)


def _off_journey_problems(book: Graph, service: str) -> list[PageProblem]:
    return [
        PageProblem(
            node.partition("#")[0],
            f"{node} is on no flow. Write a flow under flows/ whose steps link it, or link it from a step of a flow you have.",
        )
        for node in _off_journey(book, service)
    ]


def page_problems(root: Path, service: str) -> tuple[PageProblem, ...]:
    """Every problem on the service's book, each with its page: a missing entries page, a page nothing reaches, a doctor error, a command, endpoint or screen no flow walks, and a claim that does not compile."""
    pages = _book_page_paths(root, service)
    book = load(root)
    dead = [
        PageProblem(page.rel, f"{page.rel} is linked from no page the entries page reaches. Link it, or delete it.")
        for page in dead_pages(book)
        if page.service == service
    ]
    wanted = frozenset(pages)
    gaps = [gap for gap in compile_services(root, (service,)).gaps if gap_page(gap) in wanted and gap_side(gap) is Side.BOOK]
    return (
        *_entries_problems(root, service),
        *dead,
        *_doctor_problems(book, pages),
        *_off_journey_problems(book, service),
        *_gap_problems(gaps),
    )


def book_problems(root: Path, service: str) -> tuple[str, ...]:
    """Every problem on the service's book, as the check prints it."""
    return tuple(problem.text for problem in page_problems(root, service))
