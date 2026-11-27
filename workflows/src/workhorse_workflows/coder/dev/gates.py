"""The first failing check of a dev lap: the story's status line, a copy the story added, then each service gate."""
from __future__ import annotations

from workhorse.pyflow import Workflow

from workhorse_workflows.coder.shared.clones import check_copies
from workhorse_workflows.coder.shared.dev import check_story_status
from workhorse_workflows.coder.shared.failure import from_findings, from_gate
from workhorse_workflows.coder.shared.plan import resolve_impl_context
from workhorse_workflows.coder.shared.reach import resolve_check_set
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import FailureReport, GateOutcome
from workhorse_workflows.coder.shared.service_gates import GATE_ORDER, run_gate


def first_failure(flow: Workflow, lap: int) -> FailureReport | None:
    stamped = flow.call(
        check_story_status,
        flow.ctx.story_slug,
        epic=flow.ctx.story_epic,
        story_path=flow.ctx.story_path,
    )
    impl = flow.output(resolve_impl_context)
    if stamped.status == "dirty":
        return from_findings(
            "story status",
            [
                Finding(
                    target=flow.ctx.story_path,
                    issue=(
                        f"the story's Status reads '{stamped.written}', which marks it "
                        "finished. The run reads that line to pick work, so the story "
                        "drops out of every later pass and out of QA."
                    ),
                    repair=(
                        "put the Status line back to the value it held before this "
                        "story's work. `git diff` on the story file shows it. Record "
                        "what you ran as prose under `## Implementation Status` instead. "
                        "The run stamps the outcome itself, from a QA run it performed."
                    ),
                )
            ],
            flow.ctx.story_path,
            lap,
        )
    copies = flow.call(
        check_copies,
        [entry.cwd for entry in impl.dispatch_list if entry.type != "docs"],
        story_slug=flow.ctx.story_slug,
        story_id=flow.ctx.story_id,
    )
    if copies.findings:
        return from_findings("copies", copies.findings, copies.cwd, lap)
    checks = flow.call(
        resolve_check_set,
        tuple(impl.dispatch_list),
        flow.ctx.story_slug,
        flow.ctx.story_id,
    )
    for entry in checks.checks:
        outcome = GateOutcome()
        for gate in GATE_ORDER:
            outcome = flow.call(
                run_gate, entry.cwd, entry.service, gate, service_type=entry.type
            )
            if outcome.status == "dirty":
                return from_gate(outcome, entry.cwd, lap)
    return None
