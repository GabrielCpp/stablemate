"""What the QA owner's next turn reads: the failed scenarios, a gate's failure, its own findings."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ostler.qa.attribution import SAMPLE_CHARS

from workhorse_workflows.coder.qa.sides import FailedScenario
from workhorse_workflows.coder.shared.failed import failed_scenario_ids, failed_scenarios_arg
from workhorse_workflows.coder.shared.scenarios import qa_only_scenarios
from workhorse_workflows.coder.shared.schemas.qa import QaFinding, QaPlanRun, RegressionRun
from workhorse_workflows.kit.qa.schemas import StackStatus


def unfinished_run(run: QaPlanRun) -> str:
    """A scored run that neither passed nor failed, with every problem it named."""
    problems = run.ostler.get("problems")
    listed = [str(p) for p in problems] if isinstance(problems, list) else []
    detail = "\n".join([run.notes.strip(), *(f"- {p}" for p in listed)]).strip()
    return gate_text(f"the scored run ({run.status})", detail)


def gate_text(gate: str, notes: str) -> str:
    """One failed check, as the owner's next turn reads it."""
    return f"Check: {gate}\n\n{notes.strip() or 'the check reported no detail.'}"


def qa_only_arg(spec_dir: str) -> list[dict[str, Any]]:
    """The plan's QA-only scenarios, as the owner prompt lists them."""
    return [
        {"title": s.title, "ac": s.ac, "level": s.level}
        for s in qa_only_scenarios(Path(spec_dir), "")
    ]


def stack_failures(stack: StackStatus) -> list[str]:
    """The QA stack as a failure the owner repairs; empty when it serves or is not needed."""
    if stack.ready == "none":
        reason = "The book serves a surface but declares no stack runbook."
    elif stack.ready == "no":
        reason = f"The stack did not come up at step `{stack.failed_step}`."
    else:
        return []
    return [gate_text("the QA stack", f"{reason}\n\n{stack.notes}")]


def unclassified_failure(run: QaPlanRun, ids: Sequence[str]) -> str:
    """A failed scored run the owner returned no finding for."""
    return gate_text(
        "the scored run",
        f"{run.notes}\n\nThe scored run failed on {', '.join(ids) or 'some scenarios'}, "
        "and your turn returned no finding. Classify each failure: repair the plan, the "
        "stack or the scenario when the cause is there, or return it as a finding when the "
        "product is wrong.",
    )


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= SAMPLE_CHARS else f"{text[:SAMPLE_CHARS]}..."


def scenario_text(scenario: FailedScenario) -> str:
    """One failed scenario with each check that failed in it and the page ostler blames."""
    lines = [f"- `{scenario.id}` ({scenario.cause.value})"]
    for check in scenario.checks:
        label = str(check.get("label", "")).strip() or "a check"
        expected = _clip(str(check.get("expected", "")))
        line = f"  - {label}: expected {expected}, saw {_clip(str(check.get('actual', '')))}"
        ending = _clip(str(check.get("command_ending_text", "")))
        page = str(check.get("precondition", "")).strip()
        line += f"; {ending}" if ending else ""
        lines.append(line + (f" (page: `{page}`)" if page else ""))
    return "\n".join(lines)


def environment_failure(run: QaPlanRun, scenarios: Sequence[FailedScenario]) -> str:
    """Failed scenarios whose fixture step could not start, which only the operator can fix."""
    listed = "\n".join(scenario_text(s) for s in scenarios)
    return gate_text(
        "the QA environment",
        f"{run.notes}\n\nA fixture step could not start, so the stack lacks something the "
        f"book needs and neither the book nor the product was tested:\n{listed}\n\n"
        "Make the environment provide it, then answer this gate so QA reruns.",
    )


def book_failure(scenarios: Sequence[FailedScenario]) -> str:
    """Failed scenarios that never reached their claim, which the owner repairs in the book."""
    listed = "\n".join(scenario_text(s) for s in scenarios)
    return gate_text(
        "the book",
        f"These scenarios failed before their claim was tested: a fixture step failed, or "
        f"the claim's condition read back false. The product was not tested, so they are "
        f"not findings:\n{listed}\n\nRepair the page ostler names so its fixture builds the "
        "world the claim needs, then rerun them.",
    )


def product_findings(scenarios: Sequence[FailedScenario]) -> list[QaFinding]:
    """Failed scenarios whose condition held and whose claim failed, as findings for dev."""
    return [
        QaFinding(
            id=s.id,
            target=s.id,
            issue=scenario_text(s),
            repair=f"make the product hold what scenario `{s.id}` claims, then rerun it",
        )
        for s in scenarios
    ]


def unproved_findings(findings: Sequence[QaFinding]) -> str:
    """Findings the owner returned beside a passing run."""
    return gate_text(
        "unproved findings",
        f"The scored run passed, yet your turn returned these findings:\n"
        f"{findings_text(findings)}\n\nA finding stands only when a scenario fails on it. "
        "Make a scenario assert the defect, or drop the finding.",
    )


def regression_text(run: RegressionRun) -> str:
    """A failed regression run, with the tests that failed and where its log lives."""
    lines = [run.notes.strip() or f"the regression suites ended `{run.status}`."]
    if run.failing_tests:
        lines.append("Failing tests: " + ", ".join(f"`{t}`" for t in run.failing_tests))
    if run.log_path:
        lines.append(f"Log: `{run.log_path}`")
    return gate_text(f"regression suites ({run.status})", "\n".join(lines))


def findings_text(findings: Sequence[QaFinding]) -> str:
    """The product findings the owner returned, one line each."""
    return "\n".join(
        f"- `{f.id or f.target or '(no target)'}`: {f.issue}"
        + (f" Repair: {f.repair}" if f.repair else "")
        for f in findings
    )


def fallback_finding(qa_dir: str, notes: str) -> QaFinding:
    """The one finding a failed verdict carries when the owner named none."""
    return QaFinding(
        id="qa-run",
        target=qa_dir,
        issue=notes.strip() or "the QA run did not pass the story",
        repair=(
            "make the product meet every acceptance criterion the QA run exercised, "
            "then rerun the scenarios that failed"
        ),
    )


def refix_findings(findings: Sequence[QaFinding], qa_dir: str, notes: str) -> list[QaFinding]:
    """The owner's findings, or the fallback when it returned none."""
    return list(findings) or [fallback_finding(qa_dir, notes)]


__all__ = [
    "book_failure",
    "environment_failure",
    "failed_scenario_ids",
    "failed_scenarios_arg",
    "fallback_finding",
    "findings_text",
    "gate_text",
    "product_findings",
    "qa_only_arg",
    "refix_findings",
    "regression_text",
    "scenario_text",
    "stack_failures",
    "unclassified_failure",
    "unfinished_run",
    "unproved_findings",
]
