"""What the dev owner's next turn reads: its plan, a gate's failure, its open findings, the rejected answers."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from workhorse import worklist as wl

from workhorse_workflows.coder.shared.schemas.dev import FailureReport
from workhorse_workflows.coder.shared.schemas.dev_story import DevResult


def plan_arg(result: DevResult) -> dict[str, Any]:
    """The structural half of the dev owner's reply, as `record_plan` takes it."""
    return result.model_dump(
        include={
            "services",
            "implementation_order",
            "shared_packages",
            "verification_setup",
            "fixtures",
        }
    )


def report_text(report: FailureReport) -> str:
    """A gate's failure as the markdown the dev owner's next turn reads."""
    lines = [f"Gate: {report.source}"]
    if report.command:
        lines.append(f"Command: `{report.command}`")
    if report.cwd:
        lines.append(f"Directory: `{report.cwd}`")
    lines += [
        f"- `{f.target or '(no target)'}`: {f.issue}" + (f" Repair: {f.repair}" if f.repair else "")
        for f in report.findings
    ]
    if report.output.strip():
        lines += ["", "```", report.output.strip(), "```"]
    return "\n".join(lines)


def findings_text(items: Sequence[wl.WorkItem]) -> str:
    """The finding items a dev turn answers, one section per id."""
    blocks = []
    for it in items:
        blocks.append(
            "\n".join(
                [
                    f"### {it.id}",
                    "",
                    f"- Source: {it.payload.get('source') or ''}",
                    f"- Target: `{it.payload.get('target') or '(no target)'}`",
                    f"- Issue: {it.payload.get('issue') or ''}",
                    f"- Repair: {it.payload.get('repair') or ''}",
                ]
            )
        )
    return "\n\n".join(blocks)


def rejected_text(rejected: dict[str, str], errors: Sequence[str]) -> str:
    """Why the last sign-off pass kept answers open, as the dev owner's next turn reads it."""
    lines = [f"- `{fid}`: {why}" for fid, why in rejected.items()]
    lines += [f"- {err}" for err in errors]
    return "\n".join(lines)


def walk_text(missing: Sequence[int], criteria: int) -> str:
    """The criteria the plan's acceptance walk leaves out, as the dev owner's next turn reads it."""
    named = ", ".join(f"AC {n}" for n in missing)
    return (
        f"Acceptance walk: `## Acceptance Walk` in `plan.md` has no entry for {named} "
        f"of the story's {criteria} criteria.\n\n"
        "Walk each one as the story's user would see it. Add a `### AC <n>: ...` heading "
        "with its `Met by` and `Observed` bullets, and fix the product first where the "
        "criterion does not hold."
    )


def self_check_text(failed: Sequence[dict[str, Any]]) -> str:
    """The scenarios QA failed last pass that still fail on the dev owner's code."""
    lines = [
        "Self-check: these are the scenarios QA failed on its last pass, and they still fail "
        "on your code. Fix the product, then rerun them before you hand off.",
        "",
    ]
    for entry in failed:
        assertions = ", ".join(f"`{a}`" for a in entry["failed_assertions"])
        lines.append(f"- `{entry['id']}`" + (f": failed {assertions}" if assertions else ""))
    return "\n".join(lines)


__all__ = ["findings_text", "plan_arg", "rejected_text", "report_text", "self_check_text", "walk_text"]
