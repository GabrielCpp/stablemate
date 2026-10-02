"""The check the writer runs on its whole book, and the run repeats after it.

Nothing here changes a page. It reports a missing entries page, every page nothing the entries
page reaches, and every doctor error on the book, except a stale citation, which the commit
restamps. So is a bullet the page's type does not declare, which doctor only warns about because
a hand-kept book may carry one, but which on a written page is a claim nothing runs. It reports
every command, endpoint and screen no flow walks, every cli page that names no binary or one the
repository opts into no QA tool, and every obligation that does not compile, unless the gap is one ostler cannot run yet, which is
ostler's to fix and not the book's. A claim observed out of band is the book's: no run observes it, so the writer
restates it as what a caller sees, or drops it.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import AliasPath, BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, field_validator

from ostler import doctor
from ostler import graph as graph_mod
from ostler import index
from ostler.book_reach import DeadPage, dead_pages
from ostler.model import Graph, load
from ostler.pages import files_in_book
from ostler.qa.compile import HARNESS_LIMIT_GAPS
from ostler.qa.plan_source import Gap
from ostler.qa.runbook import bullet_text
from ostler.qa.tools import opted_in_tools
from workhorse_workflows.okf_book.shared.blockers import Side
from workhorse_workflows.okf_book.shared.book_compilation import compile_services, gap_page, obligation_node
from workhorse_workflows.okf_book.shared.entries import book_dir, entries_path

OSTLER_GAPS = HARNESS_LIMIT_GAPS | frozenset({"needs-snapshot"})
RESTAMPED_CODES = frozenset({"stale-citation"})
REACH_CODES = frozenset({"unreachable-node"})
CHARGED_WARNINGS = frozenset({"unknown-bullet"})
JOURNEY_TYPES = frozenset({"command", "endpoint", "screen"})
WALK_BULLETS = frozenset({"start", "steps", "end"})
WRITER_FIXES = {
    "needs-out-of-band-observation": (
        "No run observes this. State what a caller of the surface sees instead: a status, a body "
        "field, a response header, or a later read that returns what was stored. Delete the claim "
        "when nothing outside the app shows it."
    ),
    "unarrangeable-server-fault": (
        "No request makes a healthy app answer a 5xx. Say in the section's prose that the route "
        "fails when a dependency does, and delete the bullet and its `verify:`."
    ),
}


def gap_side(gap: Gap) -> Side:
    """Ostler's, when the harness cannot observe what the book states. The book's otherwise."""
    return Side.OSTLER if gap.kind in OSTLER_GAPS else Side.BOOK


def dead_book_pages(root: Path) -> tuple[DeadPage, ...]:
    """Every page no link path from its service's entries page reaches."""
    return tuple(dead_pages(load(root)))


@dataclass(frozen=True, slots=True)
class PageProblem:
    """One problem the check reports, the repo-relative page it sits on, and whether its fix goes on a flow or an entry page.

    A problem at one line of the page names it, and a problem on one node of the page names the
    node, `page#anchor`. A problem with what the page arranges names the pages whose requests failed
    on it, since the fix may be the request.
    """

    page: str
    text: str
    needs_journey: bool = False
    line: int | None = None
    node: str = ""
    requests: tuple[str, ...] = ()

    def text_ignoring_line(self) -> str:
        """The problem's text with its line number left out, since an edit above the problem moves it."""
        return self.text if self.line is None else f"{self.page}: " + self.text.removeprefix(f"{self.page}:{self.line}: ")


def _doctor_problems(book: Graph, pages: list[str]) -> list[PageProblem]:
    if not pages:
        return []
    report = doctor.scope_to_paths(doctor.run(book), pages)
    return [
        PageProblem(
            f.path, f"{f.path}:{f.line}: {f.code}: {f.message}" + (f" {f.suggestion}" if f.suggestion else ""), line=f.line
        )
        for f in report.findings
        if (f.severity == "error" or f.code in CHARGED_WARNINGS) and f.code not in RESTAMPED_CODES | REACH_CODES
    ]


