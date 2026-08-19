"""Turning whatever a gate returned into the one shape the repair role reads.

There is one repair turn in the dev lane, and this module is why it can be one. Each gate
reports in its own vocabulary — `LintOutcome` has `status`/`command`/`output`, a review
hands over `Finding`s, a future check may hand over a process exit and nothing else — and
each of those used to justify its own result schema, its own prompt and its own budget.
They differ in a word, and the word is `source`.

These are plain functions rather than nodes: they compute nothing that could fail, touch no
filesystem and take no logger. A `FailureReport` is built at the site that already holds the
gate's return, in the same state, and its correctness is the adapter's, not an agent's.
"""
from __future__ import annotations

from collections.abc import Sequence

from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import FailureReport, LintOutcome

#: How much of a gate's output the repair turn is handed. A lint run over a large service
#: can print thousands of lines, and past this the turn is reading the same class of error
#: repeatedly rather than learning anything more about it — it re-runs the command itself as
#: its first act anyway, which is the unbounded copy.
MAX_OUTPUT = 12_000


def _clip(output: str) -> str:
    """The tail of `output`, bounded. The tail because a failing run's summary is at the end."""
    text = output.strip()
    if len(text) <= MAX_OUTPUT:
        return text
    return "…[earlier output trimmed]…\n" + text[-MAX_OUTPUT:]


def from_lint(outcome: LintOutcome, cwd: str, lap: int) -> FailureReport:
    """The lint gate's `dirty` verdict as a failure the repair role can act on.

    The first adapter, and the shape the others follow: the command is carried verbatim so
    the fixer re-runs the gate rather than a command it guessed at, and no `Finding`s are
    synthesised from the output. Parsing linter text into targets and repairs is a per-tool
    job this package is forbidden to know how to do, and half-parsed findings would read as
    evidence to `CoderResult.actionable` while naming files a regex invented.
    """
    return FailureReport(
        source="lint",
        command=outcome.command,
        cwd=cwd,
        output=_clip(outcome.output),
        lap=lap,
    )


def from_command(
    source: str, command: str, cwd: str, output: str, lap: int
) -> FailureReport:
    """Any gate that is a command and an exit code — verification, regression, a repo's own.

    The generic arm. A gate declared in a repo's `agents.yml` that this package has never
    heard of arrives here and is repaired by the same turn as lint, which is the point of
    there being one turn.
    """
    return FailureReport(
        source=source, command=command, cwd=cwd, output=_clip(output), lap=lap
    )


def from_findings(
    source: str, findings: Sequence[Finding], cwd: str, lap: int, output: str = ""
) -> FailureReport:
    """A gate whose verdict is already structured — a review's or QA's hand-off.

    Distinct from `from_command` only in that there is something better than stdout to hand
    over: findings that already name a target and a repair, which is what stops the repair
    turn re-deriving from prose what the gate that read the diff already knew.
    """
    return FailureReport(
        source=source,
        cwd=cwd,
        output=_clip(output),
        findings=list(findings),
        lap=lap,
    )


__all__ = ["MAX_OUTPUT", "from_command", "from_findings", "from_lint"]
