"""The QA flow's models — the running verdict, and what each deterministic gate returns.

**`QaResult` is one model for what the YAML kept as one key.** Nine nodes wrote
`qa_result` — the ostler runner, the evidence gate, the sentinel gate, the regression
suite, three `mark-*` scripts and three agent turns — with three different payload shapes,
because a run-context key has no schema. Here it is a single model — `status` and `notes`,
what every one of those writers actually produced — and it is what the flow threads from
gate to gate as *the* verdict. The ostler-backed runner produces more, so it returns the
`QaRunResult` subclass; a `QaResult`-typed field holds it without losing the payload.

**The status vocabularies stay separate.** `QaResult.status` is ostler's four-state
`passed | failed | blocked | invalid`; `QaPlanValidation.status` is the two-state
`passed | invalid` the validator computes for itself off a returncode. They looked alike as
untyped dicts and routed through different branch tables; they are different types here.

The `qa_cleared`, `stack_*`, `backlog_items_*` and `screenshots_*` keys were flat scalars
sprayed into the run context — six of them for `ensure-stack.py` alone. Each script's set
becomes one model, because the set is what the script actually returns.
"""
from __future__ import annotations

from typing import Any, ClassVar

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class QaResult(CoderResult):
    """The story's running QA verdict — ostler's four states, plus the blank before one.

    `status` starts empty rather than at `invalid`: the flow reads it before anything has
    run (`plan_qa` is handed the previous pass's notes, and `setup_fix` can be reached
    before the runner ever executes), and an unrun gate is not a failed one. Every branch
    that routes on it names its arms explicitly and sends the blank to a `default`, which
    is what the YAML's branch tables did.

    The runner's raw payload is **not** a field here — see `QaRunResult` below for why.
    """

    status: str = ""
    notes: str = ""


class QaRunResult(QaResult):
    """`run_qa_plan`'s verdict, plus the ostler payload only it has.

    `ostler` is a subclass field rather than an optional field on `QaResult` because a
    model's top-level fields are the output keys an agent turn is *asked* for — a field
    here is a promise every writer of this model must keep. Three agent turns return a
    `QaResult`, and none of them has a runner payload to report, so declaring `ostler` on
    the base made every one of those turns unparseable: the reply carried `status` and
    `notes`, the driver demanded a third key, and the node spent its whole retry →
    reframe ladder before defaulting to a blank verdict. The payload belongs to the one
    script node that produces it.

    Nothing reads `ostler`; it is kept for the run record, and a `QaResult`-typed field
    holds this subclass without losing it.
    """

    ostler: dict[str, Any] = {}


class QaPlanValidation(CoderResult):
    """`ostler qa validate` — is the authored `qa-plan.yml` a plan the runner can execute?

    Two states only, and `invalid` is the default for the same reason `OkfContextResult`
    uses it: the script computed the verdict from a returncode rather than reading it off
    ostler, so a missing answer is a failure to validate, not a pass.
    """

    status: str = "invalid"
    notes: str = ""
    ostler: dict[str, Any] = {}


class QaCleared(CoderResult):
    """`clear-qa-evidence.py` — the stale `qa/` outputs and root verdict are gone.

    The script's `{"qa_cleared": "yes"}` was unconditional: it printed the same string
    whether it deleted two artifacts or found no spec dir at all. `cleared` is `False` on
    that second path, so the run record distinguishes "nothing to clear" from "cleared" —
    nothing branches on it either way, exactly as before.
    """

    cleared: bool = False


class QaGiveupRecord(CoderResult):
    """`record_qa_giveup` — the give-up left a `qa.md` behind, or found one already there.

    `written` is `False` both when a real QA assessment already occupies the path (nothing
    to add: the runner's own account is better than a summary of gate notes) and when there
    was no spec dir to write into. Nothing branches on it; it is there so the run record
    distinguishes the give-up that produced an explanation from the one that inherited one.
    """

    written: bool = False
    path: str = ""


