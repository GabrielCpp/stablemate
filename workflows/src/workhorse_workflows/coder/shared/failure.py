"""Turning whatever a gate returned into the one shape the repair role reads."""
from __future__ import annotations

from collections.abc import Sequence

from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import FailureReport, GateOutcome

MAX_OUTPUT = 12_000


def _clip(output: str) -> str:
    """The tail of `output`, bounded."""
    text = output.strip()
    if len(text) <= MAX_OUTPUT:
        return text
    return "…[earlier output trimmed]…\n" + text[-MAX_OUTPUT:]


def from_gate(outcome: GateOutcome, cwd: str, lap: int) -> FailureReport:
    """A declared gate's `dirty` verdict as a failure the repair role can act on."""
    return FailureReport(
        source=outcome.gate or "gate",
        command=outcome.command,
        cwd=cwd,
        output=_clip(outcome.output),
        lap=lap,
    )


def from_command(
    source: str, command: str, cwd: str, output: str, lap: int
) -> FailureReport:
    """Any gate that is a command and an exit code — verification, regression, a repo's own."""
    return FailureReport(
        source=source, command=command, cwd=cwd, output=_clip(output), lap=lap
    )


def from_findings(
    source: str, findings: Sequence[Finding], cwd: str, lap: int, output: str = ""
) -> FailureReport:
    """A gate whose verdict is already structured — a review's or QA's hand-off."""
    return FailureReport(
        source=source,
        cwd=cwd,
        output=_clip(output),
        findings=list(findings),
        lap=lap,
    )


__all__ = ["MAX_OUTPUT", "from_command", "from_findings", "from_gate"]
