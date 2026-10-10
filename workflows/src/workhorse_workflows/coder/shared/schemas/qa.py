"""The QA flow's models: the owner's verdict, and what each deterministic gate returns."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field
from workhorse.pyflow import dry_run

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding
from workhorse_workflows.kit.qa.schemas import QaPlanRun, QaResult, QaStatus, StackStatus

QaFlowStatus = Literal["passed", "replan", "refix"]


@dry_run(status="passed")
class QaRunResult(CoderResult):
    """One QA verdict an agent turn was asked for — the fix lane's check, retry and recheck."""

    status: Literal["passed", "failed", "blocked"] = Field(
        description="`passed` when every acceptance criterion is verified by something you "
        "actually ran — a criterion you could not exercise is never a pass. `failed` when "
        "the defect is real, in scope and you did not finish it, including when it is hard, "
        "when you ran out of ideas, or when your fix did not verify; that sends the item "
        "round again. `blocked` only when no further attempt in this repository could "
        "succeed because what is missing is external to it: a credential or deployment you "
        "cannot perform, a product decision present in neither the story nor the plan, or "
        "work that lives in a repo you were not given. Reaching for `blocked` to get out of "
        "difficult work is the exact failure this stage exists to stop.",
    )
    notes: str = Field(
        default="",
        description="What you ran, what you observed and what remains: the files changed, "
        "the commands that exercised them, and for a non-pass the specific defect or the "
        "missing dependency. This text is handed on to the turn that follows, so it has to "
        "be enough to act on — \"blocked, cannot fix\" comes straight back to you.",
    )


class QaPlanValidation(CoderResult):
    """`ostler qa validate` — is the authored `qa_plan.py` a plan the runner can execute?"""

    status: Literal["passed", "invalid"] = "invalid"
    notes: str = ""
    ostler: dict[str, Any] = {}


class DryRunGate(CoderResult):
    """Did the repair turn actually execute the scenarios it was told to repair?"""

    status: Literal["passed", "failed"] = "failed"
    notes: str = ""
    scenarios: list[str] = []
    verified: list[str] = []


class QaToolCatalog(CoderResult):
    """`ostler qa tools list` — the tools this repo opted into, resolved for this host."""

    tools: list[dict[str, Any]] = []
    errors: list[str] = []


class QaCleared(CoderResult):
    """`clear-qa-evidence.py` — the stale `qa/` outputs and root verdict are gone."""

    cleared: bool = False


class StackTornDown(CoderResult):
    """`teardown_stack` — the run is over, so the stack it started need not outlive it."""

    torn_down: Literal["yes", "no", "skipped"] = "no"
    notes: str = ""


class BacklogDrain(CoderResult):
    """`append-backlog-item.py` — the coder→author edge, drained into `docs/backlog.md`."""

    appended: int = 0
    skipped: int = 0
    notes: str = ""


class ScreenshotFlush(CoderResult):
    """`flush-root-screenshots.py` — stray root images relocated into `<spec_dir>/qa/`."""

    flushed: int = 0
    kept_tracked: int = 0
    notes: str = ""


class RegressionSuite(CoderResult):
    """One service's declared regression command, resolved to where it runs."""

    label: str = ""
    cwd: str = ""
    command: str = ""


class RegressionSuites(CoderResult):
    """`detect_regression_suites` — which committed suites, if any, this plan put at risk."""

    suites: list[RegressionSuite] = []


class FailureAttribution(CoderResult):
    """Which OKF node, if any, claims to verify a failing regression test."""

    test: str = ""
    path: str = ""
    classification: Literal["impacted", "outside-impact", "unattributed"] = "unattributed"
    nodes: list[str] = []


class RegressionRun(CoderResult):
    """`run_regression_suite` — the committed journey suites' own verdict."""

    status: Literal["passed", "failed", "blocked", "skipped", "error"] = "skipped"
    failing_tests: list[str] = []
    log_path: str = ""
    notes: str = ""
    failure_attribution: list[FailureAttribution] = []

    def as_qa_result(self) -> QaResult:
        """The story's running verdict, in the four states everything downstream routes on."""
        mirrored: QaStatus = "passed" if self.status == "skipped" else (
            "blocked" if self.status == "error" else self.status
        )
        notes = (
            f"regression {self.status}: {self.notes}"
            if self.status in {"skipped", "error"}
            else self.notes
        )
        return QaResult(status=mirrored, notes=notes)


class QaFinding(Finding):
    """One product defect the QA owner proved and hands back for the story's dev owner to fix."""

    id: str = Field(
        default="",
        description="Any stable handle. Reuse the same one when you restate a finding "
        "across passes.",
    )


@dry_run(status="passed")
class QaOwnerResult(CoderResult):
    """`qa/prompts/qa-story.md`: the QA owner's verdict on its story."""

    status: Literal["passed", "findings", "blocked"] = Field(
        description="`passed` when the scored run of `qa_plan.py` passed, your auditor's "
        "refutation attempt did not stand, and every obligation is covered. `findings` when "
        "the scored run failed on the product and each failure is one entry in `findings`. "
        "`blocked` only when something an operator alone can decide stops you: a credential, "
        "a deployed environment, hardware, or a product call neither the story nor the book "
        "settles. A plan, stack or setup problem is yours to repair and is never `blocked`.",
    )
    notes: str = Field(
        default="",
        description="What you planned, repaired and ran, and the scored run's result. On "
        "`blocked`, the one question that would unblock you and what you ruled out first.",
    )
    findings: list[QaFinding] = Field(
        default=[],
        description="On `findings`, one entry per product defect the scored run proved, each "
        "with the scenario and assertion that failed and the smallest product change that "
        "would pass it. Empty on `passed` and on `blocked`.",
    )
    proved_scenarios: list[str] = Field(
        default=[],
        description="The id of every scenario you added or changed this turn and dry-ran "
        "green under the scratch directory. The check reads the scratch log for each id, so "
        "naming one you did not dry-run fails it.",
    )


class QaFlowResult(CoderResult):
    """What the QA flow hands back to the run."""

    status: QaFlowStatus = "passed"
    qa: QaResult = QaResult()
    operator_notes: str = ""
    docs_recheck_required: bool = True
    findings: list[QaFinding] = []


__all__ = [
    "BacklogDrain",
    "DryRunGate",
    "FailureAttribution",
    "QaCleared",
    "QaFinding",
    "QaFlowResult",
    "QaFlowStatus",
    "QaOwnerResult",
    "QaPlanRun",
    "QaPlanValidation",
    "QaResult",
    "QaRunResult",
    "QaStatus",
    "QaToolCatalog",
    "RegressionRun",
    "RegressionSuite",
    "RegressionSuites",
    "ScreenshotFlush",
    "StackStatus",
    "StackTornDown",
]
