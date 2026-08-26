"""The QA flow's models — the running verdict, and what each deterministic gate returns.

**`QaResult` is one model for what the YAML kept as one key.** Nine nodes wrote
`qa_result` — the ostler runner, the evidence gate, the sentinel gate, the regression
suite, three `mark-*` scripts and three agent turns — with three different payload shapes,
because a run-context key has no schema. Here it is a single model — `status` and `notes`,
what every one of those writers actually produced — and it is what the flow threads from
gate to gate as *the* verdict. The ostler-backed runner produces more, so it returns the
`QaPlanRun` subclass; a `QaResult`-typed field holds it without losing the payload.

**The status vocabularies stay separate.** `QaResult.status` is ostler's four-state
`passed | failed | blocked | invalid`; `QaPlanValidation.status` is the two-state
`passed | invalid` the validator computes for itself off a returncode. They looked alike as
untyped dicts and routed through different branch tables; they are different types here.

The `qa_cleared`, `stack_*`, `backlog_items_*` and `screenshots_*` keys were flat scalars
sprayed into the run context — six of them for `ensure-stack.py` alone. Each script's set
becomes one model, because the set is what the script actually returns.
"""
from __future__ import annotations

from typing import Any, ClassVar, Literal

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding


class QaResult(CoderResult):
    """The story's running QA verdict — ostler's four states, plus the blank before one.

    `status` starts empty rather than at `invalid`: the flow reads it before anything has
    run (`plan_qa` is handed the previous pass's notes, and `setup_fix` can be reached
    before the runner ever executes), and an unrun gate is not a failed one. Every branch
    that routes on it names its arms explicitly and sends the blank to a `default`, which
    is what the YAML's branch tables did.

    The runner's raw payload is **not** a field here — see `QaPlanRun` below for why.
    """

    status: str = ""
    notes: str = ""


class QaPlanRun(QaResult):
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


class QaRunResult(CoderResult):
    """One QA verdict an agent turn was asked for — the fix lane's check, retry and recheck.

    Separate from `QaResult` because the two are produced by different things. `QaResult` is
    the *rolling* verdict Python threads from gate to gate, and it starts blank because the
    flow reads it before anything has run. This one is what a turn *reports*, so `status` is
    a required `Literal` with no default: a turn that cannot name which of the three it found
    has not reported, and the parse failure buys a retry turn where a blank bought a silent
    "not passed" arm nobody chose.

    Three values, not ostler's four: a grading turn either passed the item, failed it, or
    could not grade it at all. `invalid` is a QA *plan*'s verdict and no turn here writes one.
    """

    status: Literal["passed", "failed", "blocked"]
    notes: str = ""


class QaPlanValidation(CoderResult):
    """`ostler qa validate` — is the authored `qa_plan.py` a plan the runner can execute?

    Two states only, and `invalid` is the default for the same reason `OkfContextResult`
    uses it: the script computed the verdict from a returncode rather than reading it off
    ostler, so a missing answer is a failure to validate, not a pass.
    """

    status: str = "invalid"
    notes: str = ""
    ostler: dict[str, Any] = {}


class DryRunGate(CoderResult):
    """Did the repair turn actually execute the scenarios it was told to repair?

    The deterministic half of the dry-run contract in `repair-qa-plan.md`. A repair turn that
    edits a locator and returns has established nothing — the next full suite run is what
    finds out, forty minutes later, and a lap that costs a whole run to learn one assertion
    still fails is the loop this gate exists to cut. The turn has the stack up and the plan on
    disk, so it can run the failing scenario itself for the price of a shell command.

    `status` is `passed` or `failed`, on the same two-state rule as `QaPlanValidation`, and a
    failure routes back into the repair loop on the same budget rather than a new one.
    `scenarios` is what was demanded; `verified` is what the scratch evidence proved.
    """

    status: str = "failed"
    notes: str = ""
    scenarios: list[str] = []
    verified: list[str] = []


