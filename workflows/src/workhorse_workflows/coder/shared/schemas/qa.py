"""The QA flow's models — the running verdict, and what each deterministic gate returns."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding
from workhorse_workflows.qa.schemas import QaPlanRun, QaResult, QaStatus, StackStatus

QaDisposition = Literal["confirmed", "repair_plan", "extend_plan", "repair_setup"]

QaFailureClass = Literal["none", "product", "plan", "environment", "evidence"]

QaAuditVerdict = Literal["stands", "refuted"]
QaRefutationClass = Literal["none", "product-contradiction", "plan-defect", "evidence-defect"]

QaTriageAction = Literal["rescope", "qa_fix"]
QaTriageClass = Literal["code", "product", "evidence", "environment"]

QaFlowStatus = Literal["passed", "inconclusive", "replan", "rescope", "refix"]


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




class ContextRepair(CoderResult):
    """The repair half of `qa/prompts/repair-qa-context.md` — did the obligation packet heal?"""

    status: Literal["repaired", "blocked"] = Field(
        description="`repaired` when the grounding is fixed and the packet can be rebuilt. "
        "`blocked` only when the repair needs an author or product decision, or a source "
        "repository you were not given.",
    )
    notes: str = Field(
        default="", description="What you repaired — or, when blocked, what it needs."
    )

    def as_qa_result(self) -> QaResult:
        """This repair as the story's running QA verdict."""
        return QaResult(
            status="invalid" if self.status == "repaired" else "blocked", notes=self.notes
        )


class QaPlanResult(CoderResult):
    """`plan-qa.md` — the authored `qa_plan.py`, as the author reports it."""

    status: Literal["done", "blocked"] = Field(
        description="`done` when the plan is written. `blocked` only when no plan this "
        "stage could write would be a real test of the story: the criteria name a surface, "
        "device, service or credential that does not exist to drive, they contradict each "
        "other or the code so that no scenario can assert either reading, or the coverage "
        "lives in a repo you were not given. A plan that is merely hard to write is not "
        "blocked. Never write scenarios you know cannot run and report `done` — a plan that "
        "dry-runs green by asserting nothing is worse than no plan, because the run "
        "continues on it.",
    )
    notes: str = Field(
        default="",
        description="What you wrote, or — on a repair — each finding you closed and how, "
        "naming any you did not close and why. On `blocked`, the specific dependency and "
        "what you attempted before concluding it.",
    )
    repaired_scenarios: list[str] = Field(
        default=[],
        description="On a repair turn, the id of every scenario whose code you changed, "
        "added ones included: a scenario the last run passed can be broken by this turn and "
        "nothing else would catch it. The dry-run gate reads the scratch log for each id, so "
        "naming one you did not dry-run refuses the repair. Empty on a first draft, which "
        "repaired nothing.",
    )
    proved_scenarios: list[str] = Field(
        default=[],
        description="On a first draft, the ids you dry-ran green, riskiest first — evidence "
        "you point at rather than a claim you make, read from the same scratch logs. Empty "
        "is allowed when nothing in the plan is worth proving; a named id with no green log "
        "behind it is not.",
    )


class QaFinding(Finding):
    """One QA finding, from any of the three gates, with the authority it falls under named."""

    id: str = Field(
        default="",
        description="Any stable handle. Reuse the same one when you restate a finding "
        "across passes.",
    )
    scope: Literal["plan", "stack", "product-test"] = Field(
        default="plan",
        description="Where the repair lives — the flow routes on this field rather than on "
        "your prose. `plan`: an edit inside `qa_plan.py` / `qa-plan.md`, sent to the plan "
        "author. `product-test`: an assertion, fixture or fix in product code or a "
        "committed test the plan only cites, sent to the fix loop, which edits the code. "
        "`stack`: the book's `runbook` node and the flow's stack step — a service, emulator, "
        "database, seed or aggregate command that must be up before the plan runs. Name it "
        "by where the repair lands, not by which gate found it: an evidence defect whose "
        "real repair is a test assertion filed as `plan` bills a replan that cannot write "
        "it, and the identical gap comes back on the next pass.",
    )
    kind: Literal["coverage", "overclaim", "cosmetic"] = Field(
        default="coverage",
        description="What breaks if the plan ships as it stands. `coverage`: an AC or OKF "
        "obligation has no cited evidence that would catch it failing — the only kind that "
        "refuses a plan. `overclaim`: a checkpoint asserts more than its cited test proves; "
        "execution is unaffected, but the audit reads the plan's claims. `cosmetic`: counts, "
        "wording, ordering, which no gate and no runner reads.",
    )