def gap_problems(gaps: Iterable[Gap]) -> list[PageProblem]:
    """One problem per node, kind and fix of the gaps, so a problem names the claims of one node that one fix mends."""
    by_fix: dict[tuple[str, str, str], list[str]] = {}
    for gap in gaps:
        detail = WRITER_FIXES.get(gap.kind, gap.detail)
        by_fix.setdefault((obligation_node(gap.obligation_id), gap.kind, detail), []).append(gap.obligation_id)
    return [
        PageProblem(node.partition("#")[0], f"{ids[0]} does not compile: {kind}: {detail}", node=node)
        if len(ids) == 1
        else PageProblem(
            node.partition("#")[0],
            f"each of {len(ids)} claims on {node} does not compile: {kind}: {detail} The claims: {', '.join(ids)}",
            node=node,
        )
        for (node, kind, detail), ids in by_fix.items()
    ]


def _book_page_paths(root: Path, service: str) -> list[str]:
    folder = book_dir(root, service)
    return sorted(path.relative_to(root).as_posix() for path in files_in_book(folder)) if folder.is_dir() else []


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
    binary: str = Field(default="", validation_alias=AliasPath("bullets", "binary"))

    @field_validator("binary", mode="before")
    @classmethod
    def _first_binary(cls, value: JsonValue) -> str:
        first = value[0] if isinstance(value, list) and value else value
        return bullet_text(first) if isinstance(first, str) else ""


_NODES = TypeAdapter(tuple[_Node, ...])


def _service_nodes(book: Graph, service: str) -> list[_Node]:
    return [node for node in _NODES.validate_python(graph_mod.build(book)["nodes"]) if node.surface == service]


def off_journey_nodes(root: Path, service: str) -> tuple[str, ...]:
    """Every command, endpoint and screen of the service that no flow's walk links, itself or through a part of it."""
    return _off_journey_node_ids(_service_nodes(load(root), service))


def _off_journey_node_ids(nodes: list[_Node]) -> tuple[str, ...]:
    parents = {node.id: node.parent for node in nodes}
    walked: set[str] = set()
    for flow in (node for node in nodes if node.type == "flow"):
        for edge in flow.edges:
            target = edge.to if edge.via in WALK_BULLETS else None
            while target and target not in walked:
                walked.add(target)
                target = parents.get(target)
    return tuple(node.id for node in nodes if node.type in JOURNEY_TYPES and node.id not in walked)


def _off_journey_problems(nodes: list[_Node]) -> list[PageProblem]:
    return [
        PageProblem(
            node.partition("#")[0],
            f"{node} is on no flow. Write a flow under flows/ whose steps link it, or link it from a step of a flow you have.",
            needs_journey=True,
            node=node,
        )
        for node in _off_journey_node_ids(nodes)
    ]


def _uninvokable_problems(root: Path, nodes: list[_Node]) -> list[PageProblem]:
    tools = opted_in_tools(root)
    return [
        PageProblem(
            node.id,
            (
                f"{node.id}: no run can invoke `{node.binary}`, because this repository opts no QA tool of that name in. "
                if node.binary
                else f"{node.id}: no run can invoke it, because it names no `binary:`. "
            )
            + "When the app itself runs it, delete the page and every page under it, point each link to them at the page "
            + "of what calls it, and state there what running it changes, with claims that prove it. Do not scaffold it "
            + "again. When a user runs it, `binary:` names the program, and the operator opts that tool in.",
        )
        for node in nodes
        if node.type == "cli" and node.binary not in tools
    ]


def page_problems(root: Path, service: str) -> tuple[PageProblem, ...]:
    """Every problem on the service's book, each with its page: a missing entries page, a page nothing reaches, a doctor error, a command, endpoint or screen no flow walks, a command no run can invoke, and a claim that does not compile."""
    with index.session(root):
        pages = _book_page_paths(root, service)
        book = load(root)
        nodes = _service_nodes(book, service)
        dead = [
            PageProblem(
                page.rel,
                f"{page.rel} is linked from no page the entries page reaches. Link it, or delete it.",
                needs_journey=True,
            )
            for page in dead_pages(book)
            if page.service == service
        ]
        wanted = frozenset(pages)
        gaps = [gap for gap in compile_services(root, (service,)).gaps if gap_page(gap) in wanted and gap_side(gap) is Side.BOOK]
        return (
            *_entries_problems(root, service),
            *dead,
            *_doctor_problems(book, pages),
            *_off_journey_problems(nodes),
            *_uninvokable_problems(root, nodes),
            *gap_problems(gaps),
        )


def book_problems(root: Path, service: str) -> tuple[str, ...]:
    """Every problem on the service's book, as the check prints it."""
    return tuple(problem.text for problem in page_problems(root, service))