class QaToolCatalog(CoderResult):
    """`ostler qa tools list` — the tools this repo opted into, resolved for this host.

    A node output rather than a value `_plan_args` reads straight off `agents.yml`,
    because it crosses the same host boundary `qa_plan_validation` does: which tools
    resolve, and whether their binaries are on `PATH`, is a fact about *this* machine,
    and a resumed run must see the catalog it was checkpointed with, not one re-derived
    against whatever the host looks like when the resume happens to run.
    """

    tools: list[dict[str, Any]] = []
    errors: list[str] = []


class QaCleared(CoderResult):
    """`clear-qa-evidence.py` — the stale `qa/` outputs and root verdict are gone.

    The script's `{"qa_cleared": "yes"}` was unconditional: it printed the same string
    whether it deleted two artifacts or found no spec dir at all. `cleared` is `False` on
    that second path, so the run record distinguishes "nothing to clear" from "cleared" —
    nothing branches on it either way, exactly as before.
    """

    cleared: bool = False


class StackStatus(CoderResult):
    """`ensure-stack.py` — the durable QA stack is up, adopted, undeclared, or broken.

    `ready` is three-state on purpose, and the third state is the one this schema was
    wrong about for a year. `none` means the book declares no stack at all — no `runbook`
    node, no walkthrough `server`. That is not a pass: it used to be spelled `skip` and
    routed exactly where `yes` did, so a repo that had never authored a runbook ran its
    QA against nothing and found out only once the runner failed for reasons no fixer
    could read. `none` and `no` both reach the setup-repair loop; only `yes` runs QA.

    The pids are strings because `ostler.qa.stack.ensure_stack` returns them that way —
    they are recorded for a human killing a leaked stack, never arithmetic.
    """

    ready: str = "no"
    app_pid: str = ""
    app_pgid: str = ""
    entry_url: str = ""
    failed_step: str = ""
    notes: str = ""


class StackTornDown(CoderResult):
    """`teardown_stack` — the run is over, so the stack it started need not outlive it.

    `torn_down` is `yes`, `no` or `skipped`; none of them fails the run. A stack is an
    expensive thing to have running and a cheap thing to have left running, so a runbook
    that declares no `stop:` recipe is honoured rather than second-guessed — that is the
    `skipped` case, and it is the leave-it-up policy the reuse doctrine already states.
    """

    torn_down: str = "no"
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


class RegressionSuite(CoderResult):
    """One service's declared regression command, resolved to where it runs."""

    #: `<repo>::<path>`, the same identity the dev lane dispatches on.
    label: str = ""
    #: Absolute path to the service directory the command runs in.
    cwd: str = ""
    #: What `agents.yml` declares under this service's `regression:` key. Never guessed.
    command: str = ""