class StackStatus(CoderResult):
    """`ensure-stack.py` — the durable QA stack is up, adopted, absent, or broken.

    `ready` is three-state on purpose. `skip` (no manifest authored) is not a failure and
    routes exactly where `yes` does; only `no` reaches the setup-repair loop.

    The pids are strings because `workhorse.stack.ensure_stack` returns them that way —
    they are recorded for a human killing a leaked stack, never arithmetic.
    """

    ready: str = "no"
    app_pid: str = ""
    app_pgid: str = ""
    entry_url: str = ""
    failed_step: str = ""
    notes: str = ""


class BacklogDrain(CoderResult):
    """`append-backlog-item.py` — the coder→author edge, drained into `docs/backlog.md`.

    Both counts are reported and neither is routed on: the filer is best-effort by design,
    and an unwritable backlog degrades to `appended=0` with the items file kept rather than
    failing the story.
    """

    appended: int = 0
    skipped: int = 0
    notes: str = ""


class ScreenshotFlush(CoderResult):
    """`flush-root-screenshots.py` — stray root images relocated into `<spec_dir>/qa/`.

    `kept_tracked` is the count left alone because git already tracks them: a tracked root
    image is a committed asset, not QA litter.
    """

    flushed: int = 0
    kept_tracked: int = 0
    notes: str = ""


class RegressionPlatform(CoderResult):
    """`detect-regression-platform.py` — which committed suites, if any, this plan touched.

    `platform` defaults to `none` because the script fails **open**: an unreadable
    plan-context skips the regression step rather than blocking a story that may not have a
    UI at all. That is the opposite default from every gate in this module, and deliberate —
    this is a router, not a verdict.
    """

    platform: str = "none"
    layers: list[str] = []
    paths: list[str] = []


class FailureAttribution(CoderResult):
    """Which OKF node, if any, claims to verify a failing regression test.

    Diagnostic only. `classification` is `impacted` (a node this story changed verifies
    it), `outside-impact` (some other node does) or `unattributed` (the OKF
    `verificationIndex` names no owner) — and none of the three weakens the gate: a
    regression failure is the story's fix work whichever bucket it lands in.
    """

    test: str = ""
    path: str = ""
    classification: str = ""
    nodes: list[str] = []


class RegressionRun(CoderResult):
    """`run-regression-suite.py` — the committed journey suites' own verdict.

    `status` defaults to `passed`, which reads wrong for a gate until you see what the
    script means by it: every "nothing to run" path — no Makefile, no `e2e-journeys`
    target, no `maestro_flows/`, an unknown platform — is a *skip*, and a skip is `passed`.
    A repo with no regression suite is not a repo that failed one. Only a real non-zero
    suite exit is `failed`, and only an unreachable stack or emulator is `blocked`.

    The script emitted this twice — once as `regression_run` and once, status and notes
    only, as `qa_result` — so the shared `blocked → setup_fix` loop would pick it up.
    `as_qa_result()` is that mirror, made explicit and defined once.
    """

    status: str = "passed"
    failing_tests: list[str] = []
    log_path: str = ""
    notes: str = ""
    failure_attribution: list[FailureAttribution] = []

    def as_qa_result(self) -> QaResult:
        """The story's running verdict, as the YAML's duplicated `qa_result` key had it."""
        return QaResult(status=self.status, notes=self.notes)


# ── the agent turns' replies ──────────────────────────────────────────────────────────
# Each model's *top-level field names* are the output keys the turn is asked for — that is
# what `_outputs_for` reads off it — and the field defaults are the YAML's `default:` blocks,
# which is where a turn that answered nothing lands.


class ContextRepair(CoderResult):
    """The repair half of `prompts/repair-qa-context.md` — did the obligation packet heal?

    `repaired` re-runs the build; anything else, blank included, goes to the operator gate.
    """

    status: str = ""
    notes: str = ""