class QaAssessment(CoderResult):
    """`qa-story.md` — what the runner's raw verdict actually means for this story."""

    status: Literal["assessed", "blocked"] = Field(
        description="`assessed` when you reached a reading of the run — the three fields "
        "below are then that reading. `blocked` when you could not judge the run at all.",
    )
    disposition: QaDisposition | None = Field(
        default=None,
        description="What the run means for the story. `confirmed` carries it; each of the "
        "others says the plan did not, and names which lane repairs it.",
    )
    failure_class: QaFailureClass | None = Field(
        default=None, description="What the remaining failure needs, on a non-confirmed run."
    )
    objective_reached: bool | None = Field(
        default=None,
        description="Whether every objective the story set was observed, as a person using "
        "the running app would observe it.",
    )
    findings: list[QaFinding] = Field(
        default=[],
        description="A `confirmed` disposition returns an empty list. Any other must carry "
        "at least one finding: the disposition says the run did not carry the story, and "
        "the findings say who repairs what. This is what the repair is briefed from.",
    )
    notes: str = Field(
        default="QA run assessment produced no valid result.",
        description="A summary of the findings — routing and diagnosis, never a replacement "
        "QA verdict.",
    )


class QaAudit(CoderResult):
    """`audit-qa.md` — an adversarial second read of a pass that already cleared the gate."""

    status: Literal["audited", "blocked"] = Field(
        description="`audited` when you reached a verdict on the evidence. `blocked` when "
        "there was none to judge — which is not the same as refuting it.",
    )
    verdict: QaAuditVerdict | None = Field(
        default=None, description="Whether the pass survives an adversarial second read."
    )
    refutation_class: QaRefutationClass | None = Field(
        default=None,
        description="`none` only when the pass stands cleanly; otherwise what the "
        "refutation is — a product contradiction, a plan defect, or an evidence defect — "
        "with concrete scenario, assertion, obligation and artifact references.",
    )
    findings: list[QaFinding] = Field(
        default=[],
        description="A refutation — and a `stands` that still names a refutation class — "
        "carries at least one finding; a pass that stands cleanly returns an empty list. "
        "This is what the repair is briefed from.",
    )
    notes: str = Field(
        default="Independent QA audit produced no valid result.",
        description="A summary of the findings, in one or two sentences.",
    )


class QaTriage(CoderResult):
    """`triage-qa.md` — are the findings in-AC fixes, or a scope the author must re-derive?"""

    status: Literal["triaged", "blocked"] = Field(
        description="`triaged` when you sorted the findings. `blocked` when you could not "
        "sort them at all."
    )
    triage_action: QaTriageAction | None = Field(
        default=None,
        description="`rescope` only if you amended the acceptance criteria and have rescope "
        "budget left; otherwise `qa_fix`, which is also the answer when every finding is "
        "purely in-AC.",
    )
    qa_failure_class: QaTriageClass | None = Field(
        default=None,
        description="What the remaining failure needs. `code`: a QA-side code or test change "
        "to satisfy an AC — the scenario, its fixtures, or a driver the QA lane owns. "
        "`product`: the product itself does not meet an AC that stands, which returns the "
        "story to the dev lane rather than patching it from inside QA. `evidence`: the "
        "product code is already correct and every gate is green, and what remains is only "
        "evidence work — capturing or refreshing screenshots, widening sweep coverage, "
        "re-running a driver to completion, fixing an artifact's shape. Be strict: if any "
        "finding needs a code change the class is `code`. `environment`: the stack, fixtures "
        "or emulator must be repaired or seeded before any verdict is possible. The flow "
        "grants one extra verification-only pass when an exhausted budget leaves only "
        "`evidence` work, so classify honestly: a wrong `evidence` wastes that pass, and "
        "a wrong `code` sends a finished story to manual review.",
    )
    notes: str = Field(
        default="",
        description="Read on a refusal: what stopped you from sorting the findings. A "
        "triage that reached a verdict has said everything it needs to in the fields above.",
    )


