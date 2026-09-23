"""The run's account for the operator: what it covered, what it cost per file, what stopped it, and where to start reading.

It also names the pages the run left alone: each page that became reachable after the queue froze,
which no job wrote, and each page nothing reaches that no job owned, which garbage collection kept.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.blockers import Blocker, read_blockers
from workhorse_workflows.okf_book.contracts import read_contracts
from workhorse_workflows.okf_book.entries import entries_path
from workhorse_workflows.okf_book.exercise import RunSummary, read_run
from workhorse_workflows.okf_book.jobs import pages_by_depth, read_queue
from workhorse_workflows.okf_book.metrics import TurnMetric, read_metrics
from workhorse_workflows.okf_book.page_check import dead_book_pages
from workhorse_workflows.okf_book.production import entry_pages
from workhorse_workflows.okf_book.work_set import WorkSet

REPORT_NAME = "report.json"
REPORT_PAGE = "report.md"
_CONCEPTS = "concepts"


class FileCost(BaseModel):
    """What one file or page cost: its share of every turn that worked on it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    tokens: int
    minutes: float
    turns: int


class BookReport(BaseModel):
    """Everything the operator reads once the run stops."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    services: tuple[str, ...]
    file_count: int
    pruned_count: int
    contract_count: int
    unqueued: tuple[str, ...]
    orphans: tuple[str, ...]
    tokens: int
    minutes: float
    costs: tuple[FileCost, ...]
    blockers: tuple[Blocker, ...]
    run: RunSummary | None
    reading: tuple[str, ...]


def file_costs(metrics: tuple[TurnMetric, ...]) -> tuple[FileCost, ...]:
    """Each subject's even share of the turns that named it, dearest first."""
    tokens: defaultdict[str, float] = defaultdict(float)
    minutes: defaultdict[str, float] = defaultdict(float)
    turns: defaultdict[str, int] = defaultdict(int)
    for metric in metrics:
        share = max(len(metric.subjects), 1)
        for subject in metric.subjects:
            tokens[subject] += metric.tokens / share
            minutes[subject] += metric.minutes / share
            turns[subject] += 1
    costs = (
        FileCost(subject=s, tokens=round(tokens[s]), minutes=round(minutes[s], 2), turns=turns[s]) for s in turns
    )
    return tuple(sorted(costs, key=lambda c: (-c.tokens, c.subject)))


def _rel(root: Path, page: Path) -> str:
    return page.resolve().relative_to(root.resolve()).as_posix()


def reading_list(root: Path, services: tuple[str, ...]) -> tuple[str, ...]:
    """Where a reader starts: each entries page, its entry pages, then its concepts."""
    found: list[str] = []
    for service in services:
        entries = entries_path(root, service)
        if entries.is_file():
            found.append(_rel(root, entries))
        found.extend(_rel(root, page) for page in entry_pages(root, service))
        found.extend(page for page in pages_by_depth(root, service) if f"/{_CONCEPTS}/" in page)
    return tuple(dict.fromkeys(found))


def unqueued_pages(root: Path, run_dir: Path, services: tuple[str, ...]) -> tuple[str, ...]:
    """Each page in the book when the queue froze, reachable now, that no queued job owned."""
    queue = read_queue(run_dir)
    if queue is None:
        return ()
    present = frozenset(queue.present_pages)
    reachable = (page for service in services for page in pages_by_depth(root, service))
    return tuple(page for page in reachable if page in present and page not in queue.frozen_pages)


def orphan_pages(root: Path, services: tuple[str, ...]) -> tuple[str, ...]:
    """Each page of the services that nothing reaches, which the run did not delete."""
    return tuple(sorted(page.rel for page in dead_book_pages(root) if page.service in services))


def build_report(root: Path, run_dir: Path, work_set: WorkSet) -> BookReport:
    metrics = read_metrics(run_dir)
    return BookReport(
        services=work_set.services,
        file_count=len(work_set.files),
        pruned_count=len(work_set.pruned),
        contract_count=len(read_contracts(run_dir, work_set.files)),
        unqueued=unqueued_pages(root, run_dir, work_set.services),
        orphans=orphan_pages(root, work_set.services),
        tokens=sum(m.tokens for m in metrics),
        minutes=round(sum(m.minutes for m in metrics), 2),
        costs=file_costs(metrics),
        blockers=read_blockers(run_dir),
        run=read_run(run_dir),
        reading=reading_list(root, work_set.services),
    )


def _blocker_lines(report: BookReport) -> list[str]:
    if not report.blockers:
        return ["Nothing blocked the run."]
    return [f"- {b.phase.value} / {b.side.value}: `{b.subject}`: {b.reason}" for b in report.blockers]


def _run_lines(report: BookReport) -> list[str]:
    if report.run is None:
        return ["No scenario ran."]
    lines = [f"Status: {report.run.status}."]
    lines.extend(f"- `{name}`: {outcome.status}" for name, outcome in sorted(report.run.scenarios.items()))
    lines.extend(f"- {problem}" for problem in report.run.problems)
    return lines


def _left_alone_lines(report: BookReport) -> list[str]:
    lines = [f"- `{page}`: reachable only after the queue froze, so no job wrote it" for page in report.unqueued]
    lines.extend(f"- `{page}`: nothing reaches it, and no job owned it" for page in report.orphans)
    return lines or ["None."]


def render_report(report: BookReport) -> str:
    """The report as a page an operator reads top to bottom."""
    lines = [
        "# okf book run",
        "",
        f"Services: {', '.join(report.services)}.",
        f"{report.file_count} files documented, {report.pruned_count} pruned, {report.contract_count} contracts.",
        f"{report.tokens} tokens packed into turns over {report.minutes} minutes.",
        "",
        "## Pages the run left alone",
        "",
        *_left_alone_lines(report),
        "",
        "## Blockers",
        "",
        *_blocker_lines(report),
        "",
        "## Scenarios",
        "",
        *_run_lines(report),
        "",
        "## Start reading here",
        "",
        *(f"- `{page}`" for page in report.reading),
        "",
        "## Cost per file",
        "",
        *(f"- `{c.subject}`: {c.tokens} tokens, {c.minutes} min, {c.turns} turns" for c in report.costs),
    ]
    return "\n".join(lines) + "\n"


def write_report(run_dir: Path, report: BookReport) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    _ = (run_dir / REPORT_NAME).write_text(report.model_dump_json(indent=2), encoding="utf-8")
    page = run_dir / REPORT_PAGE
    _ = page.write_text(render_report(report), encoding="utf-8")
    return page


def read_report(run_dir: Path) -> BookReport:
    return BookReport.model_validate_json((run_dir / REPORT_NAME).read_text(encoding="utf-8"))