class QaContextRepair(CoderResult):
    """`repair-qa-context.md`'s whole reply — the only two-key agent turn in the coder.

    The YAML declared two outputs on one node (`qa_context_repair` and `qa_result`), and the
    driver builds one output key per top-level field of the model a turn returns. So the two
    keys are the two fields, each typed as the model the prompt actually specifies. Nothing
    about the driver had to change to carry this; it is the shape `_outputs_for` already
    implied, and the port is the first place that shape was needed.
    """

    qa_context_repair: ContextRepair = ContextRepair()
    qa_result: QaResult = QaResult()


class QaPlanResult(CoderResult):
    """`plan-qa.md` — the authored `qa-plan.yml`, as the author reports it.

    Nothing branches on it: the plan is judged by `validate_qa_plan` reading the file, not by
    the author's word for it. Kept because the YAML declared the key and the run record is
    poorer without the author's own account of what it wrote.
    """

    status: str = ""
    notes: str = ""


class QaPlanReview(CoderResult):
    """`review-qa-plan.md` — the semantic read of a plan that already parses.

    `revise` is the default because the YAML's is: a reviewer that produced nothing has not
    approved anything, and the bounded replan loop is the safe arm.
    """

    disposition: str = "revise"
    notes: str = "Semantic QA plan review produced no valid result."


class QaAssessment(CoderResult):
    """`qa-story.md` — what the runner's raw verdict actually means for this story.

    Four dispositions (`confirmed`, `repair_plan`, `extend_plan`, `repair_setup`) crossed with
    a `failure_class` and an `objective_reached` flag; the flow reads all three in sequence,
    which is what the YAML's four chained branch nodes did.
    """

    disposition: str = "repair_plan"
    failure_class: str = "plan"
    objective_reached: str = "no"
    notes: str = "QA run assessment produced no valid result."


class QaAudit(CoderResult):
    """`audit-qa.md` — an adversarial second read of a pass that already cleared the gate.

    `verdict` is `stands` or `refuted`, and `refutation_class` narrows a refutation to a
    product contradiction (the story is wrong), a plan defect or an evidence defect. A blank
    reply defaults to `refuted`/`plan-defect`, which spends a plan rework rather than
    shipping an unaudited pass.
    """

    verdict: str = "refuted"
    refutation_class: str = "plan-defect"
    notes: str = "Independent QA audit produced no valid result."


class QaTriage(CoderResult):
    """`triage-qa.md` — are the findings in-AC fixes, or a scope the author must re-derive?

    The YAML declared these as two bare scalar outputs rather than one object; here they are
    two fields of one model, which produces the same two keys. Both defaults are the YAML's
    and both are deliberately safe: never rescope on a malformed answer, and never let one
    earn the verification-only bonus pass.
    """

    triage_action: str = "qa_fix"
    qa_failure_class: str = "code"


class QaReport(CoderResult):
    """`report-qa-dev(-pass).md` — the findings written out to the tracker, in `dev` runs.

    One model for both prompts: they emit the same key and differ only in whether the story
    passed. Nothing branches on it — the report is the terminal act of a `dev` run.
    """

    status: str = ""
    notes: str = ""


class RegressionFix(CoderResult):
    """`fix-regression.md` — the attempt to make the committed journey suites green again.

    No `status`, and that is the prompt's own contract rather than an omission: the fixer's
    claim is not trusted, the suite is simply re-run, and `run_regression_suite` is the only
    thing that decides whether the fix worked.
    """

    notes: str = ""


class SetupResult(CoderResult):
    """`setup-fix.md` — the repair attempt on a stack manifest that would not come up.

    `unfixable` is the YAML's default and escalates to the operator gate. That is the right
    way round for a bounded loop: a fixer that exhausted its retries and said nothing must
    not be read as "ready" and sent back to `ensure_stack` to fail again.
    """

    status: str = "unfixable"
    notes: str = ""


