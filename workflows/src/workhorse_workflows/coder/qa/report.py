"""What the QA owner's next turn reads: the failed scenarios, a gate's failure, its own findings."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from workhorse_workflows.coder.shared import qa_support
from workhorse_workflows.coder.shared.scenarios import qa_only_scenarios
from workhorse_workflows.coder.shared.schemas.qa import QaFinding, QaPlanRun, RegressionRun
from workhorse_workflows.kit.qa.schemas import StackStatus


def failed_scenario_ids(result: QaPlanRun) -> tuple[str, ...]:
    """The scenarios a failed run did not pass, sorted; empty for every other status."""
    if result.status != "failed":
        return ()
    scenarios = result.ostler.get("scenarios")
    if not isinstance(scenarios, dict):
        return ()
    return tuple(
        sorted(
            str(name)
            for name, outcome in scenarios.items()
            if isinstance(outcome, dict) and outcome.get("status") != "passed"
        )
    )


def failed_scenarios_arg(spec_dir: str, ids: Sequence[str]) -> list[dict[str, Any]]:
    """Each failed scenario with the assertions it failed, as the owner prompt lists them."""
    if not spec_dir or not ids:
        return []
    failed = qa_support.failed_assertions(qa_support.scored_run_log(Path(spec_dir)))
    return [{"id": sid, "failed_assertions": failed.get(sid, [])} for sid in ids]


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
    "failed_scenario_ids",
    "failed_scenarios_arg",
    "fallback_finding",
    "findings_text",
    "gate_text",
    "qa_only_arg",
    "refix_findings",
    "regression_text",
    "stack_failures",
    "unclassified_failure",
    "unfinished_run",
    "unproved_findings",
]