class QaReport(CoderResult):
    """`report-qa-dev(-pass).md` — the findings written out to the tracker, in `dev` runs."""

    status: Literal["reported", "blocked"] = Field(
        description="`reported` once the comment file exists. `blocked` in the one case "
        "where it cannot: the evidence you were pointed at is not there to read, or the "
        "output path cannot be written. Never invent the comment's content from the story "
        "alone — a tracker comment describing a QA run nobody performed is worse than no "
        "comment, because it is read as a record.",
    )
    notes: str = Field(
        default="",
        description="The output path, and what the comment says. On `blocked`, what was "
        "missing.",
    )


class RegressionFix(CoderResult):
    """`fix-regression.md` — the attempt to make the committed journey suites green again."""

    status: Literal["attempted", "blocked"] = Field(
        description="`attempted` on any turn that did the work, whatever you think it "
        "achieved — the next suite run judges that, not this field. `blocked` only when "
        "nothing in this repository would let you attempt the fixes at all, because what is "
        "missing is external to it: a credential or deployment you cannot perform, a product "
        "decision present in neither the story nor the plan, or work in another repo. A fix "
        "you doubt is still `attempted`.",
    )
    notes: str = Field(
        default="",
        description="Per failure — and every failure, not just the first: what was wrong, "
        "what you changed in app code or spec, and how you verified it locally. Name any "
        "failure you could not fix and why. On `blocked`, the specific dependency and what "
        "you attempted before concluding it.",
    )


class SetupResult(CoderResult):
    """`setup-fix.md` — the repair attempt on a stack manifest that would not come up."""

    status: Literal["ready", "unfixable"] = Field(
        description="`ready` when the environment is QA-capable now — services up and "
        "verified, tools installed — and also when you conclude the blocker is not an "
        "environment problem at all (the feature is genuinely broken or missing), so QA "
        "re-runs and routes it to the code-fix loop. `unfixable` only for a true wall that "
        "needs a human: a real credential or secret that cannot be generated locally, a "
        "deployed or preview environment, or hardware. Prefer `ready` whenever you made the "
        "stack runnable.",
    )
    notes: str = Field(
        default="",
        description="What was blocking QA, what you changed or started to fix it, and the "
        "readiness proof — or, when unfixable, exactly which human-only resource is needed.",
    )




class AssessmentRecord(CoderResult):
    """What the loop remembers of the last execution-assessment turn."""

    notes: str = ""
    disposition: QaDisposition | Literal[""] = ""
    failure_class: QaFailureClass | Literal[""] = ""

    def dimensions(self) -> dict[str, str]:
        """The two verdicts under the flat names the telemetry store classifies by suffix."""
        return {
            "assessment_disposition": self.disposition,
            "assessment_failure_class": self.failure_class,
        }


class AuditRecord(CoderResult):
    """The same three fields for the independent audit — see `AssessmentRecord`."""

    notes: str = ""
    verdict: QaAuditVerdict | Literal[""] = ""
    refutation_class: QaRefutationClass | Literal[""] = ""

    def dimensions(self) -> dict[str, str]:
        """The audit's two verdicts under their flat, suffix-classified names."""
        return {
            "audit_verdict": self.verdict,
            "audit_refutation_class": self.refutation_class,
        }


class FixWorklist(CoderResult):
    """The per-scenario fix worklist, and where in it the flow is."""

    items: tuple[str, ...] = ()
    rework: int = 0
    problems: tuple[str, ...] = ()

    def popped(self) -> FixWorklist:
        """The worklist with the head proved green — the rest of it, on a clean slate."""
        return FixWorklist(items=self.items[1:])


class LaneClock(CoderResult):
    """What this lane has spent: wall-clock seconds, and how long the current chain is."""

    seconds: float = 0.0
    plan_seconds: float = 0.0

    chain_laps: int = 0

    overruns: int = 0

    def charged(self, seconds: float, *, plan: bool, overran: bool = False) -> LaneClock:
        """The same clock with one turn's wall-clock added to the lane it was spent in."""
        return self.model_copy(
            update={
                "seconds": self.seconds + seconds,
                "plan_seconds": self.plan_seconds + (seconds if plan else 0.0),
                "overruns": self.overruns + (1 if overran else 0),
            }
        )


