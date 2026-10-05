"""What the book's owner is shown of the gates it last failed, and what its reply names of them.

The owner holds the whole book. Code runs the gates between its turns: the page check and the run
against the app. The owner's next turn opens on their results, every failure grouped by what was
observed, and its reply names the side of each group. A group named another side's is held back
from the book's failures on every later lap, and is a blocker on that side.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from workhorse_workflows.okf_book.main.nodes.check_lead import NODES_SHOWN, SAMPLES_SHOWN, check_findings, check_groups, next_check_lap, write_check_problems
from workhorse_workflows.okf_book.main.nodes.gate import RunFailures
from workhorse_workflows.okf_book.main.nodes.lead_findings import (
    LEAD_SIDES,
    LINES_SHOWN,
    LeadFinding,
    LeadVerdict,
    OwnerReply,
    lead_findings,
    lead_groups,
    read_findings,
    record_findings,
)
from workhorse_workflows.okf_book.main.nodes.operator_answer import read_answer
from workhorse_workflows.okf_book.main.nodes.progress_ledger import read_laps, service_laps
from workhorse_workflows.okf_book.main.nodes.source_view import kept_for_turn, turn_folder
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.shared.scenarios import PLAN_NAME, RUN_NAME, spec_dir

OWNER_FOLDER = "owner"
FAILURES_NAME = "run-failures.txt"


@dataclass(frozen=True)
class Gates:
    """What the gates last measured of one book: the run against the app, the page check, and each run failure the book can fix after its page."""

    exercised: ExerciseResult | None = None
    problems: tuple[PageProblem, ...] = ()
    failures: RunFailures = field(default_factory=dict)


def write_run_failures(folder: Path, failures: RunFailures) -> Path:
    """Write each failure the run mapped to a page, one per line after its page, where the owner reads it."""
    path = folder / FAILURES_NAME
    _ = path.write_text("".join(f"{page}\t{problem.text}\n" for page, problems in failures.items() for problem in problems), encoding="utf-8")
    return path


def _run_groups(exercised: ExerciseResult | None) -> list[dict[str, object]]:
    if exercised is None:
        return []
    summary = exercised.summary
    return [
        {"number": number, "text": signature.text(), "cause": signature.cause.value, "count": signature.count, "sample": signature.sample,
         "pages": list(summary.signature_pages(signature)) if summary is not None else []}
        for number, signature in enumerate(lead_groups(exercised), start=1)
    ]


def _check_groups(problems: Iterable[PageProblem]) -> list[dict[str, object]]:
    return [
        {"number": number, "code": group.code, "count": len(group.problems),
         "samples": [problem.text for problem in group.problems[:SAMPLES_SHOWN]],
         "pages": list(group.pages), "nodes": list(group.nodes[:NODES_SHOWN]), "nodes_left": max(0, len(group.nodes) - NODES_SHOWN)}
        for number, group in enumerate(check_groups(problems), start=1)
    ]


def gate_template_args(root: Path, records_dir: Path, service: str, gates: Gates) -> dict[str, object]:
    """The gate results the owner's turn opens on: the run's groups and the head of what it printed, the check's groups, where every failure is kept, what the owner named on earlier laps, and the operator's last answer while this owner has not replied after reading it."""
    exercised, problems, failures = gates.exercised, gates.problems, gates.failures
    folder = turn_folder(root, OWNER_FOLDER)
    summary, plan = kept_for_turn(root, OWNER_FOLDER, (records_dir / RUN_NAME, spec_dir(records_dir) / service / PLAN_NAME))
    lines = list(exercised.lines[:LINES_SHOWN]) if exercised is not None else []
    return {
        "run_groups": _run_groups(exercised),
        "run_lines": lines,
        "run_lines_left": max(0, len(exercised.lines) - LINES_SHOWN) if exercised is not None else 0,
        "run_summary": str(summary),
        "run_plan": str(plan),
        "run_failures": str(write_run_failures(folder, failures)) if failures else "",
        "check_groups": _check_groups(problems),
        "check_problems": str(write_check_problems(folder, problems)) if problems else "",
        "sides": sorted(LEAD_SIDES),
        "earlier": [finding.model_dump(mode="json") for finding in read_findings(records_dir) if finding.service == service],
        "operator_answer": read_answer(records_dir, service),
    }


def record_owner_reply(records_dir: Path, service: str, gates: Gates, reply: OwnerReply) -> tuple[LeadFinding, ...]:
    """Record what the owner named of each group it was shown, so the gates hold back what it named another side's, and return it."""
    exercised, problems = gates.exercised, gates.problems
    run = (lead_findings(service, len(service_laps(read_laps(records_dir), service)), exercised, LeadVerdict(findings=reply.run))
           if exercised is not None and reply.run else ())
    check = (check_findings(service, next_check_lap(read_findings(records_dir), service), problems, LeadVerdict(findings=reply.check))
             if problems and reply.check else ())
    findings = (*run, *check)
    record_findings(records_dir, findings)
    return findings
