"""What the dev owner's next turn reads: its plan, a gate's failure, its open findings, the rejected answers."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from workhorse import worklist as wl

from workhorse_workflows.coder.shared.schemas.dev import FailureReport
from workhorse_workflows.coder.shared.schemas.dev_story import Departure, DevResult


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
        "on your code. Fix the product and cover the case with a test in the service. The "
        "workflow reruns these scenarios against your code when you hand off. Do not raise a "
        "QA stack or run the QA plan yourself: a hand run writes over QA's scored evidence.",
        "",
    ]
    for entry in failed:
        assertions = ", ".join(f"`{a}`" for a in entry["failed_assertions"])
        lines.append(f"- `{entry['id']}`" + (f": failed {assertions}" if assertions else ""))
    return "\n".join(lines)


def unadvised_text(departures: Sequence[Departure]) -> str:
    """The plan departures that carry no advisor answer, as the build's next turn reads them."""
    lines = [
        "Departures: the brief asks for the advisor's answer on every departure from the plan, "
        "and these carry none. Ask it now, and record its answer in `advice`.",
        "",
    ]
    lines += [f"- {d.change}" for d in departures]
    return "\n".join(lines)


def unconsulted_text(ids: Sequence[str]) -> str:
    """The declined findings that no advisor consult backs, as the review's next turn reads them."""
    named = ", ".join(f"`{fid}`" for fid in ids)
    return (
        f"Consults: the answer file declines {named}, and no advisor answer is on file for "
        "them. The review brief asks for the advisor's answer before any decline. Ask it now, "
        "record it in `consults`, then keep or change the answer."
    )


__all__ = ["findings_text", "plan_arg", "rejected_text", "report_text", "self_check_text", "unadvised_text", "unconsulted_text", "walk_text"]