# ── what the flow threads, and what it returns ────────────────────────────────────────


class QaLoop(CoderResult):
    """Everything the QA flow carries from gate to gate — one state parameter, not eighteen.

    The YAML kept all of this in flow vars: the running `qa_result`, five rework counters, the
    parent-owned rescope budget, three string flags used as booleans, the triager's failure
    class, and the six gate diagnostics `plan_qa` renders into its next brief. A driver state
    has parameters instead, and QA's graph is dense enough that threading eighteen of them
    through twenty-five states would be the whole file. So they travel as one model, which is
    legal without any driver change — a pydantic model round-trips through a checkpoint, as
    `author` settled — and a resume rebuilds the loop exactly.

    The three `"yes"`/`"no"` flags are real booleans here. They were compared against string
    literals in branch tables and never rendered into a prompt, so nothing observes the
    spelling.

    The diagnostics are what makes the loop converge: each failed gate hands the next
    `plan_qa` turn what it found, which is why `cleared()` exists — see the flow.
    """

    #: The story's running verdict, as whichever gate last wrote it left it.
    qa: QaResult = QaResult()

    #: `validate_qa_okf_context`'s verdict on the obligation packet, and its reasons. These
    #: two deliberately survive `cleared()`: `clear-qa-gate-state.py` never blanked them.
    context_status: str = ""
    context_notes: str = ""

    #: The four gate diagnostics `clear-qa-gate-state.py` blanked before each plan turn.
    plan_validation_notes: str = ""
    plan_review_notes: str = ""
    assessment_notes: str = ""
    audit_notes: str = ""

    #: The triager's class, which is what the one-shot bonus pass is granted on. Blank until
    #: a triage turn runs — the YAML never declared this var, so an untriaged loop reads it
    #: as unset and earns no bonus.
    failure_class: str = ""

    #: The last discrete verdict from each of the three agent gates, carried for telemetry
    #: and for the give-up record. **Nothing branches on these** — each gate branches on its
    #: own fresh result, and a stale disposition deciding a later transition is exactly the
    #: bug the `_finding` docstring describes. They are recorded because the counters alone
    #: are a cost and not a diagnosis: "four plan-QA attempts" says a story was expensive,
    #: "four attempts, every one ending `revise`" says which gate made it so.
    #:
    #: Blank means the gate has not run yet, which is distinct from a gate that ran and
    #: found nothing wrong.
    plan_review_disposition: str = ""  #: approved | revise
    assessment_disposition: str = ""  #: confirmed | repair_plan | extend_plan | repair_setup
    assessment_failure_class: str = ""  #: none | product | plan | environment | evidence
    audit_verdict: str = ""  #: stands | refuted
    audit_refutation_class: str = ""  #: none | product-contradiction | plan-defect | evidence-defect

    #: Which of the above are worth a span dimension. Each is a closed vocabulary of a
    #: handful of words, so the label cardinality they add is bounded.
    VERDICT_LABELS: ClassVar[tuple[str, ...]] = (
        "plan_review_disposition",
        "assessment_disposition",
        "assessment_failure_class",
        "audit_verdict",
        "audit_refutation_class",
    )

    #: The bounded budgets. Each was a `{value: 0}` var with a `seed`/`incr` node pair, except
    #: `plan_validation_rework` and `plan_review_rework` — see the flow's
    #: `_guard_plan_validation` and `_guard_plan_review`.
    context_rework: int = 0
    plan_rework: int = 0
    plan_validation_rework: int = 0
    plan_review_rework: int = 0
    qa_rework: int = 0
    setup_rework: int = 0
    regression_fix: int = 0

    #: The parent-owned rescope budget, threaded in and crossed back out on a rescope.
    triage_scope: int = 0

    #: Regression bookkeeping: a fix was applied since the last primary QA, and primary QA
    #: owes a re-run because of it.
    regression_fix_applied: bool = False
    regression_reqa_pending: bool = False

    #: Whether the one verification-only bonus pass past `MAX_QA_REWORKS` has been spent.
    bonus_used: bool = False

    @property
    def plan_rework_total(self) -> int:
        """Repairs spent across validation, review, and post-run plan gates.

        Derived from the durable stage counters so old checkpoints retain what they
        already spent and no duplicated total can drift from its components.
        """
        return self.plan_rework + self.plan_validation_rework + self.plan_review_rework

    def update(self, **changes: object) -> QaLoop:
        """The same loop with some fields replaced — the port of an `incr`/`emit-kv` node."""
        return self.model_copy(update=changes)

    def with_qa(self, qa: QaResult) -> QaLoop:
        """The same loop carrying a new running verdict."""
        return self.model_copy(update={"qa": qa})

    def cleared(self) -> QaLoop:
        """`clear-qa-gate-state.py`: forget every gate's findings before re-running them.

        The script replaced five keys wholesale, so the running verdict is blanked too — a
        re-planned story has not failed QA yet. The two *context* fields are not in that set
        and stay, which is the script's behaviour and not an oversight of the port.

        The recorded verdicts blank with the notes they summarise. They are the same
        statement in two forms, so leaving one behind would let a span claim `revise` for a
        gate whose finding had already been forgotten.
        """
        return self.model_copy(
            update={
                "qa": QaResult(),
                "plan_validation_notes": "",
                "plan_review_notes": "",
                "assessment_notes": "",
                "audit_notes": "",
                **dict.fromkeys(self.VERDICT_LABELS, ""),
            }
        )

    @property
    def block_notes(self) -> str:
        """The composed brief the operator gate and the setup fixer are both handed.

        `"{{ qa_result.notes }} | Assessment: {{ qa_assessment.notes }}"`, rendered once here
        because four YAML nodes rendered it identically.
        """
        return f"{self.qa.notes} | Assessment: {self.assessment_notes}"