class RegressionSuites(CoderResult):
    """`detect_regression_suites` — which committed suites, if any, this plan put at risk.

    Empty means "no service this plan touched declares a regression command", which skips
    the whole regression step. That is the opposite default from every gate in this module,
    and deliberate — this is a router, not a verdict, and it fails **open**: an unreadable
    plan context reports nothing to run rather than blocking a story.

    It replaced a `platform` field of `web`/`mobile`/`both`/`none`, which was the workflow
    holding an opinion about which stacks have journey suites. A repo that runs its journeys
    some third way could not say so, and one whose service type was not on the list was
    silently exempt from a suite it really had.
    """

    suites: list[RegressionSuite] = []


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
    """The repair half of `qa/prompts/repair-qa-context.md` — did the obligation packet heal?

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
    """`plan-qa.md` — the authored `qa_plan.py`, as the author reports it.

    Its prose is judged by nothing: the plan itself is judged by `validate_qa_plan` reading
    the file, not by the author's word for it. Kept because the YAML declared the key and the
    run record is poorer without the author's own account of what it wrote.

    `repaired_scenarios` is the exception, and only on the repair path. The dry-run gate has
    to know which scenarios a repair *touched* — a repair that rewrote a scenario the last
    run passed is exactly as capable of breaking it, and the failing set the flow already has
    cannot name it. It is a claim, not evidence: the gate still reads the scratch run log for
    each id, so naming a scenario it did not dry-run fails the gate rather than passing it.

    `proved_scenarios` is the same mechanism pointed at the *first draft*. The draft has no
    failing set to be dispatched against, so until now it was the one plan turn that reached
    the runner on nobody's word but its own — and the cheapest defects in this lane are the
    ones a first draft makes: a locator that resolves to nothing, a fixture that is not
    seeded, a straight apostrophe where the surface renders U+2019. Each of those cost a full
    suite run and a repair lap to discover. The author now names the one or two scenarios it
    judged riskiest and dry-runs them before it answers, and the same gate reads the same
    scratch evidence for the ids it named. Empty is not an error — a plan of one trivial
    unit scenario has nothing worth proving — but a named id with no green log behind it is.
    """

    status: str = ""
    notes: str = ""
    repaired_scenarios: list[str] = []
    proved_scenarios: list[str] = []


class QaFinding(Finding):
    """One QA finding, from any of the three gates, with the authority it falls under named.

    `target`/`issue`/`repair` come from `Finding` — this class is where that shared shape
    was first written, and it is now the contract every lane's findings are held to.

    `scope` is closed for the same reason `DocumentationFinding.kind` is, and here the
    closure is load-bearing rather than diagnostic. Every gate's brief says in prose that the
    heavyweight shared stack is `ensure_stack`'s and not the plan's, and that a finding the
    author cannot act on inside a plan file spends the repair budget for nothing — and gates
    keep issuing them anyway. Prose cannot filter prose. A named scope can.

    The scope now decides *routing*, not just filtering: `_route_findings` sends a
    `product-test` finding to the fix loop, a `plan` finding to the plan author and a `stack`
    finding to setup. Dropping the first two on the floor is what livelocked a live story for
    82 minutes — three gates kept rediscovering a missing test assertion and kept billing the
    one author who could not write it.

    `kind` is the second closed axis, and it exists because `scope` alone could not stop the
    other way this loop fails to terminate. `scope` answers *where the repair lives*; `kind`
    answers *what breaks if the plan ships as it stands*, which is decidable by naming the
    consumer that reads the thing:

    `coverage`   an AC or OKF obligation has no cited evidence that would catch it failing.
                 The runner's behaviour changes. This is the only kind that refuses a plan.
                 Since the pre-run reviewer's deletion, `ostler qa validate` catches the
                 mechanical half of it before any gate reads the file.
    `overclaim`  a checkpoint asserts more than its cited test proves. Execution is
                 unaffected, but `audit-qa` reads the plan's claims, so leaving one in place
                 seeds a refutation later — it is repaired, just not re-reviewed.
    `cosmetic`   counts, wording, ordering. No gate and no runner reads it.

    The default is `coverage` so the field is fail-closed: an omitted `kind`, a checkpoint
    written before this field existed, and the `assess`/`audit` gates that share this model
    without classifying all keep exactly the behaviour they had.

    The case that motivated it: a live story spent four `power="high"` pre-run review passes
    and then ended with *no QA verdict at all*, because after the first pass found a real
    evidence defect the next three each raised a fresh prose nit — a viewport claim the run
    does not exercise, and an objective saying "10 test cases" where the file has 9. Its own
    prose classified them correctly ("neither reflects a missing acceptance-criterion
    coverage gap") and it refused anyway; the instruction to approve what it had listed was
    prose, and prose cannot filter prose. That node is gone, and the axis it forced is what
    the surviving gates are still judged on.
    """

    id: str = ""
    scope: Literal["plan", "stack", "product-test"] = "plan"
    #: See the class docstring. `coverage` is the fail-closed default and the only blocking
    #: kind; the post-run gates report it and `_finding_line` renders it.
    kind: Literal["coverage", "overclaim", "cosmetic"] = "coverage"


class QaAssessment(CoderResult):
    """`qa-story.md` — what the runner's raw verdict actually means for this story.

    Four dispositions (`confirmed`, `repair_plan`, `extend_plan`, `repair_setup`) crossed with
    a `failure_class` and an `objective_reached` flag; the flow reads all three in sequence,
    which is what the YAML's four chained branch nodes did.

    `findings` is the finer grain under that classification: the disposition says the plan did
    not carry the story, and each finding says who repairs what. Without it every non-
    `confirmed` disposition billed the plan author, including the ones whose repair was an
    assertion in a committed test file. Empty by default, so a checkpoint written before this
    field existed resumes on the prose path.

    `status` carries the one answer no disposition spells: `blocked`, for a turn that could
    not judge the run at all. It is separate because every `disposition` value classifies a
    run this turn *did* read, and each routes the story to a budget that is then spent on it.
    """

    status: str = ""
    disposition: str = "repair_plan"
    failure_class: str = "plan"
    objective_reached: str = "no"
    findings: list[QaFinding] = []
    notes: str = "QA run assessment produced no valid result."


class QaAudit(CoderResult):
    """`audit-qa.md` — an adversarial second read of a pass that already cleared the gate.

    `verdict` is `stands` or `refuted`, and `refutation_class` narrows a refutation to a
    product contradiction (the story is wrong), a plan defect or an evidence defect. A blank
    reply defaults to `refuted`/`plan-defect`, which spends a plan rework rather than
    shipping an unaudited pass.

    `findings` names who repairs each gap the auditor found. `refutation_class` is the coarse
    classification and routes the product case on its own; the findings are what keep an
    evidence defect whose repair is a test assertion from being billed to the plan author,
    who cannot write it. Empty by default, so an older checkpoint resumes on the prose path.

    `status` is the auditor saying it could not audit — distinct from `refuted`, which is a
    verdict about the evidence rather than an admission there was none to judge.
    """

    status: str = ""
    verdict: str = "refuted"
    refutation_class: str = "plan-defect"
    findings: list[QaFinding] = []
    notes: str = "Independent QA audit produced no valid result."


class QaTriage(CoderResult):
    """`triage-qa.md` — are the findings in-AC fixes, or a scope the author must re-derive?

    The YAML declared these as two bare scalar outputs rather than one object; here they are
    two fields of one model, which produces the same two keys. Both defaults are the YAML's
    and both are deliberately safe: never rescope on a malformed answer, and never let one
    earn the verification-only bonus pass.

    `status` is the triager refusing to sort at all, which neither default covers: both of
    them are *classifications*, and picking one on a turn that could not read the findings
    bills a loop for a judgement nobody made.
    """

    status: str = ""
    triage_action: str = "qa_fix"
    qa_failure_class: str = "code"
    #: Only read on a refusal, and that is why it exists at all: a triage that sorted the
    #: findings said everything it had to say in the two fields above, but one that could
    #: not sort them has said nothing anywhere else — and the escalation it raises would
    #: otherwise reach the operator as "the QA triage reported it cannot proceed", with no
    #: sentence naming what stopped it.
    notes: str = ""


class QaReport(CoderResult):
    """`report-qa-dev(-pass).md` — the findings written out to the tracker, in `dev` runs.

    One model for both prompts: they emit the same key and differ only in whether the story
    passed. Nothing branches on it — the report is the terminal act of a `dev` run — but
    `blocked` is still worth saying rather than reporting a comment that was never written,
    because the run record is the only place that absence would otherwise show up.
    """

    status: str = ""
    notes: str = ""


class RegressionFix(CoderResult):
    """`fix-regression.md` — the attempt to make the committed journey suites green again.

    A claim of success is still not read: the suite is simply re-run, and
    `run_regression_suite` is the only thing that decides whether the fix worked. `status`
    exists for the opposite claim — a fixer saying it *cannot* get there, which the re-run
    can only translate into another red suite and another identical lap.
    """

    status: str = ""
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

    #: The three gate diagnostics `clear-qa-gate-state.py` blanked before each plan turn.
    plan_validation_notes: str = ""
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
    assessment_disposition: str = ""  #: confirmed | repair_plan | extend_plan | repair_setup
    assessment_failure_class: str = ""  #: none | product | plan | environment | evidence
    audit_verdict: str = ""  #: stands | refuted
    audit_refutation_class: str = ""  #: none | product-contradiction | plan-defect | evidence-defect

    #: Which of the above are worth a span dimension. Each is a closed vocabulary of a
    #: handful of words, so the label cardinality they add is bounded.
    VERDICT_LABELS: ClassVar[tuple[str, ...]] = (
        "assessment_disposition",
        "assessment_failure_class",
        "audit_verdict",
        "audit_refutation_class",
    )

    #: The bounded budgets. Each was a `{value: 0}` var with a `seed`/`incr` node pair, except
    #: `plan_validation_rework` — see the flow's `_guard_plan_validation`.
    context_rework: int = 0
    plan_rework: int = 0
    plan_validation_rework: int = 0
    qa_rework: int = 0
    setup_rework: int = 0
    regression_fix: int = 0
    #: How many times the audit has refuted a pass with findings only the plan author can
    #: close. Not a spend counter like the rest — nothing is charged to it and no repair is
    #: skipped because of it. It exists because the audit is the *last* gate, so a fresh
    #: plan finding it raises on its third pass has nothing downstream to catch what it
    #: waives; see `Qa.MAX_BLOCKING_AUDITS`.
    audit_rework: int = 0

    #: The runtime requirements the *latest* blocked QA run named, sorted — the runner's own
    #: `problems` list, which is a machine-readable statement of what was missing rather than
    #: the prose the fixer is briefed with. Written only by `run` (and blanked by it on any
    #: other status), so it always describes the run the flow is currently reacting to.
    blocked_problems: tuple[str, ...] = ()

    #: The same list as the last `setup_fix` turn was asked to repair. The pair is a
    #: repeat detector: a fixer that ran and left the runner naming exactly what it named
    #: before has demonstrated it cannot fix this from inside the run, and a live story spent
    #: three `power="high"` 40-minute laps installing Playwright, proving the install worked,
    #: and getting the identical bundle back — because the copy it repaired was not the
    #: interpreter the QA stage imports ostler into. Neither budget catches that: every lap
    #: is legal, and the flow only stops once `MAX_SETUP_REWORKS` is gone. So the *sameness*
    #: is the signal, and it goes to the operator rather than round again.
    setup_problems: tuple[str, ...] = ()

    #: What the *latest* failing QA run failed at, as a sorted fingerprint — one entry per
    #: non-passing scenario, carrying its status and its assertion/failure counts. Written
    #: only by `run` (and blanked by it on any other status), so it always describes the run
    #: the flow is currently reacting to. Empty for a run that passed, blocked, or was
    #: invalid: none of those is a repairable failure, and the counters below bound them.
    run_failures: tuple[str, ...] = ()
    #: The ids alone of the scenarios that latest failing run did not pass, sorted. Written
    #: and blanked exactly where `run_failures` is, and derived from the same payload.
    #:
    #: The fingerprint above answers "did the last repair move anything"; this answers "what
    #: must the repair turn prove it fixed", which is a different question and needs the ids
    #: without the counts glued to them. `_plan_args` hands them to `repair-qa-plan.md` as the
    #: dry-run contract, and `verify_qa_dry_run` reads the scratch evidence back.
    failed_scenarios: tuple[str, ...] = ()
    #: The per-scenario fix worklist, and where in it the flow is. `apply_fixes` seeds this
    #: from `failed_scenarios` and `fix_item` pops the head as each one is proved green, so a
    #: checkpoint taken mid-worklist resumes at the item that was in flight rather than at the
    #: whole batch again. Empty means there is no per-scenario pass running.
    #:
    #: The split is the point: a whole-report fix turn re-reads every finding on every lap and
    #: proves nothing until a full scored suite run at the end, so one wrong guess costs a
    #: rerun of everything. One scenario, dry-run green before the next one starts, costs one
    #: scenario.
    fix_worklist: tuple[str, ...] = ()
    #: How many turns the *head* of `fix_worklist` has already had. Reset to zero on each pop,
    #: because the budget is per item — a worklist of six scenarios is not six times harder
    #: than one, and a shared counter would starve whatever came last.
    fix_item_rework: int = 0
    #: The dry-run refusals the head of the worklist has already produced, in order. A second
    #: *identical* refusal is the same signal `repaired_failures` carries one loop out: the
    #: fixer ran, and the gate refused it for exactly the same reason, so the next lap has no
    #: new information to work from and the item escalates instead.
    fix_item_problems: tuple[str, ...] = ()
    #: The rejections the *plan lane* has already been sent back on, in order — one entry
    #: per pre-run refusal, carrying which gate raised it and what it said.
    #:
    #: `repaired_failures` is the same signal for the post-run half, and it cannot serve this
    #: one: it fingerprints a *suite run*, and no run happens between a repair and the schema
    #: or dry-run refusal that sends it round again. So those laps had a count bounding them
    #: and nothing else, and a plan repair that answered a refusal with the identical file
    #: could spend the whole budget re-earning the identical refusal — the observed 33-lap
    #: `repair-qa-plan` story is mostly that.
    #:
    #: A second *identical* entry is a repair turn that ran with the gate's reason in hand and
    #: produced nothing the gate reads differently, which is no new information to work from.
    #: It goes to the operator gate rather than round again — an `Await`, never an end: the
    #: operator can always send it back, and the worklist is on the loop so a resume continues.
    #:
    #: Not blanked by `cleared()` — every plan lap clears the gate notes on its way in, so a
    #: field that cleared with them could never hold two laps at once. Zeroed at the
    #: `build_context` rejoin instead, where the diff the plan answers has changed and a
    #: rejection of the old plan says nothing about the new one.
    plan_rejections: tuple[str, ...] = ()
    #: The same fingerprint as the last repair lap — a code fix or a plan repair — was
    #: dispatched against.
    #:
    #: `setup_problems` is the same idea one loop over, and for the same reason: a repair
    #: that ran and left the runner failing at *exactly* the same assertions, the same number
    #: of steps in, has demonstrated that whatever is wrong is not reachable from where it is
    #: repairing. No budget catches that — every lap is legal, so the flow only stops once
    #: `MAX_QA_REWORKS` or `MAX_PLAN_REWORKS` is gone, and each of those laps is a `power`
    #: agent turn plus a full re-run of the suite. A live story burned repairs two through
    #: four that way against a failure that reproduced only under the QA runner's own driver
    #: and never under a second one, which is not a defect any in-repo fix can reach.
    #:
    #: So the *sameness* is the signal, and it goes to the operator rather than round again.
    #: The counts are part of the fingerprint deliberately: a repair that gets the scenario
    #: three steps further before failing has moved, and has earned its next lap.
    repaired_failures: tuple[str, ...] = ()
    #: Which repair loop stamped `repaired_failures` — `"code fix"` or `"QA-plan repair"`.
    #:
    #: The two loops share one fingerprint field but are not one loop, and without this the
    #: sameness test reads across them. A plan repair stamps the fingerprint; the repaired
    #: plan is reviewed, approved, and its findings routed to the *fix* loop — all without a
    #: second run, because a plan repair does not re-run the suite. The fix loop's first
    #: visit then compares the untouched fingerprint against itself and reports "the last
    #: code fix left the QA run failing identically" about a code fix that never happened.
    #: A live story escalated to the operator that way with zero code laps spent.
    repaired_lap: str = ""
    #: Every repair class this story has actually dispatched a lap against — the values
    #: `repaired_lap` has taken, unioned.
    #:
    #: `repaired_lap` names the *latest* one and so cannot answer "has the other hypothesis
    #: ever been tried", which is the question a stall has to ask before ending the story.
    tried_laps: tuple[str, ...] = ()
    #: Whether this story has already taken the one hypothesis-class switch it is allowed.
    #:
    #: A repair that moved nothing refutes the *hypothesis*, not the story: "the plan repair
    #: changed nothing" is evidence the failure is not in the plan, which argues for trying
    #: the product rather than for giving up. A live story was abandoned on exactly that
    #: inference having never spent a code lap, and the five assertions it died on were races
    #: in the plan. So the first stall switches class instead of escalating.
    #:
    #: The whole termination argument rests on this being monotone and written in exactly one
    #: place (`Qa._switched`): one switch per story, only toward a class that has never run,
    #: and the second stall — whichever class raises it — falls through to the operator gate
    #: as before.
    class_switched: bool = False

    #: How many times this story has been handed to the operator gate, counting the one it
    #: is being handed to now. `dev` and `review` already keep this as `plan_blocks` /
    #: `review_blocks`; QA had no equivalent because nothing branched on it, and nothing
    #: branches on it here either — it is what the escalation body puts at the top so a
    #: reader can tell "this story blocked once" from "this story has blocked three times
    #: and each answer bounced". Deliberately not a budget: see `coder.shared.escalation`.
    escalations: int = 0

    #: The parent-owned rescope budget, threaded in and crossed back out on a rescope.
    triage_scope: int = 0

    #: Regression bookkeeping: a fix was applied since the last primary QA, and primary QA
    #: owes a re-run because of it.
    regression_fix_applied: bool = False
    regression_reqa_pending: bool = False

    #: Whether the one verification-only bonus pass past `MAX_QA_REWORKS` has been spent.
    bonus_used: bool = False

    #: Whether a plan has been authored and approved on this pass, which is what tells `stack`
    #: where to go next.
    #:
    #: The stack is stood up *before* the plan is written, so the planner authors against a
    #: surface it can actually reach — a locator that does not resolve, a fixture password that
    #: disagrees with the seed script, a curly apostrophe in an accessible name are all things
    #: one dry run finds and no amount of reading finds. But `stack` is also the setup-fix
    #: loop's re-entry point, and a fixer that repaired a broken emulator must return to the
    #: run, not to a second authoring turn. So the same node reads this flag rather than the
    #: flow needing two of it.
    #:
    #: `build_context` clears it, because it is the loop's join point: every state that routes
    #: back there does so having changed what the diff obligates, and a plan written against
    #: the old obligations is exactly what must not be run. False is therefore also the right
    #: value for a checkpoint written before this field existed — it costs a resumed run one
    #: authoring turn and cannot skip one.
    plan_authored: bool = False

    #: A post-documentation mutation may have changed the as-built truth. True is the
    #: fail-closed default for checkpoints written before this field existed; `Qa.start`
    #: explicitly establishes False for a fresh, known-clean QA pass.
    docs_recheck_required: bool = True

    #: Wall-clock seconds this lane has spent inside agent turns, and how much of that the
    #: plan lane (`plan`, `repair_plan`) took. `Qa.qa_lane_budget_s` and
    #: `Qa.plan_lane_budget_s` are the advisory numbers they are reported against — they are
    #: logged when crossed and decide nothing.
    #:
    #: **Accumulated as deltas, never derived from a start timestamp.** A lane that stored
    #: when it began and subtracted `now` would come back from a resume — or from a run
    #: parked overnight at the operator gate — already over budget, and would report an hour
    #: of effort it never spent. What is being measured is effort, and a charged delta is the
    #: only form of it that survives a checkpoint honestly.
    #:
    #: Deliberately not blanked by `cleared()`, unlike the gate diagnostics: a re-planned
    #: story has no findings against it yet, but the hour it already spent is still gone.
    #: `ensure_stack` is charged to neither — it is `INFRA_NODES` and can legitimately wait
    #: forty minutes for a stack to boot, which is not effort this flow can spend less of.
    lane_seconds: float = 0.0
    plan_lane_seconds: float = 0.0

    #: Consecutive repair laps that have run on the story's QA-plan session chain, so
    #: `repair_plan` can end a conversation that has grown longer than it is worth. Reset to
    #: 0 whenever the chain is, which is what makes it *consecutive* rather than a total —
    #: every rejoin through `build_context` ends the chain, because the diff the plan answers
    #: has changed. It lives here because it must survive a resume: a counter kept anywhere
    #: else would restart at 0 mid-loop and give a stale chain a fresh budget.
    chain_laps: int = 0

    @property
    def plan_rework_total(self) -> int:
        """Repairs spent across validation, review, and post-run plan gates.

        Derived from the durable stage counters so old checkpoints retain what they
        already spent and no duplicated total can drift from its components.

        This is the flow's *outermost* plan ceiling (`Qa.MAX_TOTAL_PLAN_LAPS`), and the only
        thing that reads it. It does not replace the per-stage budgets and is not a smaller
        version of them — see `plan_judgement_rework` for why one shared ceiling of four was
        the wrong shape. What it bounds is their **product**: the stage budgets are checked
        independently, so a story could legally spend three schema repairs, four judgement
        repairs and keep alternating between the two, which is how `plan-qa` reached thirteen
        laps when no single budget permits more than four.
        """
        return self.plan_rework + self.plan_validation_rework

    @property
    def plan_judgement_rework(self) -> int:
        """Repairs spent on the two gates that exercise *judgement* about the plan.

        `validate_qa_plan` is a schema check: `ostler qa validate` imports `qa_plan.py`
        and says whether it is well-formed. Failing it means the plan turn mistyped a
        field — cheap to fix, deterministic, and worth nothing as evidence about whether
        the plan tests the story. The post-run plan gates are the opposite: an agent judging
        coverage against evidence that exists, which is the work the budget exists to bound.

        They shared one ceiling of four until a story spent three repairs on schema typos
        and reached the judging gate with a single revision left, then gave up "after 4 total
        QA-plan repair" — a give-up a human reads as an intractable plan when the plan had
        in fact been read critically exactly once. Mechanical failures now spend their own
        budget (`MAX_PLAN_VALIDATION_REWORKS`) and cannot starve this one.
        """
        return self.plan_rework

    def update(self, **changes: object) -> QaLoop:
        """The same loop with some fields replaced — the port of an `incr`/`emit-kv` node."""
        return self.model_copy(update=changes)

    def with_qa(self, qa: QaResult) -> QaLoop:
        """The same loop carrying a new running verdict."""
        return self.model_copy(update={"qa": qa})

    def with_lap(self, lap: str, **changes: object) -> QaLoop:
        """The same loop dispatching a repair lap of class `lap`, with the class remembered.

        `repaired_lap` is overwritten every lap, so on its own it cannot say whether the
        *other* hypothesis has ever been tried — which is what `Qa._switched` has to know
        before a stall is allowed to end the story. `tried_laps` is the union, and it is
        bounded at three entries by there being three classes.
        """
        return self.model_copy(
            update={
                **changes,
                "repaired_lap": lap,
                "tried_laps": self.tried_laps
                if lap in self.tried_laps
                else (*self.tried_laps, lap),
            }
        )

    def charged(self, seconds: float, *, plan: bool = False) -> QaLoop:
        """The same loop with one turn's wall-clock added to the lane it was spent in.

        `plan` charges the plan lane as well as the whole one — the plan lane is a slice of
        the lane, not a sibling of it, so a plan turn is spent twice over by design.
        """
        return self.model_copy(
            update={
                "lane_seconds": self.lane_seconds + seconds,
                "plan_lane_seconds": self.plan_lane_seconds + (seconds if plan else 0.0),
            }
        )

    def require_docs_recheck(self) -> QaLoop:
        """Mark a possible as-built mutation; this taint is monotonic within the flow."""
        return self.model_copy(update={"docs_recheck_required": True})

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

    `status` is the `qa_status` the four `emit-kv.py` terminals wrote (`passed`,
    `inconclusive`, `replan`, `rescope`), plus `refix` — a product-class failure handed back
    to the dev lane, which owns product code, rather than patched by a QA fixer briefed on a
    QA report. It differs from `rescope` in what moved: a `rescope` means triage amended the
    story's acceptance criteria, a `refix` means they stand and the product does not meet
    them. `inconclusive` is the default for the same reason
    the YAML's `qa_phase` output declared it: a flow that produced nothing has not passed.
    Every budget the flow can exhaust now routes to the operator gate instead — `Qa` never
    returns `inconclusive` on its own; only `target_env="dev"`'s `report_dev` does, because
    that mode does not own the code and reporting the findings *is* the terminal action.

    `triage_scope` crosses the flow boundary in both directions — the parent seeds it and
    reads the bumped value back — which is the one piece of state the isolated flow does not
    own.
    """

    status: str = "inconclusive"
    qa: QaResult = QaResult()
    qa_rework: int = 0
    triage_scope: int = 0
    operator_notes: str = ""
    #: Whether the parent must document again before committing. Missing old results recheck.
    docs_recheck_required: bool = True


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
    "QaPlanValidation",
    "QaReport",
    "QaResult",
    "QaPlanRun",
    "QaRunResult",
    "QaToolCatalog",
    "QaTriage",
    "RegressionFix",
    "RegressionSuite",
    "RegressionSuites",
    "RegressionRun",
    "ScreenshotFlush",
    "SetupResult",
    "StackStatus",
]