class QaLoop(CoderResult):
    """Everything the QA flow carries from gate to gate — one state parameter, not eighteen."""

    qa: QaResult = QaResult()

    context_status: Literal["", "passed", "invalid"] = ""
    context_notes: str = ""

    plan_validation_notes: str = ""

    assessment: AssessmentRecord = AssessmentRecord()
    audit: AuditRecord = AuditRecord()

    failure_class: QaTriageClass | Literal[""] = ""

    context_rework: int = 0
    plan_rework: int = 0
    plan_validation_rework: int = 0
    qa_rework: int = 0
    setup_rework: int = 0
    regression_fix: int = 0
    audit_rework: int = 0

    blocked_problems: tuple[str, ...] = ()

    setup_problems: tuple[str, ...] = ()

    fix: FixWorklist = FixWorklist()

    plan_rejections: tuple[str, ...] = ()
    repaired_failures: tuple[str, ...] = ()
    repaired_lap: str = ""
    tried_laps: tuple[str, ...] = ()
    class_switched: bool = False

    escalations: int = 0

    triage_scope: int = 0

    regression_fix_applied: bool = False
    regression_reqa_pending: bool = False

    bonus_used: bool = False

    docs_recheck_required: bool = True

    clock: LaneClock = LaneClock()

    @property
    def plan_rework_total(self) -> int:
        """Repairs spent across validation, review, and post-run plan gates."""
        return self.plan_rework + self.plan_validation_rework

    @property
    def plan_judgement_rework(self) -> int:
        """Repairs spent on the two gates that exercise *judgement* about the plan."""
        return self.plan_rework

    def update(self, **changes: object) -> QaLoop:
        """The same loop with some fields replaced — the port of an `incr`/`emit-kv` node."""
        return self.model_copy(update=changes)

    def with_qa(self, qa: QaResult) -> QaLoop:
        """The same loop carrying a new running verdict."""
        return self.model_copy(update={"qa": qa})

    def with_lap(self, lap: str, **changes: object) -> QaLoop:
        """The same loop dispatching a repair lap of class `lap`, with the class remembered."""
        return self.model_copy(
            update={
                **changes,
                "repaired_lap": lap,
                "tried_laps": self.tried_laps
                if lap in self.tried_laps
                else (*self.tried_laps, lap),
            }
        )

    def charged(self, seconds: float, *, plan: bool = False, overran: bool = False) -> QaLoop:
        """The same loop with one turn's wall-clock added to the lane it was spent in."""
        return self.model_copy(
            update={"clock": self.clock.charged(seconds, plan=plan, overran=overran)}
        )

    def require_docs_recheck(self) -> QaLoop:
        """Mark a possible as-built mutation; this taint is monotonic within the flow."""
        return self.model_copy(update={"docs_recheck_required": True})

    def cleared(self) -> QaLoop:
        """`clear-qa-gate-state.py`: forget every gate's findings before re-running them."""
        return self.model_copy(
            update={
                "qa": QaResult(),
                "plan_validation_notes": "",
                "assessment": AssessmentRecord(),
                "audit": AuditRecord(),
            }
        )

    @property
    def block_notes(self) -> str:
        """The composed brief the operator gate and the setup fixer are both handed."""
        return f"{self.qa.notes} | Assessment: {self.assessment.notes}"


class QaFlowResult(CoderResult):
    """What the QA flow hands back — the YAML's five `qa_phase` output keys, as one value."""

    status: QaFlowStatus = "inconclusive"
    qa: QaResult = QaResult()
    qa_rework: int = 0
    triage_scope: int = 0
    operator_notes: str = ""
    docs_recheck_required: bool = True


__all__ = [
    "BacklogDrain",
    "ContextRepair",
    "FailureAttribution",
    "QaAssessment",
    "QaAudit",
    "QaAuditVerdict",
    "QaCleared",
    "QaDisposition",
    "QaFailureClass",
    "QaFlowResult",
    "QaFlowStatus",
    "QaLoop",
    "QaPlanResult",
    "QaPlanRun",
    "QaPlanValidation",
    "QaRefutationClass",
    "QaReport",
    "QaResult",
    "QaRunResult",
    "QaStatus",
    "QaToolCatalog",
    "QaTriage",
    "QaTriageAction",
    "QaTriageClass",
    "RegressionFix",
    "RegressionRun",
    "RegressionSuite",
    "RegressionSuites",
    "ScreenshotFlush",
    "SetupResult",
    "StackStatus",
]