class QaFlowResult(CoderResult):
    """What the QA flow hands back — the YAML's five `qa_phase` output keys, as one value.

    `status` is the `qa_status` the four `emit-kv.py` terminals wrote (`passed`, `exhausted`,
    `replan`, `rescope`), and `exhausted` is the default for the same reason the YAML's
    `qa_phase` output declared it: a flow that produced nothing has not passed.

    `triage_scope` crosses the flow boundary in both directions — the parent seeds it and
    reads the bumped value back — which is the one piece of state the isolated flow does not
    own.

    `spent` exists because `qa_rework` alone cannot describe why the flow gave up. Four
    separate budgets end it `exhausted` — context repairs, plan repairs, code reworks, and the
    operator loop — and the parent stamped the story with the code-rework count whichever one
    ran out. A story that burned its QA-plan repairs and never reached a code fix was
    committed as `[QA FAILED after 0 attempts — needs manual review]`, which reads as "the
    loop never tried" and is the opposite of what happened.
    """

    status: str = "exhausted"
    qa: QaResult = QaResult()
    qa_rework: int = 0
    triage_scope: int = 0
    operator_notes: str = ""
    #: Which budget ran out and how much of it was spent, as the phrase that goes in the
    #: give-up marker ("4 total QA-plan repair"). Empty unless the flow ended `exhausted`.
    spent: str = ""


__all__ = [
    "BacklogDrain",
    "ContextRepair",
    "FailureAttribution",
    "QaAssessment",
    "QaAudit",
    "QaCleared",
    "QaContextRepair",
    "QaFlowResult",
    "QaLoop",
    "QaPlanResult",
    "QaPlanReview",
    "QaPlanValidation",
    "QaReport",
    "QaResult",
    "QaRunResult",
    "QaTriage",
    "RegressionFix",
    "RegressionPlatform",
    "RegressionRun",
    "ScreenshotFlush",
    "SetupResult",
    "StackStatus",
]
