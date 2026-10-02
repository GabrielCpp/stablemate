"""The run's account for the operator: what it covered, what each book cost, what stopped it, how each lap went, and where to start reading.

It also names each page of the run's books that nothing reaches, which the run did not delete.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from ostler.pages import files_in_book
from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.main.nodes.progress_ledger import LapCounts, read_laps, service_laps, trend
from workhorse_workflows.okf_book.shared.blockers import Blocker, read_blockers
from workhorse_workflows.okf_book.shared.entries import book_dir, entries_path
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, read_metrics
from workhorse_workflows.okf_book.shared.page_check import dead_book_pages
from workhorse_workflows.okf_book.shared.production import entry_pages
from workhorse_workflows.okf_book.shared.scenarios import RunSummary, read_run

REPORT_NAME = "report.json"
REPORT_PAGE = "report.md"
_CONCEPTS = "concepts"


class BookCost(BaseModel):
    """What one book cost: its share of every turn that wrote it. Its dollars are unknown when no turn reported any."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    minutes: float
    turns: int
    tokens_read: int = 0
    tokens_generated: int = 0
    dollars: float | None = None


class BookReport(BaseModel):
    """Everything the operator reads once the run stops."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    services: tuple[str, ...]
    orphans: tuple[str, ...]
    minutes: float
    dollars: float | None = None
    costs: tuple[BookCost, ...]
    blockers: tuple[Blocker, ...]
    run: RunSummary | None
    reading: tuple[str, ...]
    laps: tuple[LapCounts, ...] = ()


def _dollars(shares: Iterable[tuple[TurnMetric, int]]) -> float | None:
    reported = [m.dollars / share for m, share in shares if m.dollars is not None]
    return round(sum(reported), 2) if reported else None


def book_costs(metrics: tuple[TurnMetric, ...]) -> tuple[BookCost, ...]:
    """Each book's even share of the turns that named it, dearest first."""
    by_subject: defaultdict[str, list[tuple[TurnMetric, int]]] = defaultdict(list)
    for metric in metrics:
        for subject in metric.subjects:
            by_subject[subject].append((metric, len(metric.subjects)))
    costs = (
        BookCost(
            subject=subject,
            minutes=round(sum(m.minutes / share for m, share in shares), 2),
            turns=len(shares),
            tokens_read=sum(m.tokens_read // share for m, share in shares),
            tokens_generated=sum(m.tokens_generated // share for m, share in shares),
            dollars=_dollars(shares),
        )
        for subject, shares in by_subject.items()
    )
    return tuple(sorted(costs, key=lambda c: (-c.minutes, c.subject)))


def _rel(root: Path, page: Path) -> str:
    return page.resolve().relative_to(root.resolve()).as_posix()


def _concept_pages(root: Path, service: str) -> list[str]:
    folder = book_dir(root, service)
    if not folder.is_dir():
        return []
    return sorted(rel for rel in (_rel(root, page) for page in files_in_book(folder)) if f"/{_CONCEPTS}/" in rel)


def reading_list(root: Path, services: tuple[str, ...]) -> tuple[str, ...]:
    """Where a reader starts: each entries page, its entry pages, then its concepts."""
    found: list[str] = []
    for service in services:
        entries = entries_path(root, service)
        if entries.is_file():
            found.append(_rel(root, entries))
        found.extend(_rel(root, page) for page in entry_pages(root, service))
        found.extend(_concept_pages(root, service))
    return tuple(dict.fromkeys(found))


def orphan_pages(root: Path, services: tuple[str, ...]) -> tuple[str, ...]:
    """Each page of the services that nothing reaches, which the run did not delete."""
    return tuple(sorted(page.rel for page in dead_book_pages(root) if page.service in services))


def build_report(root: Path, records_dir: Path, services: tuple[str, ...]) -> BookReport:
    metrics = read_metrics(records_dir)
    return BookReport(
        services=services,
        orphans=orphan_pages(root, services),
        minutes=round(sum(m.minutes for m in metrics), 2),
        dollars=_dollars((m, 1) for m in metrics),
        costs=book_costs(metrics),
        blockers=read_blockers(records_dir),
        run=read_run(records_dir),
        reading=reading_list(root, services),
        laps=read_laps(records_dir),
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


def _gap_lines(report: BookReport) -> list[str]:
    gaps = report.run.gaps if report.run is not None else {}
    return [f"- `{claim}`: gapped: {gap} absent" for claim, gap in gaps.items()] or ["None."]


def _lap_lines(report: BookReport) -> list[str]:
    lines: list[str] = []
    for service in report.services:
        laps = service_laps(report.laps, service)
        if laps:
            lines.append(f"- `{service}`: the book's failed checks, lap by lap: {trend(laps)}")
            lines.extend(f"  - lap {number}: {lap.text()}" for number, lap in enumerate(laps, start=1))
    return lines or ["No lap ran."]


def _money(dollars: float | None) -> str:
    return "dollars not reported" if dollars is None else f"${dollars:.2f}"


def render_report(report: BookReport) -> str:
    """The report as a page an operator reads top to bottom."""
    lines = [
        "# okf book run",
        "",
        f"Services: {', '.join(report.services)}.",
        f"{report.minutes} minutes of writing, {_money(report.dollars)}.",
        "",
        "## Pages nothing reaches",
        "",
        *([f"- `{page}`" for page in report.orphans] or ["None."]),
        "",
        "## Blockers",
        "",
        *_blocker_lines(report),
        "",
        "## Scenarios",
        "",
        *_run_lines(report),
        "",
        "## Gapped claims",
        "",
        *_gap_lines(report),
        "",
        "## Progress per lap",
        "",
        *_lap_lines(report),
        "",
        "## Start reading here",
        "",
        *(f"- `{page}`" for page in report.reading),
        "",
        "## Cost per book",
        "",
        *(
            f"- `{c.subject}`: {c.minutes} min, {c.turns} turns, {c.tokens_read} tokens read, "
            + f"{c.tokens_generated} generated, {_money(c.dollars)}"
            for c in report.costs
        ),
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
